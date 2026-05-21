# OpenSSF Scorecard Workflow

对仓库进行自动化安全态势评估，帮助发现供应链安全风险并跟踪改进。

## 概览

本 workflow 使用 [OpenSSF Scorecard](https://github.com/ossf/scorecard) 对仓库进行 **18 项安全检查**，结果以 SARIF 格式上传到 GitHub Security 面板，同时发布到 OpenSSF 公共 API（可获取徽章）。

## 触发条件

| 事件 | 说明 |
|------|------|
| `push` to `main`/`master` | 每次合入主线后立即评估 |
| `schedule`（每周一 08:30 UTC） | 定期评估，即使没有新提交也能反映安全态势变化 |
| `workflow_dispatch` | 手动触发，在 Actions 面板点击 "Run workflow" |

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

每项评分 0-10 分。评分含义：

- **0-3**：存在严重风险，需优先修复
- **4-6**：有改进空间
- **7-9**：良好，仅需小幅优化
- **10**：完全符合最佳实践

## 查看结果

### 方式 1：Security 面板

1. 仓库页面 → **Security** tab → **Code scanning**
2. 点击 Scorecard 的告警条目查看详细报告
3. 每条告警包含：检查项名称、分数、修复建议、参考链接

### 方式 2：Workflow Run 日志

1. **Actions** tab → 点击最新的 `OpenSSF Scorecard` run
2. 展开 `Run OpenSSF Scorecard analysis` step
3. 查看 stdout 输出的评分摘要

### 方式 3：OpenSSF 公共面板（含徽章）

分析结果会自动发布到 OpenSSF API。你可以在 README 中添加徽章：

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Jsheng2019/Start_Workflow/badge)](https://scorecard.dev/viewer/?uri=github.com/Jsheng2019/Start_Workflow)
```

点击徽章可查看完整的在线分析报告。

## 权限说明

| 权限 | 用途 | 范围 |
|------|------|------|
| `contents: read` | 检出代码 | 默认（全局） |
| `security-events: write` | 上传 SARIF 结果 | 仅 scorecard job |
| `id-token: write` | OIDC 令牌用于 OpenSSF API 发布 | 仅 scorecard job |

采用最小权限原则：全局默认 `read-all`，仅在需要的步骤显式提权。

## 前置条件

1. **Workflow permissions** 需设为 "Read and write permissions"：
   Settings → Actions → General → Workflow permissions → **Read and write permissions**
2. 如果在私有仓库运行，`publish_results: true` 会将仓库名称等元信息发送到 OpenSSF API。可设为 `false` 来关闭。

## 常见问题

### Q: 为什么 `fetch-depth: 0`？

Scorecard 需要分析完整的 git 历史，例如检查 commit 签名、贡献者分布等。浅克隆会导致部分检查无法执行。

### Q: 如何提升低分项？

Scorecard 报告中的每条告警都附有 "Remediation" 链接，指向具体的修复指南。优先处理评分 0-3 的严重项。

### Q: 多久更新一次结果？

- 每次 push 到 main 后自动更新
- 每周一定期更新（即使代码未变更，漏洞数据库可能更新）
- 随时可手动触发
