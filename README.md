# Start_Workflow

GitHub Actions 工作流学习项目，包含 5 个常见的 CI/CD 工作流示例及中文文档。

## 工作流列表

| 工作流 | 文件 | 说明 |
|--------|------|------|
| CI Pipeline | `ci.yml` | 构建矩阵、缓存、产物上传 |
| Deploy Pipeline | `deploy.yml` | 多环境部署、并发控制、密钥管理 |
| PR Check | `pr-check.yml` | 标题检查、大小标记、自动分配 |
| Scheduled Tasks | `scheduled.yml` | 定时过期管理、安全审计 |
| Release | `release.yml` | Tag 触发发版、变更日志 |

## 文档

每个工作流都有对应的 `docs/*.md` 文档，逐行解释配置含义。