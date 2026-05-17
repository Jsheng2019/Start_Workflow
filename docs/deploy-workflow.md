# Deploy Pipeline 工作流详解

文件路径：`.github/workflows/deploy.yml`

---

## 整体结构概览

```
name → on(workflow_dispatch + push) → concurrency → jobs → prepare → deploy-staging → deploy-production
```

---

## 逐行说明

### 第 1 行：`name: Deploy Pipeline`

部署流水线的名称，显示在 Actions 面板中。

---

### 第 3-22 行：`on:` 双触发器

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: '选择部署环境'
        required: true
        type: choice
        default: 'staging'
        options:
          - staging
          - production
      version:
        description: '部署版本号（留空则使用最新）'
        required: false
        type: string

  push:
    branches: [main]
```

- **`workflow_dispatch:`** — **手动触发器**。它会在 GitHub Actions 页面生成一个 "Run workflow" 按钮，用户可以填写参数后手动启动。
  - **`inputs:`** — 定义用户可填写的输入参数。不同类型的输入会渲染不同的 UI 控件。
  - **`type: choice`** — 下拉选择框，用户只能从 `options` 中选择。
  - **`type: string`** — 文本输入框，非必填时用户可以留空。
  - **`required: true`** — 必须填写，否则无法触发。
  - **`default:`** — 默认值，可以简化手动触发流程。
- **`push:`** — 当代码推送到 main 分支时自动触发，实现自动部署 staging 的流程。

**为什么同时有手动和自动？**
- `push` 自动触发 → 每次合入代码后自动部署 staging，快速验证
- `workflow_dispatch` 手动触发 → 生产部署需要人工决策时机，选择环境

---

### 第 24-27 行：`concurrency` 并发控制

```yaml
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true
```

- **`concurrency:`** — 并发控制，确保同一时间只有一个部署在进行。
- **`group: deploy-${{ github.ref }}`** — 同一分支上的部署属于同一个并发组。`github.ref` 是当前分支名（如 `refs/heads/main`）。
- **`cancel-in-progress: true`** — 当新的部署开始时，自动取消还在运行中的旧部署。
- **为什么需要？** 避免两次部署同时操作同一环境，导致数据库迁移冲突或服务不稳定。

---

### 第 29-49 行：`prepare` Job — 解析参数

```yaml
prepare:
  runs-on: ubuntu-latest
  outputs:
    env: ${{ steps.resolve-env.outputs.env }}
    version: ${{ steps.resolve-env.outputs.version }}
```

- **`outputs:`** — 将 job 内部的数据暴露给其他 job 使用。这是 job 间传递数据的机制。
- **`steps.resolve-env.outputs.env`** — 引用 ID 为 `resolve-env` 的步骤中设置的 `env` 输出。

#### 步骤细节

```yaml
- name: Resolve environment and version
  id: resolve-env
  run: |
    ENV="${{ github.event.inputs.environment || 'staging' }}"
    VERSION="${{ github.event.inputs.version || github.sha }}"
    VERSION="${VERSION:0:7}"
    echo "env=$ENV" >> $GITHUB_OUTPUT
    echo "version=$VERSION" >> $GITHUB_OUTPUT
```

- **`id: resolve-env`** — 给步骤一个唯一 ID，这样其他步骤或 job 可以通过 `steps.resolve-env.outputs` 访问它的输出。
- **`${{ github.event.inputs.environment || 'staging' }}`** — 表达式中的 `||` 是逻辑或：如果用户填写了 `environment` 就用它，否则默认为 `staging`。
- **`github.sha`** — 触发这次工作流的 commit SHA，是一个完整的 40 位哈希。
- **`${VERSION:0:7}`** — Bash 字符串截取，取前 7 位作为短版本号。
- **`>> $GITHUB_OUTPUT`** — **这是关键**。`$GITHUB_OUTPUT` 是 GitHub Actions 提供的特殊文件路径，将 `key=value` 写入此文件后，该 key 就会成为步骤的输出变量。

---

### 第 51-85 行：`deploy-staging` Job

#### 条件运行

```yaml
if: needs.prepare.outputs.env == 'staging'
```

- **`if:`** — 条件表达式。只有当 `prepare` job 输出的 `env` 等于 `staging` 时，此 job 才会运行。
- 这意味着：如果用户在手动触发时选择了 `production`，这个 job 会直接跳过。

#### environment 环境配置

```yaml
environment:
  name: staging
  url: https://staging.example.com
```

- **`environment:`** — 指定此 job 所属的部署环境。
- **`name:`** — 环境名称。在 GitHub 仓库的 Settings → Environments 中可以为此环境配置：
  - **保护规则**（Protection rules）：要求审批人批准后才能部署
  - **环境密钥**（Environment secrets）：此环境专属的 secrets，与仓库级 secrets 隔离
  - **部署分支限制**：限制哪些分支可以部署到此环境
  - **等待时间**：部署前强制等待 N 分钟
- **`url:`** — 部署完成后，此 URL 会显示在 Actions 摘要页面，方便一键访问。

#### 密钥使用

```yaml
env:
  DATABASE_URL: ${{ secrets.STAGING_DATABASE_URL }}
```

- **`secrets.STAGING_DATABASE_URL`** — 从仓库 Settings → Secrets 中读取。**secrets 的值在日志中会被自动打码（显示为 `***`）**，防止泄露。
- **`env:`** 在步骤级别设置环境变量，仅对该步骤生效。

---

### 第 86-122 行：`deploy-production` Job

```yaml
deploy-production:
  needs: [prepare, deploy-staging]
  if: needs.prepare.outputs.env == 'production'
```

- **`needs: [prepare, deploy-staging]`** — 同时依赖两个 job。只有两者都成功完成后，production 部署才会开始。这确保了 staging 先部署成功。
- **同时依赖 `deploy-staging`** 还有一个隐含作用：保证生产部署之前 staging 一定已经成功。

#### 部署后通知

```yaml
- name: Notify deployment success
  if: success()
  run: echo "Deploy success! Sending notification..."
```

- **`if: success()`** — 内置函数，仅在前面的所有步骤都成功时执行。这样可以区分成功和失败通知。
- 对应的还有 `failure()` —— 在步骤失败时执行；`always()` —— 无论成功失败都执行。

---

## 关键概念总结

| 概念 | 说明 |
|------|------|
| `workflow_dispatch` | 手动触发，可带参数 |
| `inputs` | 手动触发时用户填写的参数 |
| `concurrency` | 防止同一环境并发部署 |
| `outputs` | Job 级别的数据输出，供其他 job 引用 |
| `$GITHUB_OUTPUT` | 写入步骤输出变量的特殊文件 |
| `environment` | 关联 GitHub 环境，启用保护和密钥隔离 |
| `secrets.XXX` | 敏感信息引用，日志中自动屏蔽 |
| `if` | 条件控制 job/step 是否执行 |
| `success()` / `failure()` | 检查前置步骤执行状态 |
| `github.sha` | 触发工作流的 commit hash |
