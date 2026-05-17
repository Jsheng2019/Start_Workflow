# Scheduled Tasks 工作流详解

文件路径：`.github/workflows/scheduled.yml`

---

## 整体结构概览

```
name → on(schedule + workflow_dispatch) → jobs → stale-management → security-audit → repo-health
```

---

## 逐行说明

### 第 1 行：`name: Scheduled Tasks`

定时执行维护任务的工作流。

---

### 第 3-10 行：`on:` 定时触发器 + 手动触发

```yaml
on:
  schedule:
    - cron: '0 0 * * *'
    - cron: '0 6 * * 1'
  workflow_dispatch:
```

- **`schedule:`** — **定时触发器**，使用 POSIX cron 语法（5 个字段）。
- **cron 语法说明**：`分 时 日 月 星期`

#### 第一个 cron：`0 0 * * *`
| 字段 | 值 | 含义 |
|------|-----|------|
| 分钟 | `0` | 第 0 分钟 |
| 小时 | `0` | 凌晨 0 点 |
| 日 | `*` | 每天 |
| 月 | `*` | 每月 |
| 星期 | `*` | 每周每天 |

**实际效果**：每天 UTC 0:00（北京时间 8:00）运行。

#### 第二个 cron：`0 6 * * 1`
| 字段 | 值 | 含义 |
|------|-----|------|
| 分钟 | `0` | 第 0 分钟 |
| 小时 | `6` | 早上 6 点 |
| 星期 | `1` | 周一 |

**实际效果**：每周一 UTC 6:00（北京时间周一 14:00）运行。

> **重要**：cron 使用 **UTC 时间**，需要自行换算时区。GitHub 不保证精确到分钟的执行时间，高峰时段可能有延迟（最长可能延迟数小时）。

- **`workflow_dispatch:`** — 也允许手动触发，方便随时执行维护任务。

---

### 第 12-50 行：`stale-management` Job — 过期管理

```yaml
stale-management:
  runs-on: ubuntu-latest
  if: github.event_name == 'schedule'
```

- **`if: github.event_name == 'schedule'`** — Job 级别的条件过滤。此 job 只在定时触发时运行，手动触发时跳过。
- **`github.event_name`** — 当前触发事件的类型。可能的值包括 `push`、`pull_request`、`schedule`、`workflow_dispatch`、`release` 等。

```yaml
  permissions:
    issues: write
    pull-requests: write
```

- **权限声明** — `actions/stale` 需要修改 issue 和 PR（添加标签、发表评论、关闭等），所以需要写权限。

#### `actions/stale@v9` 参数详解

```yaml
with:
  days-before-issue-stale: 30
  days-before-pr-stale: 45
  days-before-issue-close: 7
  days-before-pr-close: 7
```

- **`days-before-issue-stale: 30`** — Issue 在 30 天无活动后会被标记为 "过期"（stale）。
- **`days-before-pr-stale: 45`** — PR 给 45 天，比 issue 更长（因为 PR 审核通常需要更多时间）。
- **`days-before-issue-close: 7`** — 被标记为 stale 后再过 7 天无活动，自动关闭。
- **"活动" 的定义**：任何人在 issue/PR 中发表评论或进行修改。

```yaml
  stale-issue-label: 'stale'
  stale-issue-message: '...'
  close-issue-message: '...'
```

- **`stale-issue-label:`** — 标记过期时添加的标签，方便筛选。
- **`stale-issue-message:`** — 标记过期时自动发布的评论内容，告知作者。
- **`close-issue-message:`** — 自动关闭时发布的评论内容。

```yaml
  exempt-issue-labels: 'pinned,security,keep'
  exempt-pr-labels: 'pinned,security,keep'
```

- **`exempt-*`** — **豁免规则**。带有这些标签的 issue/PR 永远不会被标记为过期。
- 典型用例：
  - `pinned` — 置顶的重要 issue
  - `security` — 安全相关，不能自动关闭
  - `keep` — 虽无活动但需要保留

```yaml
  operations-per-run: 30
```

- **`operations-per-run: 30`** — 容量控制。防止一次性标记/关闭过多 issue（GitHub API 有速率限制）。

---

### 第 52-76 行：`security-audit` Job — 安全审计

```yaml
security-audit:
  runs-on: ubuntu-latest
  if: github.event.schedule == '0 6 * * 1'
```

- **精确匹配特定 cron**：只在每周一的定时触发时运行，不在每天的定时触和手动触发时运行。

```yaml
- name: Run npm audit
  continue-on-error: true
  run: npm audit --audit-level=high
```

- **`npm audit`** — 检查项目依赖中是否存在已知的安全漏洞。
- **`--audit-level=high`** — 只报告 `high` 和 `critical` 级别的漏洞，忽略低危和中危。
- **`continue-on-error: true`** — **关键配置**。即使 `npm audit` 发现了高危漏洞（命令返回非零退出码），也不会让 job 失败。这在安全审计场景中很重要：**发现漏洞应该被记录，但不应该阻塞其他流程**。

```yaml
- name: Upload audit report
  if: failure()
  uses: actions/upload-artifact@v4
```

- **`if: failure()`** — 只有审计步骤发现漏洞（失败）时才上传报告。如果审计通过（无高危漏洞），就没有必要上传空报告。

---

### 第 78-108 行：`repo-health` Job — 仓库健康检查

```yaml
repo-health:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/github-script@v7
      with:
        script: |
          const days = 30;
          const since = new Date();
          since.setDate(since.getDate() - days);
```

这是一个**纯脚本驱动的 Job**，使用 JavaScript 编写自定义逻辑。

#### 搜索 API 的使用

```javascript
const { data: stalePrs } = await github.rest.search.issuesAndPullRequests({
  q: `repo:${context.repo.owner}/${context.repo.repo} type:pr created:<${since.toISOString()} state:open sort:created`,
});
```

- **`github.rest.search.issuesAndPullRequests()`** — GitHub 的搜索 API 封装。
- **`q:` 参数** — GitHub 的[搜索查询语法](https://docs.github.com/en/search-github/searching-on-github)：
  - `repo:owner/repo` — 限定在当前仓库
  - `type:pr` — 只搜索 PR
  - `created:<日期` — 创建时间早于指定日期
  - `state:open` — 只查打开的
  - `sort:created` — 按创建时间排序
- **`context.repo.owner`** / **`context.repo.repo`** — 自动解析当前仓库信息。

---

## 关键概念总结

| 概念 | 说明 |
|------|------|
| `schedule` + `cron` | 定时触发，使用 POSIX cron 语法（UTC 时区） |
| `cron` 语法 | `分 时 日 月 星期`，`*` 表示任意 |
| `github.event_name` | 获取触发事件类型，用于条件区分 |
| `continue-on-error: true` | 命令失败不使 job 失败 |
| `if: failure()` | 仅在前面步骤失败时执行（常用于错误处理） |
| `operations-per-run` | 限制批量操作数量，避免触发 API 限制 |
| `exempt-*-labels` | 豁免规则，特定标签的条目不受操作影响 |
| `actions/stale@v9` | 自动化过期 issue/PR 管理 |
| `github.rest.search.*` | 使用 GitHub 搜索 API 查询仓库数据 |
