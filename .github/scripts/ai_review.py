# -*- coding: utf-8 -*-
"""AI 代码检视：取 PR diff → 分块调用 OpenAI 兼容 LLM → 生成 markdown 检视报告。

用法（在 workflow 里）：
  GH_TOKEN=<token> python3 .github/scripts/ai_review.py <pr-number>

环境变量：
  LLM_BASE_URL  网关 base（含 /v1）
  LLM_API_KEY   API key
  LLM_MODEL     模型名，缺省 deepseek-v4-flash
  REVIEW_OUT    报告输出路径，缺省 /tmp/ai-review.md
  REVIEW_SUMMARY 摘要输出路径，缺省 /tmp/ai-review-summary.txt
  DRY_RUN=1     不调用 LLM，仅打印将发送的 payload 摘要与 diff 统计

退出码：0 成功（含"无变更/无问题"）；1 检视过程失败。
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
import urllib.request

DEFAULT_BASE = ""
DEFAULT_MODEL = "deepseek-v4-flash"
MARKER = "<!-- ai-review -->"

# 不参与检视的文件（噪声大、token 贵）
SKIP_PATTERNS = [
    r"package-lock\.json$", r"yarn\.lock$", r"pnpm-lock\.yaml$", r"poetry\.lock$",
    r"go\.sum$", r"Cargo\.lock$", r"\.min\.(js|css)$", r"\.map$",
    r"\.(png|jpe?g|gif|ico|svg|woff2?|ttf|pdf|zip|gz|xlsx?|docx?)$",
    r"^(dist|build|vendor|node_modules|third_party)/",
]
# 单文件 diff 最多送检行数、单批字符预算
MAX_LINES_PER_FILE = 300
CHUNK_CHAR_BUDGET = 24000   # 约 6k tokens/批
MAX_FILE_CHARS = 12000
MAX_BATCHES = 6             # 最多 6 批，超出提示人工

SYSTEM_PROMPT = """你是资深代码审查员，负责审查 Pull Request 的变更。用简体中文输出 Markdown。

只关注变更部分（diff 的 +/- 行），不要评论未改动的代码。

审查维度（按重要性排序）：
1. 缺陷风险：空指针/越界/边界条件、错误处理缺失、资源泄漏、并发与竞态、时区与编码
2. 安全隐患：注入、越权、敏感信息硬编码、不安全的反序列化、路径穿越
3. 规范问题：命名、格式、与语言惯例或项目约定不符、重复代码、过度复杂
4. 可维护性：可读性、注释缺失（仅在逻辑复杂时提）

严格按以下格式输出，不要添加开场白或结束语：

### 检视结论

<一行结论>，等级：<✅ 通过 | ⚠️ 建议改进 | ❌ 需修改>

### 发现的问题

| 文件:行 | 级别 | 问题 | 建议 |
|---|---|---|---|
| ... | 高/中/低 | ... | ... |

若无问题，此节只写：未发现明显问题。

### 亮点（可选）

- <最多 2 条，没有就整节省略>

