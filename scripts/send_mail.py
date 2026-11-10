# -*- coding: utf-8 -*-
"""GitHub Actions 执行结果邮件通知（workflow_run 观察者模式）。

发送当前（或被监听的）workflow 运行状态、commit id、分支、耗时、详情链接等
给可配置的目标邮箱。配置全部来自环境变量（仓库 vars / secrets）：

  MAIL_FROM       发件人地址（必填）
  MAIL_TO         收件人，多个用逗号/分号/空格分隔（必填）
  SMTP_PASSWORD   SMTP 授权码（密钥，必填；不是登录密码）
  SMTP_HOST       可选，缺省 smtp.163.com
  SMTP_PORT       可选，缺省 465（SSL）；其他端口走 STARTTLS
  SMTP_USER       可选，缺省取 MAIL_FROM
  MAIL_CC         可选，抄送
  MAIL_SUBJECT    可选，覆盖默认主题模板

通知载荷（由 workflow 以 env 注入，来自 workflow_run 事件）：
  REPO_FULL / RUN_NAME / RUN_CONCLUSION / RUN_SHA / RUN_BRANCH /
  RUN_ACTOR / RUN_EVENT / RUN_NUMBER / RUN_ID / RUN_URL /
  RUN_STARTED_AT / RUN_UPDATED_AT

退出码：0 成功或跳过；1 发送失败。
"""
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate

DEFAULT_SMTP_HOST = "smtp.163.com"
DEFAULT_SMTP_PORT = "465"
BJ = timezone(timedelta(hours=8))

CONCLUSION_DISPLAY = {
    "success": ("✅", "成功"),
    "failure": ("❌", "失败"),
    "cancelled": ("⛔", "已取消"),
    "timed_out": ("⏰", "超时"),
    "startup_failure": ("💥", "启动失败"),
    "manual-test": ("🧪", "手动测试"),
}


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def split_addrs(raw):
    out = []
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def parse_iso(ts):
    """GitHub ISO8601（含 Z 后缀）→ 带时区 datetime；失败返回 None。"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def conclusion_display(conclusion):
    emoji, text = CONCLUSION_DISPLAY.get(conclusion, ("ℹ️", conclusion or "未知"))
    return emoji, text


def build_duration(started_at, updated_at):
    start, end = parse_iso(started_at), parse_iso(updated_at)
    if not start or not end or end < start:
        return ""
    seconds = int((end - start).total_seconds())
    if seconds < 60:
        return f"{seconds} 秒"
    return f"{seconds // 60} 分 {seconds % 60} 秒"


def short_sha(sha):
    return sha[:8] if sha else ""


def build_body(data):
    emoji, text = conclusion_display(data["conclusion"])
    lines = [
        f"GitHub Actions 执行通知（{emoji} {text}）",
        "",
        f"Workflow : {data['run_name']}",
        f"结果     : {text}",
        f"仓库     : {data['repo_full']}",
        f"分支     : {data['branch'] or '/'}",
        f"Commit   : {short_sha(data['sha']) or '/'}",
        f"执行人   : {data['actor'] or '/'}",
        f"触发方式 : {data['event'] or '/'}",
        f"Run 编号 : #{data['run_number']}",
    ]
    duration = build_duration(data["started_at"], data["updated_at"])
    if duration:
        lines.append(f"耗时     : {duration}")
    if data["url"]:
        lines += ["", f"详情链接 : {data['url']}"]
    lines += ["", "（本邮件由 GitHub Actions 自动发送）"]
    return "\n".join(lines)


def main():
    mail_from = env("MAIL_FROM")
    mail_to = split_addrs(env("MAIL_TO"))
    password = env("SMTP_PASSWORD")
    host = env("SMTP_HOST", DEFAULT_SMTP_HOST)
    port = env("SMTP_PORT", DEFAULT_SMTP_PORT)
    user = env("SMTP_USER") or mail_from
    cc = split_addrs(env("MAIL_CC"))

    missing = [n for n, v in (("MAIL_FROM", mail_from),
                              ("MAIL_TO", mail_to),
                              ("SMTP_PASSWORD", password)) if not v]
    if missing:
        print("MAIL-SKIP: 未配置 %s（仓库变量/密钥），本次不发送邮件" % ", ".join(missing))
        return 0

    data = {
        "repo_full": env("REPO_FULL"),
        "run_name": env("RUN_NAME") or "GitHub Actions",
        "conclusion": env("RUN_CONCLUSION"),
        "sha": env("RUN_SHA"),
        "branch": env("RUN_BRANCH"),
        "actor": env("RUN_ACTOR"),
        "event": env("RUN_EVENT"),
        "run_number": env("RUN_NUMBER"),
        "run_id": env("RUN_ID"),
        "url": env("RUN_URL"),
        "started_at": env("RUN_STARTED_AT"),
        "updated_at": env("RUN_UPDATED_AT"),
    }

    emoji, text = conclusion_display(data["conclusion"])
    subject = env("MAIL_SUBJECT") or (
        "[%s] %s%s %s #%s" % (data["repo_full"], emoji, text,
                              data["run_name"], data["run_number"])
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((env("MAIL_FROM_NAME", "GitHub Actions 通知"), mail_from))
    msg["To"] = ", ".join(mail_to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(build_body(data))

    rcpts = mail_to + cc
    port_num = int(port)
    try:
        context = ssl.create_default_context()
        if port_num == 465:
            server = smtplib.SMTP_SSL(host, port_num, timeout=60, context=context)
        else:
            server = smtplib.SMTP(host, port_num, timeout=60)
        with server:
            if port_num != 465:
                server.starttls(context=context)
            server.login(user, password)
            server.send_message(msg, from_addr=mail_from, to_addrs=rcpts)
    except Exception as exc:
        print("MAIL-FAILED: %s: %s" % (type(exc).__name__, exc))
        return 1

    print("MAIL-OK: %s%s %s #%s，收件人 %d 个"
          % (emoji, text, data["run_name"], data["run_number"], len(rcpts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
