# OpenSSF Scorecard Workflow

对仓库进行自动化安全态势评估，18 项供应链安全检查，帮助发现安全风险并跟踪改进。

## 概览

使用 [ossf/scorecard-action](https://github.com/ossf/scorecard-action)（固定 v2.4.3）对仓库执行 **18 项安全检查**，结果以 JSON 格式输出到 Workflow Step Summary 和控制台日志。

- **零额外权限**：不请求 `security-events` 或 `id-token`，开箱即用
- **Step Summary 表格**：每次运行后在 Actions 页面直接查看可视化评分表
- **可选升级**：如需 Security 面板 + 徽章，参考下方 [升级指南](#升级至-sarif--徽章)

## 触发条件

| 事件 | 说明 |
|------|------|
| `push` to `main`/`master` | 每次合入主线后立即评估 |
| `schedule`（每周一 08:30 UTC） | 定期评估，即使没有新提交，漏洞数据库也可能更新 |
| `workflow_dispatch` | 手动触发，Actions 面板 → OpenSSF Scorecard → Run workflow |

## 工作流程（4 步）

```
push/schedule/manual
        │
        ▼
┌─────────────────┐
│ 1. Checkout     │  actions/checkout@v4, fetch-depth: 0（完整 git 历史）
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. Scorecard    │  ossf/scorecard-action@v2.4.3
│    Analysis     │  产出 results.json（18 项检查）
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. Format       │  Python 脚本解析 JSON → Markdown 表格
│    Results      │  写入 GITHUB_STEP_SUMMARY
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. Log Console  │  cat results.json（备查原始数据）
└─────────────────┘
```

## 检查项（18 项）

| 类别 | 检查项 | 说明 |
|------|--------|------|
| **供应链** | Dependency-Update-Tool | 是否使用 Dependabot/Renovate 自动更新依赖 |
| | Fuzzing | 是否使用 OSS-Fuzz 进行模糊测试 |
| | Vulnerabilities | 是否存在已知漏洞（OSV 数据库） |
| | Signed-Releases | 发布是否经过签名 |
| **构建与发布** | Build-As-Code | CI/CD 是否以代码定义（GitHub Actions） |
| | Packaging | 构建过程是否可重现 |
| | Pinned-Dependencies | 依赖是否锁定版本（非浮动 tag） |
| | Token-Permissions | Workflow token 权限是否最小化 |
| **代码质量** | SAST | 是否使用静态分析工具（CodeQL 等） |
| | CI-Best-Practices | CI 配置是否遵循最佳实践 |
| | Code-Review | 是否要求代码审查后才能合入 |
| | Branch-Protection | 是否启用分支保护规则 |
| **维护** | Maintained | 项目是否持续维护 |
| | Contributors | 是否有多个组织的贡献者 |
| | CII-Best-Practices | 是否获得 OpenSSF 最佳实践徽章 |
| **风险** | Binary-Artifacts | 仓库是否包含二进制文件 |
| | Dangerous-Workflow | 是否存在危险的 Workflow 模式 |
| | License | 是否有明确的许可证 |
| | Webhooks | Webhook 是否使用 Secret |

每项评分 0-10 分：

- **0-3** 🔴：存在严重风险，需优先修复
- **4-6** 🟡：有改进空间
- **7-9** 🟢：良好，仅需小幅优化
- **10** ✅：完全符合最佳实践

## 查看结果

### 方式 1：Step Summary（推荐）

1. 仓库页面 → **Actions** → 点击最新的 `OpenSSF Scorecard` run
2. 在运行页面的 **Summary** 区域即可看到评分表格
3. 表格包含每项检查的名称、分数、风险等级

### 方式 2：控制台日志

1. Actions 页面 → 点击具体 run
2. 展开 **Log results to console** step
3. 查看完整 JSON 原始数据

## 权限说明

| 权限 | 用途 |
|------|------|
| `contents: read` | 检出代码（`actions/checkout` 默认权限） |
| `actions: read` | GitHub Actions 自动注入，无感知 |

**不需要**额外权限。如果升级到 SARIF 模式才需 `security-events: write`。

## 升级至 SARIF + 徽章

如果希望在 Security 面板查看结果并添加 OpenSSF 徽章，需要两步：

### 1. 启用仓库写权限

Settings → Actions → General → Workflow permissions → **Read and write permissions**

### 2. 修改 workflow

```yaml
jobs:
  scorecard:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: ossf/scorecard-action@v2.4.3
        with:
          results_file: results.sarif
          results_format: sarif
          publish_results: true
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
```

然后可在 README 添加徽章：

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Jsheng2019/Start_Workflow/badge)](https://scorecard.dev/viewer/?uri=github.com/Jsheng2019/Start_Workflow)
```

## 常见问题

### Q: 为什么 `fetch-depth: 0`？

Scorecard 需要完整的 git 历史来分析 commit 签名、贡献者分布、活动时间线等。浅克隆（默认 fetch-depth: 1）会导致部分检查无法执行或降分。

### Q: 为什么固定版本 @v2.4.3 而不是 @v2？

固定主版本锁定已知可用的版本，避免上游 breaking change 导致 workflow 突然失败。建议每季度手动更新一次。

### Q: 如何提升低分项？

Scorecard 报告中的每条检查都有对应的 [修复指南](https://github.com/ossf/scorecard#remediation)。优先处理评分 0-3 的严重项：

1. **Branch-Protection** — 在 Settings → Branches 添加规则
2. **Token-Permissions** — 在 workflow 顶部添加 `permissions: read-all`
3. **Dangerous-Workflow** — 避免在 `pull_request_target` 中使用 `pull_request` 上下文
4. **Pinned-Dependencies** — 将 GitHub Actions 锁定到 commit SHA

### Q: 多久更新一次结果？

- 每次 push 到 main 后自动更新
- 每周一 08:30 UTC 定期更新
- 随时可手动触发