要求：
- 每条问题必须能定位到具体文件与行（基于 diff 中的 @@ 行号）
- 结论要克制：风格偏好类问题不要标"高"
- 不要输出 diff 原文，不要复述代码
"""


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 120), **kw)


def get_pr_diff(pr):
    """用 gh 取 PR diff（预合入视图）。"""
    r = run(["gh", "pr", "diff", str(pr)])
    if r.returncode != 0:
        raise RuntimeError(f"gh pr diff 失败: {r.stderr[:400]}")
    return r.stdout


def get_pr_meta(pr):
    r = run(["gh", "pr", "view", str(pr), "--json",
             "number,title,author,baseRefName,headRefName,additions,deletions,changedFiles"])
    if r.returncode != 0:
        return {}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def split_files(diff):
    """把 diff 按文件切开，返回 [(path, text), ...]。"""
    parts = re.split(r"^diff --git ", diff, flags=re.M)
    out = []
    for p in parts:
        if not p.strip():
            continue
        m = re.match(r"a/(\S+) b/", p)
        path = m.group(1) if m else "unknown"
        out.append((path, "diff --git " + p if not p.startswith("diff --git") else p))
    return out


def should_skip(path):
    return any(re.search(pat, path) for pat in SKIP_PATTERNS)


def trim_file(text, max_lines):
    """单文件超长时只保留前 max_lines 行 diff，并标注截断。"""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    kept = lines[:max_lines]
    kept.append(f"...（此文件 diff 共 {len(lines)} 行，已截断至前 {max_lines} 行）")
    return "\n".join(kept)


def build_batches(files):
    """按字符预算聚合成若干批，返回 [{"text":..., "files":[...]}]。"""
    batches, cur, cur_files, cur_len = [], [], [], 0
    for path, text in files:
        text = trim_file(text, MAX_LINES_PER_FILE)
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n...（超长文件已截断）"
        if cur and cur_len + len(text) > CHUNK_CHAR_BUDGET:
            batches.append({"text": "\n".join(cur), "files": cur_files})
            cur, cur_files, cur_len = [], [], 0
        cur.append(text)
        cur_files.append(path)
        cur_len += len(text)
    if cur:
        batches.append({"text": "\n".join(cur), "files": cur_files})
    return batches


def llm_call(base, key, model, user_content, timeout=180):
    """调用 OpenAI 兼容 /chat/completions，返回 content 文本。"""
    url = base.rstrip("/") + "/chat/completions"
    # 兼容性：部分模型（如 kimi 系）只接受 temperature=1
    temp = 1 if re.search(r"kimi", model, re.I) else 0.2
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 3000,      # reasoning 模型会消耗思考 token，留足预算
        "temperature": temp,
        "stream": False,
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "content-type": "application/json",
        "authorization": f"Bearer {key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"LLM HTTP {e.code}: {detail}")
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {type(e).__name__}: {e}")

    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:
        # reasoning 模型 token 被思考吃光的典型表现
        rt = data.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        raise RuntimeError(f"模型返回空内容（reasoning_tokens={rt}），请增大 max_tokens")
    return content


def merge_reports(parts, meta, stats):
    """合并多批检视结果为一份报告。"""
    head = [MARKER, ""]
    if meta:
        head.append(f"## 🤖 AI 代码检视 · PR #{meta.get('number')} {meta.get('title', '')}")
        head.append("")
        head.append(f"- 变更：`{meta.get('headRefName')}` → `{meta.get('baseRefName')}`"
                    f" · +{meta.get('additions', 0)}/-{meta.get('deletions', 0)}"
                    f" · {meta.get('changedFiles', 0)} 个文件")
        head.append(f"- 检视范围：{stats['reviewed']} 个文件 / {stats['skipped']} 个跳过"
                    f" / {stats['batches']} 批（模型 `{stats['model']}`）")
        bj = timezone(timedelta(hours=8))
        head.append(f"- 检视时间：{datetime.now(bj).strftime('%Y-%m-%d %H:%M:%S')}（北京时间）")
        head.append("")
    if len(parts) == 1:
        body = parts[0]
    else:
        # 多批时按批分节，避免表格混在一起
        body = "\n\n".join(f"#### 批次 {i+1}\n\n{p}" for i, p in enumerate(parts))
    head.append(body)
    head.append("")
    head.append("---")
    head.append("<sub>本检视由 AI 自动生成，仅供参考，不阻塞合并；请以人工评审为准。</sub>")
    return "\n".join(head)


def extract_verdict(report):
    """从报告中提取结论行，用于邮件摘要。"""
    m = re.search(r"^### 检视结论\s*\n+\s*(.+)", report, re.M)
    line = m.group(1).strip() if m else "（未能解析结论）"
    # 统计问题表格行数
    rows = re.findall(r"^\|\s*[^|]+\|\s*(高|中|低)\s*\|", report, re.M)
    counts = {k: rows.count(k) for k in ("高", "中", "低")}
    return line, counts, len(rows)


def main():
    if len(sys.argv) < 2:
        print("usage: ai_review.py <pr-number>", file=sys.stderr)
        return 2
    pr = sys.argv[1]
    base = env("LLM_BASE_URL", DEFAULT_BASE)
    key = env("LLM_API_KEY")
    model = env("LLM_MODEL", DEFAULT_MODEL)
    out_path = env("REVIEW_OUT", "/tmp/ai-review.md")
    summary_path = env("REVIEW_SUMMARY", "/tmp/ai-review-summary.txt")
    dry = env("DRY_RUN") == "1"

    if not dry and (not base or not key):
        print("SKIP: LLM_BASE_URL / LLM_API_KEY 未配置")
        return 0

    diff = get_pr_diff(pr)
    if not diff.strip():
        print("SKIP: PR 无代码变更")
        return 0
    meta = get_pr_meta(pr)

    files = split_files(diff)
    kept, skipped = [], 0
    for path, text in files:
        if should_skip(path):
            skipped += 1
            continue
        kept.append((path, text))
    if not kept:
        print(f"SKIP: {len(files)} 个文件全部属于跳过类型")
        return 0

    batches = build_batches(kept)
    if len(batches) > MAX_BATCHES:
        print(f"WARN: 变更过大（{len(batches)} 批），只检视前 {MAX_BATCHES} 批")
        batches = batches[:MAX_BATCHES]

    print(f"共 {len(files)} 个文件，送检 {len(kept)} 个，跳过 {skipped} 个；分批 {len(batches)}")

    if dry:
        for i, b in enumerate(batches, 1):
            print(f"  批 {i}: {len(b['files'])} 文件, {len(b['text'])} 字符 → {b['files'][:5]}")
        return 0

    reports = []
    for i, b in enumerate(batches, 1):
        files_list = ", ".join(os.path.basename(f) for f in b["files"][:8])
        user = (f"PR #{pr} 第 {i}/{len(batches)} 批变更，涉及文件：{files_list}\n\n"
                f"```diff\n{b['text']}\n```")
        print(f"[批 {i}/{len(batches)}] {len(b['files'])} 文件, {len(b['text'])} 字符 …")
        content = llm_call(base, key, model, user)
        reports.append(content)
        print(f"[批 {i}/{len(batches)}] 完成，{len(content)} 字符")

    report = merge_reports(reports, meta, {
        "reviewed": len(kept), "skipped": skipped,
        "batches": len(batches), "model": model,
    })
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    verdict, counts, total = extract_verdict(report)
    summary = (f"{verdict}\n"
               f"问题数：高 {counts['高']} / 中 {counts['中']} / 低 {counts['低']}（共 {total} 条）\n"
               f"检视范围：{len(kept)} 个文件、{len(batches)} 批、模型 {model}")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print("SUMMARY:", summary.replace("\n", " | "))
    print(f"报告已写入 {out_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"AI-REVIEW-FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
