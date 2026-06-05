# 工作流 5：复合操作（Composite Action）— 完整指南

> **受众：** 想了解如何将多个步骤封装为可复用组件的开发者。
>
> **文件：** `.github/actions/node-ci-gate/action.yml` + `.github/workflows/demo-composite.yml`
>
> **涉及的概念：** composite action 语法、inputs/outputs、步骤组合、嵌套 actions、`github.action_path`、矩阵 × 复合操作

---

## 目录

1. [什么是复合操作？](#1-什么是复合操作)
2. [文件概览](#2-文件概览)
3. [action.yml 语法逐段解析](#3-action.yml-语法逐段解析)
4. [inputs：声明可配置参数](#4-inputs声明可配置参数)
5. [outputs：对外暴露结果](#5-outputs对外暴露结果)
6. [runs.steps：步骤编排](#6-runssteps步骤编排)
7. [工作流中调用复合操作](#7-工作流中调用复合操作)
8. [矩阵 × 复合操作](#8-矩阵-×-复合操作)
9. [复合操作 vs 可复用工作流 vs JavaScript Action](#9-复合操作-vs-可复用工作流-vs-javascript-action)
10. [关键模式总结](#10-关键模式总结)

---

## 1. 什么是复合操作？

复合操作（composite action）是 GitHub Actions 的三种自定义 action 之一。它允许你把多个 `run` 步骤（甚至其他 action）打包成一个可复用的单元。

**类比：** 就像把一段 shell 脚本封装成函数——调用方只需要知道输入和输出，不需要关心内部实现。

```yaml
# 不用复合操作：每个工作流重复这 20 行
- uses: actions/setup-node@v4
- run: npm ci
- run: npm test
- run: npm run build

# 用复合操作：一行替代
- uses: ./.github/actions/node-ci-gate
  with:
    node-version: '20'
```

---

## 2. 文件概览

本 demo 包含两个文件：

| 文件 | 作用 |
|------|------|
| `.github/actions/node-ci-gate/action.yml` | 复合操作定义（核心） |
| `.github/workflows/demo-composite.yml` | 调用方工作流（演示用法） |

**node-ci-gate** 做的事情：setup Node.js → 缓存 npm → 安装依赖 → lint → test → build → 安全审计。全部在一个 action 里完成。

---

## 3. action.yml 语法逐段解析

```yaml
name: Node.js CI Gate           # 在 GitHub UI 中显示的名称
description: >                  # 描述（支持多行 > 折叠）
  Composite action that sets up Node.js, installs dependencies,
  runs lint, test, and build.

inputs:                         # 可配置参数（见 §4）
outputs:                        # 对外暴露的结果（见 §5）
runs:                           # 执行逻辑
  using: composite              # 必须是 "composite"
  steps:                        # 步骤列表（语法和 workflow job 中的 steps 一样）
```

**关键点：** `runs.using` 必须设为 `composite`。这是告诉 GitHub Actions 引擎"这是一个组合型 action"。

---

## 4. inputs：声明可配置参数

```yaml
inputs:
  node-version:
    description: 'Node.js version to use'
    required: false           # 可选参数
    default: '20'             # 默认值
  working-directory:
    description: 'Directory to run commands in'
    required: false
    default: '.'
  audit-level:
    description: 'npm audit severity threshold'
    required: false
    default: 'low'
```

**语法要点：**
- `required: true` — 调用方必须提供
- `required: false` — 必须有 `default` 值
- 在 steps 中通过 `${{ inputs.node-version }}` 引用

---

## 5. outputs：对外暴露结果

```yaml
outputs:
  lint-status:
    description: 'pass / fail / skipped'
    value: ${{ steps.lint.outputs.status }}    # 引用内部 step 的 output
  test-status:
    description: 'pass / fail'
    value: ${{ steps.test.outputs.status }}
  build-status:
    description: 'pass / fail'
    value: ${{ steps.build.outputs.status }}
```

**核心机制：** 复合操作的 output 本质上是**透传内部 step 的 output**。每个 output 的 `value` 指向 `${{ steps.<内部step的id>.outputs.<内部output名> }}`。

> 注意：内部 step 必须用 `echo "name=value" >> "$GITHUB_OUTPUT"` 来设置 output，和普通 job step 一样。

---

## 6. runs.steps：步骤编排

复合操作的 steps 语法**和 workflow job 中的 steps 完全相同**——支持 `run`、`uses`、`env`、`working-directory`、`continue-on-error` 等所有指令。

### 6.1 调用其他 action

复合操作**可以嵌套调用其他 action**：

```yaml
- name: Setup Node.js
  id: node
  uses: actions/setup-node@v4      # 在复合操作中调用官方 action
  with:
    node-version: ${{ inputs.node-version }}
```

### 6.2 动态计算

```yaml
- name: Compute npm cache key
  id: cache-key
  shell: bash
  run: |
    if [ -f package-lock.json ]; then
      HASH=$(sha256sum package-lock.json | cut -c1-16)
      echo "key=npm-${{ runner.os }}-${HASH}" >> "$GITHUB_OUTPUT"
    fi
```

### 6.3 非阻塞步骤

```yaml
- name: Lint
  id: lint
  shell: bash
  continue-on-error: true          # lint 失败不中断，但会标记 status=fail
  run: |
    if npm run lint 2>&1; then
      echo "status=pass" >> "$GITHUB_OUTPUT"
    else
      echo "status=fail" >> "$GITHUB_OUTPUT"
    fi
```

### 6.4 安全审计（可配置阈值）

```yaml
- name: Security audit
  shell: bash
  continue-on-error: true
  run: |
    npm audit --audit-level=${{ inputs.audit-level }} 2>&1 || true
```

---

## 7. 工作流中调用复合操作

### 7.1 基本调用

```yaml
jobs:
  ci-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run CI gate
        id: gate
        uses: ./.github/actions/node-ci-gate   # 本地复合操作路径
        with:
          node-version: '20'
          audit-level: 'low'

      - name: Show results
        run: |
          echo "Lint:  ${{ steps.gate.outputs.lint-status }}"
          echo "Test:  ${{ steps.gate.outputs.test-status }}"
          echo "Build: ${{ steps.gate.outputs.build-status }}"
```

**引用方式：** 本地复合操作用 `./.github/actions/<name>`，已发布的操作用 `owner/repo@ref`。

### 7.2 输出消费

```yaml
steps:
  - id: gate
    uses: ./.github/actions/node-ci-gate
    with:
      node-version: '20'

  # 通过 steps.<id>.outputs.<output名> 读取
  - run: echo "Result: ${{ steps.gate.outputs.test-status }}"
```

---

## 8. 矩阵 × 复合操作

复合操作和矩阵策略天然兼容：

```yaml
jobs:
  ci-gate:
    strategy:
      matrix:
        node-version: ['18', '20', '22']
      fail-fast: false
    steps:
      - uses: ./.github/actions/node-ci-gate
        with:
          node-version: ${{ matrix.node-version }}   # 每个矩阵维度传不同值
```

效果：同一套 CI 流程在 Node 18/20/22 三个版本上并行执行，每次只需一行 `uses`。

---

## 9. 复合操作 vs 可复用工作流 vs JavaScript Action

| 特性 | Composite Action | 可复用工作流 | JavaScript Action |
|------|:---:|:---:|:---:|
| 存储位置 | `.github/actions/` | `.github/workflows/` | `.github/actions/` |
| 调用方式 | `uses: ./.github/actions/x` | `uses: owner/repo/.github/workflows/x.yml@ref` | `uses: ./.github/actions/x` |
| 包含其他 action | ✅ 可以 | ✅ 可以 | ❌ 不可以 |
| 支持 if/条件 | ❌ 有限 | ✅ 完整 | ✅ 完整 |
| secrets 继承 | ❌ 需显式传 | ✅ 可继承 | ❌ 需显式传 |
| 适用场景 | 封装步骤组合 | 封装整个 job 逻辑 | 需要复杂逻辑（API 调用等） |
| 速度 | 快（在调用方 runner 上运行） | 慢（需要启动新 runner） | 快 |

**选择建议：**
- 封装 3-15 个步骤 → 用 Composite Action
- 封装整个 job（含 secrets、环境等）→ 用可复用工作流
- 需要调用 API、解析复杂数据 → 用 JavaScript Action

---

## 10. 关键模式总结

| 模式 | 示例 |
|------|------|
| **可选输入 + 默认值** | `default: '20'` |
| **输出透传** | `value: ${{ steps.<id>.outputs.<name> }}` |
| **嵌套官方 action** | `uses: actions/setup-node@v4` |
| **动态缓存键** | 从 `sha256sum` 计算 hash 作为 cache key 的一部分 |
| **非阻塞检查** | `continue-on-error: true` + 手动设 `status` output |
| **矩阵 × 复合** | `with: { node-version: ${{ matrix.node-version }} }` |
| **步骤摘要输出** | 在 workflow 中用 `>> "$GITHUB_STEP_SUMMARY"` 渲染结果表 |

---

## 运行方式

1. 推送代码到 `Jsheng2019/Start_Workflow` 仓库
2. Actions tab → 找到 **"Demo - Composite Action"**
3. 点击 **Run workflow** → 选择 Node 版本和 audit 级别 → **Run workflow**
4. 查看 matrix 并行运行结果，以及 summary job 的聚合输出
5. 对比 `.github/actions/node-ci-gate/action.yml`（定义）和 `demo-composite.yml`（调用），理解声明式 vs 调用式的区别
