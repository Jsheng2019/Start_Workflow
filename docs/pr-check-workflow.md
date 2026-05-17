# PR Check 工作流详解

文件路径：`.github/workflows/pr-check.yml`

---

## 整体结构概览

```
name → on(pull_request types) → permissions → jobs → title-check → size-label → auto-assign → unresolved-check
```

---

## 逐行说明

### 第 1 行：`name: PR Check`

用于对 Pull Request 进行自动化检查的工作流。

---

### 第 3-5 行：`on:` 精确的 PR 事件类型

```yaml
on:
  pull_request:
    types: [opened, reopened, synchronize, labeled, unlabeled]
```

- **`pull_request:`** — PR 相关事件触发器。
- **`types:`** — 只监听特定类型的 PR 活动：
  - **`opened`** — PR 被创建时触发。
  - **`reopened`** — 已关闭的 PR 被重新打开时触发。
  - **`synchronize`** — **最常用**。当 PR 的源分支有新的 commit 推送时触发（也就是 PR 更新了代码）。
  - **`labeled`** — 给 PR 添加标签时触发。
  - **`unlabeled`** — 移除 PR 标签时触发。

> 如果不写 `types`，默认监听 `[opened, synchronize, reopened]`。

---

### 第 7-9 行：`permissions` 权限声明

```yaml
permissions:
  contents: read
  pull-requests: write
```

- **`permissions:`** — 明确声明工作流所需的权限，遵循**最小权限原则**。
- **`contents: read`** — 允许读取仓库代码（checkout 需要）。
- **`pull-requests: write`** — 允许对 PR 进行写操作（如添加标签、发表评论）。
- **为什么重要？** 默认情况下 `GITHUB_TOKEN` 有较多权限，显式声明可以限制令牌的能力范围，提高安全性。

---

### 第 11-32 行：`title-check` Job — PR 标题格式检查

```yaml
title-check:
  runs-on: ubuntu-latest
  steps:
    - name: Check PR title format
      uses: amannn/action-semantic-pull-request@v5
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        types: |
          feat
          fix
          docs
          ...
        requireScope: false
```

- **`amannn/action-semantic-pull-request@v5`** — 社区维护的 Action，用于验证 PR 标题是否符合 [Conventional Commits](https://www.conventionalcommits.org/) 规范。
- **`GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`** — 每个工作流自动生成的认证令牌，无需手动创建。在此处用于调用 GitHub API 读取 PR 信息。
- **`types:`** — 允许的提交类型列表，使用 `|` 表示多行字符串。这里的配置覆盖了 Conventional Commits 的全部标准类型：
  - `feat` — 新功能
  - `fix` — Bug 修复
  - `docs` — 文档变更
  - `style` — 代码格式（不影响逻辑）
  - `refactor` — 重构
  - `perf` — 性能优化
  - `test` — 测试相关
  - `build` — 构建系统变更
  - `ci` — CI 配置变更
  - `chore` — 杂项任务
  - `revert` — 回滚提交
- **`requireScope: false`** — 不强制要求 scope。如果设为 `true`，标题必须包含括号中的 scope，如 `feat(api): add endpoint`。

---

### 第 34-53 行：`size-label` Job — 自动标记 PR 大小

```yaml
size-label:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
```

- **`fetch-depth: 0`** — 获取全部提交历史，而非默认的仅最近一次 commit。这是计算 PR 变更行数所需要的（需要与 base 分支做 diff）。

```yaml
    - uses: codelytv/pr-size-labeler@v1
      with:
        xs_label: 'size/xs'
        xs_max_size: 10
        s_label: 'size/s'
        s_max_size: 100
        m_label: 'size/m'
        m_max_size: 500
        l_label: 'size/l'
        l_max_size: 1000
        xl_label: 'size/xl'
        fail_if_xl: false
        files_to_ignore: 'package-lock.json *.lock docs/*'
```

- **`codelytv/pr-size-labeler@v1`** — 根据 PR 变更行数自动添加大小标签。
- **`xs_max_size: 10`** — 变更 ≤ 10 行打上 `size/xs` 标签。
- **`s_max_size: 100`** — 变更 ≤ 100 行打上 `size/s` 标签。
- 以此类推，共有 5 个大小等级。
- **`fail_if_xl: false`** — 即使 PR 超过 1000 行也不使检查失败（只打标签提醒）。
- **`files_to_ignore:`** — 排除自动生成或非关键文件的变更行数。`package-lock.json`、任何 `.lock` 文件、`docs/` 目录下的文件都不计入统计。这样可以让大小标签更真实地反映实际业务代码的变更量。

---

### 第 55-63 行：`auto-assign` Job — 自动分配

```yaml
auto-assign:
  runs-on: ubuntu-latest
  if: github.event.action == 'opened'
```

- **`if: github.event.action == 'opened'`** — 只在 PR 打开时运行一次。每次 push（`synchronize`）不会重新分配。
- **`github.event.action`** — 访问触发事件的具体 action 类型，值就是 `on.pull_request.types` 中的某个（这里是 `opened`）。

```yaml
    - uses: kentaro-m/auto-assign-action@v2.0.0
      with:
        configuration-path: '.github/auto_assign.yml'
```

- **`configuration-path:`** — 指向仓库中的配置文件。此 Action 会从该文件读取分配规则（如：谁 review 哪个目录的文件）。

---

### 第 65-81 行：`unresolved-check` Job — 自定义脚本

```yaml
unresolved-check:
  runs-on: ubuntu-latest
  if: always()
```

- **`if: always()`** — 即使前面的 job 失败，这个 job 也会运行。`always()` 是内置状态检查函数。
- 对比：
  - `success()` — 只有前面全部成功才运行（默认行为）
  - `failure()` — 只有前面有失败才运行
  - `always()` — 无论如何都运行（常用于清理或通知步骤）

```yaml
    - uses: actions/github-script@v7
      with:
        script: |
          const { data: reviews } = await github.rest.pulls.listReviews({
            owner: context.repo.owner,
            repo: context.repo.repo,
            pull_number: context.issue.number,
          });
          console.log(`Found ${reviews.length} reviews`);
          return 'PR check completed';
```

- **`actions/github-script@v7`** — **极其强大的 Action**。允许在 workflow 中直接写 JavaScript/TypeScript 代码，并预置了已认证的 `github` 客户端和 `context` 上下文。
- **`github.rest.pulls.listReviews()`** — 调用 GitHub REST API 获取 PR 的所有 review 记录。这是 `@octokit/rest` 的封装。
- **`context.repo.owner`** / **`context.repo.repo`** — 工作流运行上下文，自动包含当前仓库信息。
- **`context.issue.number`** — 当前 PR 的编号。注意：对于 PR 触发的事件，`context.issue` 实际上就是 PR（GitHub 将 PR 视为一种 issue）。

---

## 关键概念总结

| 概念 | 说明 |
|------|------|
| `pull_request.types` | 精确控制触发 PR 工作流的事件类型 |
| `permissions` | 声明最小权限，限制 GITHUB_TOKEN 的能力 |
| `fetch-depth: 0` | 获取完整 git 历史 |
| `if: github.event.action == '...'` | 根据事件类型条件执行 |
| `always()` / `success()` / `failure()` | 状态检查函数，控制步骤/JOB 的执行条件 |
| `actions/github-script` | 在 workflow 中运行自定义 JS 脚本，访问 GitHub API |
| `context` | 运行上下文对象，包含 repo、issue、sha 等信息 |
| `Conventional Commits` | 约定式提交规范，`type(scope): description` 格式 |
