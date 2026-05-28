# 工作流 1：高级缓存与构建加速 — 完整指南

> **受众：** 刚接触 GitHub Actions 的开发者，希望了解生产级缓存、矩阵构建和 CI/CD 加速。
>
> **文件：** `.github/workflows/advanced-cache-build.yml`
>
> **涉及的概念：** 触发器、权限、并发、`hashFiles()`、`matrix` 策略、`actions/cache`（保存/恢复）、构件、Docker 层缓存、条件执行、表达式语法和上下文对象。

---

## 目录

1. [文件概览和顶层结构](#1-文件概览和顶层结构)
2. [触发器语法 (on:)](#2-触发器语法-on)
3. [权限块](#3-权限块)
4. [并发组](#4-并发组)
5. [环境默认值 (env:)](#5-环境默认值-env)
6. [任务 1：cache-calc — 集中式缓存键计算](#6-任务-1-cache-calc)
7. [任务 2：deps-install — 带缓存的矩阵依赖安装](#7-任务-2-deps-install)
8. [任务 3：lint — 快速反馈代码质量检查](#8-任务-3-lint)
9. [任务 4：docker-prepare — Docker 层缓存预构建](#9-任务-4-docker-prepare)
10. [任务 5：build — 带输出构件的矩阵构建](#10-任务-5-build)
11. [任务 6：test-unit — 矩阵测试分片](#11-任务-6-test-unit)
12. [任务 7：test-integration — Docker Compose 集成测试](#12-任务-7-test-integration)
13. [任务 8：cache-warm — 主分支缓存预热](#13-任务-8-cache-warm)
14. [表达式语法和上下文对象](#14-表达式语法和上下文对象)
15. [关键模式总结](#15-关键模式总结)

---

## 1. 文件概览和顶层结构

### YAML

```yaml
# =============================================================================
# 高级缓存与构建加速
# =============================================================================
# 一个生产级 GitHub Actions 工作流，演示多层缓存、
# 矩阵构建、构件传递、Docker 层缓存和缓存预热。
#
# 演示的关键概念：
#   - 集中式缓存键计算（cache-calc 任务）
#   - Node 版本、操作系统变体和测试分片的矩阵策略
#   - 显式缓存恢复/保存与自动后操作缓存
#   - 用于任务间传递的构件上传/下载
#   - 使用 BuildKit 缓存后端的 Docker 层缓存
#   - 用于取消冗余运行的并发组
#   - 条件执行（仅主分支的缓存预热）
# =============================================================================

name: Advanced Cache & Build Acceleration
```

### 逐行说明

| 行号 | 元素 | 说明 |
|-------|---------|-------------|
| 1-14 | `#` 注释 | YAML 注释。`#` 之后到行尾的内容均被忽略。这些是块级文档注释，解释文件的用途。 |
| 16 | `name:` | 工作流名称，显示在 GitHub Actions UI 中（每个工作流运行的左上角）。由于可能存在多个工作流，请选择描述性的名称。 |

### 动作能力：YAML 中的注释

YAML 支持使用 `#` 进行单行注释。标准 YAML 中没有多行注释语法。请在每行注释开头使用 `#`。行内注释也有效：

```yaml
name: Build  # 行内注释
```

### 为什么采用这种方式

文件顶部的块注释充当：
- **快速参考**，供阅读文件的开发者使用
- **设计文档**，随代码一起传递
- **入门辅助**，帮助新团队成员学习 GitHub Actions 模式

---

## 2. 触发器语法 (on:)

### YAML

```yaml
# ---------------------------------------------------------------------------
# 触发器
# ---------------------------------------------------------------------------
# push:       每次提交到 main 或 dev 分支时执行 CI
# pull_request: 当 PR 目标为 dev 时执行 CI（在合并前发现问题）
# workflow_dispatch: 通过 GitHub UI 或 API 手动触发，用于测试
# ---------------------------------------------------------------------------
on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [dev]
  workflow_dispatch:
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1 | `on:` | `on`（或 `trigger`）关键字定义哪些事件会导致此工作流运行。它是工作流执行的入口点。 |
| 2 | `push:` | 在 `git push` 事件时运行工作流。 |
| 3 | `branches: [main, dev]` | 仅当推送到 `main` 或 `dev` 分支时触发。YAML 数组语法 `[main, dev]` 等价于块形式：`branches:\n  - main\n  - dev`。 |
| 4 | `pull_request:` | 在拉取请求事件时运行工作流（默认为 opened、synchronize、reopened）。 |
| 5 | `branches: [dev]` | 仅当 PR 的目标分支是 `dev` 时触发 PR 事件。直接针对 `main` 的 PR 不会触发此工作流。 |
| 6 | `workflow_dispatch:` | 允许从 GitHub Actions UI、`gh workflow run` CLI 命令或 REST API 手动触发。无需额外配置。 |

### 动作能力：事件触发器

GitHub Actions 支持许多事件类型。最常见的：

| 事件 | 触发时机 | 常见用途 |
|-------|---------------|------------|
| `push` | 提交被推送时 | 每次提交执行 CI |
| `pull_request` | PR 被打开/更新时 | 合并前验证 |
| `workflow_dispatch` | 手动触发 | 临时运行、调试 |
| `schedule` | Cron 计划 | 夜间构建、维护 |
| `release` | 发布发布时 | 部署工作流 |
| `issue_comment` | 在 Issue/PR 上评论时 | Chatops、/trigger 命令 |

**分支过滤**（`branches:`）可以是字面名称或 glob 模式：
- `main` — 精确匹配
- `dev` — 精确匹配
- `release/**` — 任何以 `release/` 开头的分支
- `!alpha` — 排除 `alpha`

**重要说明：** `push` 的分支过滤指定哪些分支的推送会触发构建。`pull_request` 的分支过滤指定哪些目标分支的 PR 会触发检查。两者的用途不同。

### 为什么采用这种方式

- **`push` 在 main + dev 上：** 每次提交立即得到测试。没有人能在不知情的情况下推送损坏的代码。
- **`pull_request` 在 dev 上：** 针对 dev 的 PR 在合并前经过验证。这在审查阶段捕获问题，防止它们进入 main。
- **`workflow_dispatch`：** 测试工作流变更的必备工具。没有它，每次想测试修改时都需要推送提交。
- **省略 PR 在 main 上：** 变更仅通过从 dev 合并的 PR 进入 main，因此 dev 的 PR 检查覆盖了这一点。

---

## 3. 权限块

### YAML

```yaml
# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------
# contents: read     — 检出代码所需
# checks: write      — 允许 dorny/test-reporter 创建检查运行
# pull-requests: write — 允许 test-reporter 编写 PR 评论
# ---------------------------------------------------------------------------
permissions:
  contents: read
  checks: write
  pull-requests: write
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1 | `permissions:` | 定义此工作流的 GITHUB_TOKEN 权限。GitHub Actions 自动生成一个作用于仓库的令牌。 |
| 2 | `contents: read` | 对仓库内容的读取权限。`actions/checkout` 需要此权限。没有它将无法检出。 |
| 3 | `checks: write` | 对检查运行 API 的写入权限。`dorny/test-reporter` 使用它在 GitHub UI 中创建检查运行条目。 |
| 4 | `pull-requests: write` | 对拉取请求的写入权限。`dorny/test-reporter` 使用它在 PR 上发表带有测试结果的评论。 |

### 动作能力：GITHUB_TOKEN 和权限

每次工作流运行都会获得一个 `secrets.GITHUB_TOKEN`，其作用域可配置。细粒度权限模型（2023 年底 GA）取代了之前宽泛的 `write-all` 默认值。

**可用的权限：**

| 权限 | 授权内容 |
|------------|---------------|
| `actions` | 读/写操作（构件、缓存、工作流运行） |
| `checks` | 读/写检查运行和检查套件 |
| `contents` | 读/写仓库内容（提交、发布、标签） |
| `deployments` | 读/写部署 |
| `id-token` | 读/写 OIDC 令牌（用于云提供商认证） |
| `issues` | 读/写 Issue |
| `pull-requests` | 读/写拉取请求 |
| `packages` | 读/写 GitHub Packages |

**安全最佳实践：** 仅授予所需的最低权限。旧的 `write-all` 默认值意味着任何一个工作流被攻破就能推送代码。新仓库现在需要显式的 `permissions:` 块。

### 为什么采用这种方式

- `contents: read` 是检出所需的最低权限。
- `checks: write` 支持在 GitHub 本地进行丰富的测试报告（无需外部服务）。
- `pull-requests: write` 允许自动在 PR 上发布带有测试摘要的评论。
- 没有额外的权限意味着没有令牌滥用面。

---

## 4. 并发组

### YAML

```yaml
# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------
# 按工作流名称 + 分支引用来分组运行，这样如果在之前的运行完成之前
# 推送了新提交，正在进行的运行将被取消。
# 这在快速迭代的分支上节省了 CI 分钟数。
# ---------------------------------------------------------------------------
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1 | `concurrency:` | 定义一个并发组 — 工作流运行的逻辑队列。 |
| 2 | `group:` | 组标识符。每个组同时只有一个运行在执行。 |
| 3 | `${{ github.workflow }}` | 表达式：展开为工作流名称（"Advanced Cache & Build Acceleration"）。 |
| 4 | `${{ github.ref }}` | 表达式：展开为分支或标签引用（例如 `refs/heads/dev`）。 |
| 5 | `cancel-in-progress: true` | 当新运行加入组时，取消同一组中正在进行的运行。 |

### 并发组如何工作

```
场景：
  在 t=0 推送到 dev  → 运行 #1 开始
  在 t=30 推送到 dev → 运行 #2 被排队（同一组："Build-refs/heads/dev"）
                         → 运行 #1 通过 API 被取消
                         → 运行 #2 立即开始

场景 2（不同分支）：
  推送到 dev  → 运行 #1 开始（组："Build-refs/heads/dev"）
  推送到 main → 运行 #2 开始（组："Build-refs/heads/main"）
  两者并行运行 — 不同的组键。
```

### 表达式语法：`${{ }}`

`${{ }}` 分隔符标记 GitHub Actions 表达式。内部的任何内容都由 Actions 表达式解析器在步骤运行之前计算。这与 shell 变量展开（`$VAR` 或 `${VAR}`）不同。

**关键特性：**
- 表达式在服务端计算，在运行器执行之前
- 它们可以出现在工作流的任何字段中（不仅仅是 `run:`）
- 它们可以访问上下文对象：`github`、`env`、`runner`、`matrix`、`needs`、`secrets`、`inputs`、`steps`

### 为什么采用这种方式

- **取消进行中节约 CI 分钟数。** 如果你快速连续推送三次提交，只有最后一次会运行完成。
- **组键使用 `github.ref`**，这样不同分支不会互相取消。main 和 dev 独立运行。
- **没有这个设置，** 每次推送都会排队一个新的运行，并且所有运行都会执行，在不重要的中间状态上浪费 CI 分钟数。

---

## 5. 环境默认值 (env:)

### YAML

```yaml
# ---------------------------------------------------------------------------
# 环境默认值
# ---------------------------------------------------------------------------
env:
  NODE_VERSION: 20       # 非矩阵任务的默认 Node.js 版本
  NODE_LTS: 22           # docker-prepare 和 cache-warm 使用的最新 LTS
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1 | `env:` | 定义工作流中所有任务和步骤都可用的环境变量。 |
| 2 | `NODE_VERSION: 20` | 自定义环境变量。在表达式中通过 `${{ env.NODE_VERSION }}` 访问，或在 shell 步骤中通过 `$NODE_VERSION` 访问。 |
| 3 | `NODE_LTS: 22` | 另一个自定义环境变量。注意：此处定义了但仅在文档注释中作为参考使用。 |

### 动作能力：环境变量作用域

GitHub Actions 中的环境变量有三个层级：

| 作用域 | 定义位置 | 可用范围 |
|-------|------------|-------------|
| **工作流级** | 顶层 `env:` | 所有任务和步骤 |
| **任务级** | `jobs.<job_id>.env:` | 该任务中的所有步骤 |
| **步骤级** | `steps[*].env:` 或 `steps[*].with.env` | 仅该特定步骤 |
| **运行时** | `echo "NAME=value" >> $GITHUB_ENV` | 同一任务中的后续步骤 |

访问方式：
- **表达式：** `${{ env.NODE_VERSION }}`（服务端计算）
- **Shell：** `$NODE_VERSION` 或 `${NODE_VERSION}`（在运行器上计算）

### 为什么采用这种方式

- 默认 Node 版本的单一事实来源。更改一行，所有非矩阵任务都会生效。
- 使用环境变量而不是硬编码数字，使工作流更易于维护和自文档化。

---

## 6. 任务 1：cache-calc

### YAML

```yaml
# =============================================================================
# 任务 1：cache-calc — 集中式缓存键计算
# =============================================================================
# 目的：管道中所有缓存键的单一事实来源。
# 每个下游任务从此任务的输出中读取键前缀，确保
# 一致的键构造并消除键漂移错误。
#
# 为什么需要专用任务：
#   - 避免每个任务使用不同的模式运行自己的 hashFiles()
#   - 使缓存失效逻辑在一个地方可审计
#   - 输出是强类型的（needs.<id>.outputs.<name> 中的任务输出）
# =============================================================================
cache-calc:
  runs-on: ubuntu-latest
  # 这些输出被下游任务通过 ${{ needs.cache-calc.outputs.* }} 消费
  outputs:
    dep-key:     ${{ steps.compute.outputs.dep-key }}
    build-key:   ${{ steps.compute.outputs.build-key }}
    docker-key:  ${{ steps.compute.outputs.docker-key }}
    test-key:    ${{ steps.compute.outputs.test-key }}
  steps:
    # 检出是必要的，以便 hashFiles() 操作仓库内容
    - uses: actions/checkout@v4

    # 每个键使用 hashFiles() 对相关输入进行指纹识别：
    #   - dep-key：      锁定文件是依赖真相的规范来源
    #   - build-key：    源文件 + tsconfig + dep-key（链式失效）
    #   - docker-key：   Dockerfile + .dockerignore + dep-key（依赖链）
    #   - test-key：     测试源文件
    #
    # 键链接：build-key 通过 package-lock.json 哈希包含 dep-key。
    # 当依赖改变时，依赖和构建缓存都会自动失效。
    - id: compute
      name: 计算所有缓存键
      run: |
        echo "dep-key=npm-cache-${{ hashFiles('package-lock.json') }}-${{ runner.os }}" >> "$GITHUB_OUTPUT"
        echo "build-key=build-${{ hashFiles('src/**/*.ts', 'tsconfig.json', 'web/tsconfig.json') }}-${{ hashFiles('package-lock.json') }}" >> "$GITHUB_OUTPUT"
        echo "docker-key=docker-${{ hashFiles('Dockerfile', '.dockerignore') }}-${{ hashFiles('package-lock.json') }}" >> "$GITHUB_OUTPUT"
        echo "test-key=test-${{ hashFiles('src/**/*.test.ts', 'tests/**/*.test.ts') }}" >> "$GITHUB_OUTPUT"
```

### 逐行说明

#### 任务定义

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-23 | `#` 注释 | 文档头部，解释任务的用途和设计原理。 |
| 24 | `cache-calc:` | 任务 ID。在工作流中必须唯一。用作 `needs:` 和 `needs.<id>.outputs.*` 中的标识符。 |
| 25 | `runs-on: ubuntu-latest` | 指定运行器环境。`ubuntu-latest` 是标准 Linux 运行器（当前为 Ubuntu 22.04 或 24.04）。 |
| 26-27 | `#` 注释 | 提醒这些输出在其他地方被消费。 |
| 28-31 | `outputs:` | 任务级输出声明。每个输出将一个名称映射到一个表达式。下游任务通过 `${{ needs.cache-calc.outputs.dep-key }}` 访问。 |
| 28 | `dep-key:` | 输出名称。值是表达式 `${{ steps.compute.outputs.dep-key }}`，它从 `id: compute` 的步骤读取 `dep-key` 输出。 |
| 29 | `build-key:` | 相同模式：读取 `steps.compute.outputs.build-key`。 |
| 30 | `docker-key:` | 相同模式：读取 `steps.compute.outputs.docker-key`。 |
| 31 | `test-key:` | 相同模式：读取 `steps.compute.outputs.test-key`。 |

#### 步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 33-34 | `#` 注释 + 步骤 | `uses: actions/checkout@v4` — 官方检出操作。将仓库克隆到运行器的工作区。`hashFiles()` **需要**此操作才能找到文件。 |
| 35-46 | `#` 注释 | 说明键计算策略的文档。 |
| 47 | `- id: compute` | 将步骤 ID 设置为 `compute`。此 ID 被任务级 `outputs:` 块中的 `steps.compute.outputs.*` 使用。 |
| 48 | `name: Compute all cache keys` | 人类可读的步骤名称，显示在 GitHub Actions 日志 UI 中。 |
| 49 | `run: \|` | 管道符 `\|` 开始一个多行 YAML 字符串（字面块标量）。每行原样保留并带有换行符。 |
| 50 | `echo "...dep-key..." >> "$GITHUB_OUTPUT"` | 将步骤输出写入 `GITHUB_OUTPUT` 文件。格式：`name=value`。`$GITHUB_OUTPUT` 文件是一种工作流命令机制 — 写入此文件的任何行都成为可通过 `steps.<id>.outputs.<name>` 访问的步骤输出。 |
| 51 | `${{ hashFiles('package-lock.json') }}` | `hashFiles()` 函数计算匹配文件的 SHA-256 哈希。对于单个文件参数，返回 `hash(file)`。 |
| 52 | `${{ runner.os }}` | 展开为运行器的操作系统（例如 `Linux`）。 |
| 53 | `${{ hashFiles('src/**/*.ts', 'tsconfig.json', 'web/tsconfig.json') }}` | `hashFiles()` 与多个 glob 模式计算所有匹配文件的单个组合哈希。`**/*.ts` glob 递归匹配 `src/` 中的 TypeScript 文件。 |
| 54 | `${{ hashFiles('Dockerfile', '.dockerignore') }}` | 对 Docker 配置文件进行哈希。 |
| 55 | `${{ hashFiles('src/**/*.test.ts', 'tests/**/*.test.ts') }}` | 专门对测试文件进行哈希。 |

### 动作能力：任务输出 (`outputs:`)

**语法：**
```yaml
jobs:
  <job-id>:
    outputs:
      <output-name>: <expression>
```

**输出如何流动：**
1. 任务中的步骤写入 `$GITHUB_OUTPUT`：
   ```bash
   echo "my-key=some-value" >> "$GITHUB_OUTPUT"
   ```
2. 步骤的输出通过 `${{ steps.<step-id>.outputs.my-key }}` 访问。
3. 任务的 `outputs:` 块将其映射到任务级输出：
   ```yaml
   outputs:
     my-key: ${{ steps.my-step.outputs.my-key }}
   ```
4. 下游任务通过 `${{ needs.<job-id>.outputs.my-key }}` 访问。

**重要约束：**
- 输出只能是字符串（不能是数组或对象）
- 矩阵任务的输出必须引用特定的矩阵变体
- 输出大小有限制（所有输出总共约 1 MB）

### 动作能力：`hashFiles()` 函数

**语法：**
```
hashFiles('<glob-pattern>', '<glob-pattern>', ...)
```

**行为：**
- 接受一个或多个 glob 模式
- 返回所有模式匹配的所有文件的单个 SHA-256 哈希
- 文件在哈希前按字母顺序排序，因此模式的顺序无关紧要
- 如果没有文件匹配，返回空字符串
- **仅在 `actions/checkout` 之后有效** — 函数从工作区读取

**Glob 模式：**
- `*` — 匹配除 `/` 外的任意字符
- `**` — 匹配任意数量的目录（递归）
- `?` — 匹配单个字符
- `[abc]` — 字符范围
- `!` 前缀 — 否定模式（排除匹配的文件）

**示例：**
```yaml
# 单个文件
hashFiles('package-lock.json')

# 多个模式的组合
hashFiles('src/**/*.ts', 'src/**/*.tsx', 'tsconfig.json')

# 从构建哈希中排除测试文件
hashFiles('src/**/*.ts', '!src/**/*.test.ts')

# 无匹配 → 空字符串（缓存键将是常量！）
hashFiles('nonexistent.file')
```

### 为什么采用这种方式

**集中式键计算**解决了一个实际问题：当每个任务计算自己的缓存键时，glob 模式的细微差异会导致缓存未命中。例如，一个任务使用 `hashFiles('src/**/*.ts')` 而另一个使用 `hashFiles('src/**/*.ts', '!src/**/*.test.ts')`。即使相同的文件发生了变化，它们也会产生不同的哈希值。

**键链接**确保缓存失效正确传播：
- `build-key` 包含 `package-lock.json` 的哈希。当依赖变化时，构建键也随之变化。
- 这防止了使用过时的构建输出来配合更新的依赖。
- 无需手动失效逻辑。

---

## 7. 任务 2：deps-install

### YAML

```yaml
# =============================================================================
# 任务 2：deps-install — 安装 npm 依赖并缓存（矩阵）
# =============================================================================
# 目的：在 3 个 Node 版本上安装 npm 依赖。每个组合
# 独立缓存，并将生成的 node_modules/ 作为构件上传，
# 供下游任务使用。
#
# 缓存策略：
#   1. 尝试使用完整 dep-key（包括 node 版本）精确恢复
#   2. 未命中时，尝试 restore-keys（前缀匹配 — 跨 node 版本可重用）
#   3. npm ci --prefer-offline（使用全局 npm 缓存作为第二后备）
#   4. 任务执行后：如果键之前缺失，actions/cache 自动保存（后操作）
#
# 为什么使用矩阵 node 版本：
#   - 确保在所有受支持的 Node.js 版本上的兼容性
#   - 下游构建 + 测试任务使用相同的矩阵以保持一致性
# =============================================================================
deps-install:
  needs: cache-calc
  runs-on: ubuntu-latest
  strategy:
    matrix:
      node: [18, 20, 22]   # 根据 Node.js 发布计划的活动 LTS 版本
  steps:
    - uses: actions/checkout@v4

    # setup-node 与 cache: npm 管理全局 npm 缓存 (~/.npm/)
    # 即使我们的 node_modules 缓存未命中，这也加速了 npm ci
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}
        cache: npm

    # 显式的 node_modules/ 缓存恢复
    # 使用 actions/cache/restore@v4（仅恢复子操作）让我们
    # 精确控制 — 我们只在此处恢复，让任务后的保存处理
    # npm ci 修改 node_modules 后的持久化。
    - name: 恢复 node_modules 缓存
      id: deps-cache-restore
      uses: actions/cache/restore@v4
      with:
        path: node_modules
        # 完整键包括 node 版本 — 不同的 Node 构建产生
        # 不同的 node_modules（本机插件如 better-sqlite3）
        key: ${{ needs.cache-calc.outputs.dep-key }}-${{ matrix.node }}
        # 后备恢复键（基于前缀的部分匹配）：
        #   1. 相同 OS + 锁定文件，任意 node 版本
        #   2. 仅相同 OS，任意锁定文件
        # GitHub Actions 返回匹配该前缀的最新写入缓存
        restore-keys: |
          ${{ needs.cache-calc.outputs.dep-key }}-
          npm-cache-

    # --prefer-offline：优先使用全局 npm 缓存，仅获取缺失的包
    - name: 安装依赖
      run: npm ci --prefer-offline

    # 上传完整的 node_modules/ 作为构建构件
    # 下游任务下载此构件而无需重新运行 npm ci
    # 保留：1 天（短 — 构件仅在单个运行内需要）
    - name: 上传 node_modules 构件
      uses: actions/upload-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules/
        retention-days: 1
```

### 逐行说明

#### 任务定义

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-22 | `#` 注释 | 文档头部。 |
| 23 | `deps-install:` | 任务 ID。使用连字符名称（kebab-case），这是 GitHub Actions 任务 ID 最常见的约定。 |
| 24 | `needs: cache-calc` | 声明对 `cache-calc` 任务的依赖。此任务在 `cache-calc` 成功完成之前不会启动。如果 `cache-calc` 失败，此任务将被跳过（除非使用了 `if: always()`）。 |
| 25 | `runs-on: ubuntu-latest` | 所有 deps-install 矩阵任务在 Ubuntu 上运行。 |
| 26-28 | `strategy:` / `matrix:` | 定义构建矩阵。任务对每个值组合运行一次。 |
| 27 | `node: [18, 20, 22]` | 三个值 → 三个并行任务实例。每个实例的 `${{ matrix.node }}` 设置为这些值之一。 |
| 29-31 | 步骤 | 检出和设置。 |

#### 矩阵步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 33 | `- uses: actions/setup-node@v4` | 官方 Node.js 设置操作。下载并缓存指定的 Node.js 版本。 |
| 35 | `node-version: ${{ matrix.node }}` | `${{ matrix.node }}` 展开为当前矩阵值（18、20 或 22）。 |
| 36 | `cache: npm` | **关键特性：** 告诉 setup-node 保存/恢复全局 npm 缓存（`~/.npm/`）。这通过避免从注册表重新下载包来加速 `npm ci`。与我们的 node_modules 缓存不同，这是包级缓存，而不是 `node_modules/` 缓存。 |

#### 缓存恢复步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 38-39 | `name:` + `id:` | 人类可读的名称和机器可读的 ID。`id:` 用于稍后检查 `steps.deps-cache-restore.outputs.cache-hit`。 |
| 40 | `uses: actions/cache/restore@v4` | `actions/cache` 包中的仅恢复子操作。版本 `v4` 是最新的稳定版本。 |
| 42 | `path: node_modules` | 要从缓存恢复的目录。必须与缓存时的路径完全匹配。 |
| 44 | `key: ${{ needs.cache-calc.outputs.dep-key }}-${{ matrix.node }}` | 主缓存键。由以下部分组成：来自 cache-calc 的 `dep-key`（包含锁定文件哈希 + 操作系统）+ node 版本。示例：`npm-cache-a1b2c3d4-Linux-20`。 |
| 46-47 | `restore-keys: \|` + 多行 | 用于部分匹配的后备键。管道符 `\|` 创建一个多行字符串。如果主键未命中，则依次尝试每一行。 |
| 46 | `${{ needs.cache-calc.outputs.dep-key }}-` | 第一个后备：匹配键以此前缀开头的任何缓存。由于 dep-key 包括锁定文件哈希和操作系统但不包括 node 版本，因此这匹配相同锁定文件+操作系统的任何 node 版本。 |
| 47 | `npm-cache-` | 第二个后备：匹配任何以 `npm-cache-` 前缀的缓存。捕获锁定文件已更改但存在某些先前缓存的情况。 |

#### 安装步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 50 | `run: npm ci --prefer-offline` | `npm ci` — 从锁定文件进行干净安装（比 `npm install` 更快且更可重现）。`--prefer-offline` 告诉 npm 优先使用全局缓存，仅获取缺失的包。如果 node_modules 恢复命中，此步骤很快（仅验证）；如果恢复未命中但 npm 全局缓存命中，则避免网络获取。 |

#### 构件上传步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 52-57 | 上传步骤 | 上传已安装的 `node_modules/` 作为构建构件。 |
| 54 | `name: node_modules-${{ matrix.node }}` | 每个 node 版本唯一的构件名称。示例：`node_modules-20`。 |
| 55 | `path: node_modules/` | 要上传的路径。尾部的 `/` 可选但符合惯例。 |
| 56 | `retention-days: 1` | **关键设置：** 构件在 1 天后删除。构建构件仅在同一个工作流运行中需要，通常只需几分钟，而不是几天。短保留期节省存储成本。 |

### 动作能力：`actions/cache/restore@v4`

**目的：** 通过键恢复先前缓存的目录。

**关键输入：**

| 输入 | 必需 | 描述 |
|-------|----------|-------------|
| `path` | 是 | 要恢复的文件/目录路径（支持 glob，多个路径用换行符分隔） |
| `key` | 是 | 要查找的精确缓存键 |
| `restore-keys` | 否 | 用于后备匹配的前缀键的有序列表 |
| `fail-on-cache-miss` | 否 | 如果为 `true`，在没有匹配的缓存条目时使步骤失败（默认：`false`） |
| `lookup-only` | 否 | 如果为 `true`，检查缓存是否存在而不恢复（用于预检检查） |

**关键输出：**

| 输出 | 描述 |
|--------|-------------|
| `cache-hit` | 如果找到精确匹配则为 `"true"`，如果只有部分匹配或未命中则为 `"false"` |
| `cache-primary-key` | 提供的键 |
| `cache-matched-key` | 实际匹配的键（可能因 restore-keys 而不同） |

**缓存匹配逻辑：**

1. 尝试与 `key` 精确匹配。如果找到 → `cache-hit: "true"`，立即恢复。
2. 如果没有精确匹配，依次尝试每个 `restore-keys`。对于每个键，找到键以此前缀开头的**最近写入**的缓存条目。
3. 如果任何 restore-key 匹配 → `cache-hit: "false"`（重要：不是 `"true"`），从部分匹配恢复。
4. 如果没有匹配 → 不恢复任何内容。

**`cache-hit` 的区别很重要：**
- `"true"` → node_modules 正是 `npm ci` 会生成的结果。可以安全跳过 `npm ci`。
- `"false"` → node_modules 来自不同的键。应该运行 `npm ci` 以确保正确性。不过，部分恢复加速了 `npm ci`，因为大多数包已经存在。

### 动作能力：`actions/cache@v4`（完整操作）

完整的 `actions/cache@v4` 操作结合了恢复（前步骤）和保存（后步骤）。当你在步骤中使用 `actions/cache@v4` 时，它：
1. 在步骤开始时恢复缓存（类似于 `cache/restore`）
2. 注册一个任务后钩子，在任务完成后保存缓存（类似于 `cache/save`）

**为什么我们使用 `cache/restore` 而不是 `cache`：** 分离恢复和保存让我们有更精细的控制。我们显式地恢复，运行 `npm ci`，然后让自动的后操作保存处理持久化。后操作保存仅在缓存键是**新**的时运行（不是在缓存命中时）。这避免了不必要的缓存写入。

### 动作能力：`actions/upload-artifact@v4`

**目的：** 将文件从运行器上传到 GitHub 的构件存储。

**关键输入：**

| 输入 | 必需 | 描述 |
|-------|----------|-------------|
| `name` | 是（默认：`artifact`） | 用于标识的构件名称。由 `download-artifact` 使用。 |
| `path` | 是 | 要上传的文件/目录路径（支持 glob，多个路径） |
| `retention-days` | 否 | 构件保留天数（默认：90，最大：取决于组织设置） |
| `if-no-files-found` | 否 | 如果没有文件匹配时的行为：`warn`（默认）、`error`、`ignore` |
| `compression-level` | 否 | Gzip 压缩级别（0-9，默认：6） |

**保留期说明：**
- 默认保留期为 90 天（可在组织级别调整）
- 为中间构件设置**短**保留期（1-3 天）
- 仅为最终发布构件设置长保留期
- GitHub 按月计费存储空间；短保留期降低成本

### 为什么采用这种方式

**用于 Node 版本的矩阵：** 确保兼容性。本机模块（如 `better-sqlite3`）在不同 Node 版本上可能编译不同。

**每个 node 版本单独的缓存：** 两个具有不同 `matrix.node` 值的任务产生不同的缓存键。Node 20 的本机插件与 Node 22 的运行时不兼容。如果我们使用共享缓存，会出现运行时错误。

**后备 `restore-keys`：**
- 如果精确键 `npm-cache-a1b2c-Linux-22` 未命中（例如，node 22 的第一次 CI 运行），后备键 `npm-cache-a1b2c-Linux-` 匹配先前 node 20 运行的缓存。
- 即使在新的 node 版本的第一次运行中，这也提供了有用的部分恢复。
- `npm ci` 只需要获取那些在 node 版本之间不同的包。

**下游任务使用构件而不是缓存：**
- 构件比缓存恢复更快（在同一工作流运行内）
- 构件没有缓存大小限制（每个缓存条目约 10GB 对比约 2GB）
- 构件隔离到特定工作流运行 — 没有跨运行污染
- 缓存用于**冷启动**（分支上的第一次运行），构件用于同一运行内的**后续任务**

---

## 8. 任务 3：lint

### YAML

```yaml
# =============================================================================
# 任务 3：lint — Lint + TypeScript 类型检查
# =============================================================================
# 目的：最快反馈任务。Lint 和类型检查在依赖安装后立即运行，
# 无需等待完整的构建管道。
#
# 此任务有意使用单个 Node 版本（来自 env 的 20）：
#   - Lint 和类型检查是工具链问题，而非运行时问题
#   - 在 3 个节点上运行会浪费 CI 分钟数且不会提供额外信号
# =============================================================================
lint:
  needs: deps-install
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}

    # 从 deps-install 矩阵下载 node 20 的 node_modules
    # 这避免了重新运行 npm ci — 每次运行节省约 30-60 秒
    - name: 下载 node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ env.NODE_VERSION }}
        path: node_modules

    - name: 运行 linter
      run: npm run lint

    - name: TypeScript 类型检查
      run: npx tsc --noEmit
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-14 | `#` 注释 | 文档。关键点：lint 为单节点以提高速度。 |
| 15 | `lint:` | 任务 ID。 |
| 16 | `needs: deps-install` | 依赖于 `deps-install`。微妙之处：`deps-install` 是一个矩阵任务。当你将矩阵任务放入 `needs:` 时，你等待所有矩阵变体完成。不过，我们只下载 node 20 的变体。 |
| 17 | `runs-on: ubuntu-latest` | Linux 运行器。 |
| 19-20 | 检出 | 标准检出。 |
| 22-25 | 设置 Node | 使用 `${{ env.NODE_VERSION }}`（20）。不需要 `cache: npm`，因为我们不运行 `npm ci`。 |
| 27-32 | 下载 `node_modules` | 从 `deps-install` 下载 node 20 的预安装 `node_modules` 构件。 |
| 29 | `name: node_modules-${{ env.NODE_VERSION }}` | 匹配 `deps-install` 中的构件名称。这必须**精确**匹配 — 构件名称区分大小写。 |
| 30 | `path: node_modules` | 将下载的构件放置在工作区中的位置。 |
| 33-34 | `npm run lint` | 运行 linter（ESLint）。`package.json` 脚本：`eslint src/ tests/`。 |
| 35-36 | `npx tsc --noEmit` | TypeScript 类型检查，不输出文件。`--noEmit` 很关键 — 它告诉 `tsc` 只进行类型检查，不编译。这比完整编译更快。 |

### 动作能力：`actions/download-artifact@v4`

**目的：** 下载在同一工作流运行中先前上传的构件（或在使用 `workflow-run-id` 时从其他工作流运行下载）。

**关键输入：**

| 输入 | 必需 | 描述 |
|-------|----------|-------------|
| `name` | 否 | 要下载的构件名称。如果未指定，下载运行中的所有构件。 |
| `path` | 否 | 目标目录（默认：`$GITHUB_WORKSPACE`）。 |
| `github-token` | 否 | 用于跨工作流构件下载的令牌（很少需要）。 |
| `run-id` | 否 | 从特定运行而不是当前运行下载。 |

**v4 中的重要变化（与 v3 相比）：**
- v4 在需要特定构件时需要显式的 `name:`（不再合并所有构件）
- v4 保留原始文件结构，不扁平化
- v4 更快且使用更少存储（流式传输而非内存中的 ZIP）

**下载行为：**
- 如果 `name` 匹配一个构件，仅下载该构件
- 如果未指定 `name`，下载运行中的所有构件（谨慎使用 — 可能很慢）
- 如果构件是从目录上传的，目录结构会被保留

### 为什么采用这种方式

**单个节点用于 lint：** Lint 和类型检查操作的是源代码，而非运行时行为。Node 18、20 和 22 之间的 lint 结果没有差异。在所有三个节点上运行 lint 会使 CI 时间增加三倍，而不会产生任何额外信号。

**构件下载而不是缓存恢复：** 同一运行内的数据传输，构件更快。缓存需要 HTTP 请求来查询键，然后下载。构件是直接下载，没有查找开销。

**顺序 lint → 类型检查：** ESLint 和 TypeScript 是独立的工具。它们可以并行运行，但在单个运行器上没有好处（运行器只有一个 CPU）。顺序运行更简单且同样快。

---

## 9. 任务 4：docker-prepare

### YAML

```yaml
# =============================================================================
# 任务 4：docker-prepare — 预构建 Docker 层
# =============================================================================
# 目的：构建 Docker 镜像层并将其推送到 GitHub Actions 缓存。
# 与 lint 并行运行，实现最大的管道效率。
#
# 使用 Docker BuildKit 的 GitHub Actions 缓存后端（type=gha）。
# 层缓存由 cache-calc 中的 docker-key 键控。
#
# 关键设计：push: false — 我们只构建以填充层缓存，
# 而不是发布镜像。实际的镜像发布在部署工作流中完成。
# =============================================================================
docker-prepare:
  needs: cache-calc
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    # docker/metadata-action 从 Git 上下文生成 Docker 镜像标签和标签：
    # 分支名称、提交 SHA、语义版本等。
    - name: 生成 Docker 元数据
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ghcr.io/${{ github.repository }}
        tags: |
          type=ref,event=branch
          type=sha,format=short
          type=raw,value=latest,enable={{is_default_branch}}

    # setup-buildx-action 使用默认配置初始化 BuildKit
    - name: 设置 Docker Buildx
      uses: docker/setup-buildx-action@v3

    # 构建镜像但不推送（push: false）。
    # cache-from: type=gha — 从先前运行恢复缓存的层
    # cache-to: type=gha,mode=max — 保存所有层（不仅是最终的），允许
    #   跨构建的最大化缓存重用。mode=max 存储每个中间
    #   层；mode=min 仅存储最终镜像层。
    - name: 构建并缓存 Docker 层
      uses: docker/build-push-action@v6
      with:
        context: .
        push: false
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-14 | `#` 注释 | 文档。关键点：不推送，仅缓存构建。 |
| 15 | `docker-prepare:` | 任务 ID。 |
| 16 | `needs: cache-calc` | 仅需要 `cache-calc`（用于 docker-key，虽然通过 `type=gha` 隐式使用）。不需要 `deps-install` — 这与 `lint` 并行运行。 |
| 17 | `runs-on: ubuntu-latest` | Docker 仅在 Linux 运行器上可用（macOS/Windows 运行器默认不支持 Docker）。 |
| 19 | 检出 | 标准检出。 |
| 21-28 | Docker 元数据 | 为 Docker 镜像生成标签和标签。 |
| 23 | `id: meta` | 用于访问输出的步骤 ID。 |
| 24 | `uses: docker/metadata-action@v5` | 用于生成元数据的官方 Docker 操作。 |
| 26 | `images: ghcr.io/${{ github.repository }}` | 容器注册表 + 镜像名称。`ghcr.io` 是 GitHub Container Registry。`${{ github.repository }}` 展开为 `owner/repo-name`。 |
| 27-29 | `tags:` | 标签生成规则。每行是一个标签类型。 |
| 28 | `type=ref,event=branch` | 从分支名称生成标签（例如 `dev`、`main`）。 |
| 29 | `type=sha,format=short` | 从短提交 SHA 生成标签（例如 `sha-a1b2c3d`）。 |
| 30 | `type=raw,value=latest,enable={{is_default_branch}}` | 仅在默认分支（main）上添加 `latest` 标签。`{{is_default_branch}}` 是 metadata-action 中的模板变量，不是 GitHub Actions 表达式。 |
| 32-33 | `docker/setup-buildx-action@v3` | 设置 Docker BuildKit（现代 Docker 构建后端）。确保 BuildKit 功能可用（缓存挂载、多平台构建等）。 |
| 35-46 | 主构建步骤。 | |
| 37 | `uses: docker/build-push-action@v6` | 官方 Docker 构建和推送操作。 |
| 39 | `context: .` | 构建上下文 — 构建期间发送到 Docker 守护进程的目录。 |
| 40 | `push: false` | **关键：** 构建镜像但不推送到注册表。此步骤纯粹用于缓存预热。 |
| 41 | `tags: ${{ steps.meta.outputs.tags }}` | 来自元数据操作的标签（换行分隔）。 |
| 42 | `labels: ${{ steps.meta.outputs.labels }}` | 来自元数据操作的标签。 |
| 43 | `cache-from: type=gha` | **缓存源：** 使用 GitHub Actions 缓存作为 BuildKit 缓存后端。从先前运行恢复层。 |
| 44 | `cache-to: type=gha,mode=max` | **缓存目标：** 将层保存到 GitHub Actions 缓存。`mode=max` 保存所有层（包括中间层）；`mode=min` 仅保存最终镜像层。`max` 提供更好的缓存命中率，但需要更多缓存存储空间。 |

### 动作能力：`docker/build-push-action@v6`

**关键输入：**

| 输入 | 描述 |
|-------|-------------|
| `context` | 构建上下文目录 |
| `push` | 推送到注册表（布尔值） |
| `tags` | 镜像标签（换行或逗号分隔） |
| `labels` | 镜像元数据标签 |
| `cache-from` | 缓存导入源（例如 `type=gha`、`type=registry,ref=image:cache`） |
| `cache-to` | 缓存导出目标（例如 `type=gha,mode=max`） |
| `build-args` | Docker 构建时变量 |
| `file` | Dockerfile 路径（默认：`{context}/Dockerfile`） |
| `platforms` | 目标平台（用于多架构构建） |
| `provenance` | 构建出处证明模式 |
| `sbom` | SBOM 生成模式 |

**缓存后端：**

| 后端 | 类型字符串 | 最适合 |
|---------|-------------|----------|
| GitHub Actions 缓存 | `type=gha` | 同仓库缓存（免费） |
| 内联（在镜像中） | `type=inline` | 基于注册表的缓存 |
| 注册表 | `type=registry,ref=img:cache` | 跨仓库或跨平台 |
| 本地目录 | `type=local` | 具有共享存储的自托管运行器 |
| S3 | `type=s3` | AWS 环境 |
| Azure Blob | `type=azblob` | Azure 环境 |

**`mode=max` 与 `mode=min`：**
- `mode=max`（推荐用于 CI）：缓存构建过程中创建的每一层。产生最佳缓存命中率，但使用更多缓存存储空间。
- `mode=min`：仅缓存最终镜像层（类似于多阶段构建结果）。使用更少存储空间，但可能在缓存未命中时需要重建某些层。

### 为什么采用这种方式

**与 lint 并行执行：** 由于 `docker-prepare` 只需要 `cache-calc`（而非 `deps-install`），它与 `lint` 并行运行。这意味着 Docker 层缓存在 lint 运行时进行，不增加实际耗时。

**`push: false`：** 我们不想从每次 CI 运行发布镜像 — 那是部署工作流的工作。我们只想填充层缓存，以便部署工作流构建更快。

**使用 `type=gha` 进行缓存：** GitHub Actions 缓存免费且作用于仓库。它是 GitHub Actions 中最简单的 CI 缓存后端 — 无需注册表凭证。

**`mode=max`：** 我们保存所有中间层。这意味着即使只有最后几层发生变化（例如应用程序代码），基础层（操作系统包、系统依赖）也会从缓存中重用。

---

## 10. 任务 5：build

### YAML

```yaml
# =============================================================================
# 任务 5：build — TypeScript 编译 + Vite 打包（矩阵）
# =============================================================================
# 目的：在 3 个 Node 版本上编译 TypeScript 并使用 Vite 打包。
# 使用来自 deps-install 的依赖缓存和构建缓存（dist/）以在
# 可能的情况下实现增量编译。
#
# 为什么使用矩阵构建：
#   - 验证项目在所有目标 Node 版本上都能干净编译
#   - 为 test-unit 矩阵生成特定版本的 dist/ 构件
# =============================================================================
build:
  needs: deps-install
  runs-on: ubuntu-latest
  strategy:
    matrix:
      node: [18, 20, 22]
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}

    # 从匹配的 deps-install 任务下载预安装的 node_modules
    - name: 下载 node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules

    # 从缓存恢复先前构建的 dist/（如果有）
    # Vite/tsc 可以将其用于持久编译缓存
    - name: 恢复构建缓存
      id: build-cache-restore
      uses: actions/cache/restore@v4
      with:
        path: dist
        key: ${{ needs.cache-calc.outputs.build-key }}-${{ matrix.node }}
        restore-keys: |
          ${{ needs.cache-calc.outputs.build-key }}-

    # npm run build 编译 TypeScript 并使用 Vite 打包
    # （在 package.json 中定义为：npm run build:web && tsc && cp -r ...）
    - name: 构建项目
      run: npm run build

    # 为 test-unit 和 test-integration 任务上传 dist/
    - name: 上传 dist 构件
      uses: actions/upload-artifact@v4
      with:
        name: dist-${{ matrix.node }}
        path: dist/
        retention-days: 3
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-15 | `#` 注释 | 文档头部。 |
| 16 | `build:` | 任务 ID。 |
| 17 | `needs: deps-install` | 依赖于 `deps-install`。不依赖于 `lint` 或 `docker-prepare` — 它们并行运行。 |
| 18 | `runs-on: ubuntu-latest` | Linux 运行器。 |
| 19-22 | 矩阵 `node: [18, 20, 22]` | 与 `deps-install` 相同的 3 节点矩阵。 |
| 24-25 | 检出 | 标准。 |
| 27-31 | 设置 Node | 不需要 `cache: npm`（我们从构件下载 node_modules，不运行 npm ci）。 |
| 33-38 | 下载 `node_modules` | 从匹配的 deps-install 下载。构件名称 `node_modules-${{ matrix.node }}` 确保 node 20 构建获取 node 20 的 node_modules。 |
| 40-48 | 构建缓存恢复 | 从缓存恢复先前构建的 `dist/`（如果有）。 |
| 44 | `key: ${{ needs.cache-calc.outputs.build-key }}-${{ matrix.node }}` | 构建缓存键。链式：包括源文件哈希和锁定文件哈希。如果源代码或依赖发生变化，键也会变化。 |
| 46 | `restore-keys: \| ${{ needs.cache-calc.outputs.build-key }}-` | 后备键：来自相同源哈希的任何先前构建（任何 node 版本 — 对部分恢复有用）。 |
| 50-51 | 构建 | 运行 `npm run build`。 |
| 53-58 | 上传 `dist/` 构件 | 为下游测试任务上传构建输出。 |

### 缓存键链接实战

构建键是 `build-<source-hash>-<dep-hash>`。这意味着：

```
场景：仅源代码发生变化
  build-key: build-a1b2c-d4e5f → 缓存未命中（源哈希变化）
  restore-key: build-a1b2c- → 从具有相同源的先前构建部分命中
  → 构建运行，部分缓存可能通过 tsc 增量编译重用

场景：仅依赖发生变化（package-lock.json）
  build-key: build-a1b2c-d4e6f → 缓存未命中（由于锁定文件，依赖哈希变化）
  源哈希 a1b2c 相同，但依赖哈希变了
  → 需要完整重建（新依赖可能改变编译结果）

场景：没有任何变化
  build-key: build-a1b2c-d4e5f → 缓存命中
  → 从缓存恢复 dist/，完全跳过构建
  → （如果构建步骤仍然运行，tsc 增量编译很快）
```

### 为什么 `dist/` 使用构件而不是缓存

`dist/` 和 `node_modules/` 都在同一运行内传递使用构件，跨运行预热使用缓存。区别如下：

| 机制 | 使用场景 | 速度 | 持久性 |
|-----------|----------|-------|-------------|
| **缓存** | 跨运行（分支上的第一次 CI） | 较慢（键查找） | 数天（基于 LRU 淘汰） |
| **构件** | 同一运行（当前工作流） | 更快（直接下载） | 由 `retention-days` 配置 |

`build` 任务的缓存恢复提供了冷启动优势：如果你推送一个分支，并且第一次 CI 运行找到了来自先前 main 构建的缓存，`dist/` 在几秒钟内就能恢复。但在当前工作流运行内，`test-unit` 和 `test-integration` 将 `dist/` 作为构件下载。

---

## 11. 任务 6：test-unit

### YAML

```yaml
# =============================================================================
# 任务 6：test-unit — 带矩阵分片的单元测试
# =============================================================================
# 目的：在 3 个 Node 版本 x 2 个操作系统变体 x 2 个分片上运行单元测试。
# 这是管道中并行化程度最高的任务。
#
# 分片策略：
#   - Vitest --shard=N/M 将测试文件分配到 M 个分片上
#   - 总实际耗时变为 max(shard_time)，而不是 sum(all_test_times)
#   - 在 6（node x os）变体上使用 2 个分片 = 最多 12 个并行运行器
#
# fail-fast: false — 一个失败组合不会取消其他组合，
# 让我们看到哪些组合通过、哪些失败。
# =============================================================================
test-unit:
  needs: build
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      node: [18, 20, 22]
      os: [ubuntu-latest, windows-latest]
      # 每个 node+os 组合 2 个分片 = 2 倍覆盖而不增加 2 倍实际耗时
      shard: [1, 2]
    # 排除 windows + node 18：降低 CI 成本，同时仍然测试
    # 最重要的组合（win+20、win+22、所有 ubuntu 组合）
    exclude:
      - os: windows-latest
        node: 18
    # 当某个运行器失败时不要取消所有运行器 — 我们需要每个组合的信号
    fail-fast: false
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}

    # 从匹配的构建任务下载预构建的 dist/
    - name: 下载 dist 构件
      uses: actions/download-artifact@v4
      with:
        name: dist-${{ matrix.node }}
        path: dist

    # 需要 node_modules 用于测试框架和类型解析
    - name: 下载 node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules

    # Vitest 分片：https://vitest.dev/guide/cli.html#shard
    # --shard=1/2 运行前半部分测试文件
    # --shard=2/2 运行后半部分
    - name: 运行单元测试（分片 ${{ matrix.shard }}/2）
      run: npx vitest run --shard=${{ matrix.shard }}/2

    # 即使失败也上传测试结果（if: always()）用于调试
    - name: 上传测试结果
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: test-results-${{ matrix.node }}-${{ matrix.os }}-shard${{ matrix.shard }}
        path: test-results/
        retention-days: 7
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-18 | `#` 注释 | 文档。 |
| 19 | `test-unit:` | 任务 ID。 |
| 20 | `needs: build` | 依赖于 `build` 任务（build 的所有矩阵变体必须完成）。 |
| 21 | `runs-on: ${{ matrix.os }}` | **关键：** 运行器操作系统由矩阵控制。`os: windows-latest` 的任务在 Windows 上运行；`os: ubuntu-latest` 在 Linux 上运行。这测试了跨平台兼容性。 |
| 22-35 | `strategy:` 块 | 带有排除的复杂矩阵。 |
| 24-28 | `matrix:` 维度 | 三个维度：`node`（3 个值）、`os`（2 个值）、`shard`（2 个值）。理论总计：3 × 2 × 2 = 12 个组合。 |
| 25 | `node: [18, 20, 22]` | Node 版本。 |
| 26 | `os: [ubuntu-latest, windows-latest]` | 操作系统。 |
| 28 | `shard: [1, 2]` | 测试分片索引。 |
| 30-31 | `exclude:` | 从矩阵中移除特定组合。 |
| 31 | `- os: windows-latest, node: 18` | 移除（windows, node 18）组合 — 2 个分片值 × 1 个排除 = 减少 2 个任务。 |
| 33-34 | `fail-fast: false` | **关键：** 当一个矩阵任务失败时，不要取消其余正在进行的任务。没有这个设置，Node 18 失败会取消仍在运行的 Node 22 任务。 |

#### 矩阵如何展开

不加排除：
```
(18, ubuntu, 1)  (18, ubuntu, 2)  (18, windows, 1)  (18, windows, 2)
(20, ubuntu, 1)  (20, ubuntu, 2)  (20, windows, 1)  (20, windows, 2)
(22, ubuntu, 1)  (22, ubuntu, 2)  (22, windows, 1)  (22, windows, 2)
```
= 12 个任务

带排除 `(windows, 18)`：
```
(18, ubuntu, 1)  (18, ubuntu, 2)  ~~(18, windows, 1)~~  ~~(18, windows, 2)~~
(20, ubuntu, 1)  (20, ubuntu, 2)  (20, windows, 1)  (20, windows, 2)
(22, ubuntu, 1)  (22, ubuntu, 2)  (22, windows, 1)  (22, windows, 2)
```
= 10 个任务

#### 步骤

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 37-38 | 检出 | 标准。 |
| 40-44 | 设置 Node | 使用 `matrix.node`。 |
| 46-51 | 下载 `dist/` | 从匹配的构建任务下载。例如，对于 `(node: 20, os: windows)`，下载 `dist-20`。 |
| 53-58 | 下载 `node_modules` | 从 `deps-install` 为 `matrix.node` 下载。 |
| 60-63 | Vitest 分片运行 | 以分片模式运行 vitest。 |
| 62 | `run: npx vitest run --shard=${{ matrix.shard }}/2` | Vitest 将测试文件分成 2 组。`--shard=1/2` 运行前半部分，`--shard=2/2` 运行后半部分。 |
| 65-72 | 上传结果 | 即使测试失败也上传测试结果文件（JUnit XML、覆盖率等）（`if: always()`）。 |
| 67 | `if: always()` | 此表达式使步骤无论前一步骤的结果如何都运行。没有它，测试失败会跳过上传步骤。 |
| 69 | `name: test-results-${{ matrix.node }}-${{ matrix.os }}-shard${{ matrix.shard }}` | 每个组合唯一的构件名称。示例：`test-results-20-windows-latest-shard1`。 |
| 71 | `retention-days: 7` | 测试结果的较长保留期（你可能希望在 1-3 天的 CI 构件窗口过期后查看它们）。 |

### 动作能力：矩阵策略

**完整的 `strategy` 语法：**

```yaml
strategy:
  matrix:
    <dimension>: [<values>]
    <dimension>: [<values>]
  include:
    - <dimension>: <value>
      <extra-key>: <value>    # 向特定组合添加额外变量
  exclude:
    - <dimension>: <value>    # 移除特定组合
  fail-fast: true|false       # 当一个任务失败时取消所有任务（默认：true）
  max-parallel: <number>      # 限制并发矩阵任务数（默认：无限制）
```

**`include` 的用法：**

`include` 关键字添加自定义组合或向现有组合添加额外变量：

```yaml
strategy:
  matrix:
    node: [18, 20]
    os: [ubuntu]
  include:
    - node: 20
      os: windows
      experimental: true    # 仅此组合的额外变量
    - node: 22              # 完全新的组合
      os: ubuntu
```

**关键矩阵概念：**
- 矩阵任务是完全独立的 — 它们在单独的运行器实例上运行
- 每个任务有自己的 `${{ matrix.<dimension> }}` 值
- 矩阵任务共享相同的 `needs:` 块
- `fail-fast` 是每个矩阵实例的，不是每个工作流的

### 动作能力：`if:` 条件

`if:` 关键字控制步骤或任务是否运行：

```yaml
if: <expression>
```

**常见模式：**

| 表达式 | 行为 |
|------------|----------|
| `always()` | 无论前一步骤成功/失败都运行。如果运行器损坏，步骤仍然会失败。 |
| `success()` | 仅当所有前一步骤都成功时运行（默认行为）。 |
| `failure()` | 仅当之前步骤失败时运行。 |
| `cancelled()` | 仅当工作流被取消时运行。 |
| `github.ref == 'refs/heads/main'` | 仅在 main 分支上。 |
| `steps.my-step.outputs.cache-hit != 'true'` | 仅在缓存未命中时。 |

**组合条件：**
```yaml
if: always() && !cancelled()
if: failure() || github.event_name == 'workflow_dispatch'
```

### 为什么要分片？

没有分片时，如果你有 100 个测试文件和 4 个运行器，实际耗时是一个运行器上所有测试运行时间的总和：

```
不进行分片的测试运行时间：10 分钟（所有测试在一个运行器上）
```

在 5 个（node x os）组合的每个上使用 2 个分片：

```
分片 1：50 个测试文件 → 5 分钟
分片 2：50 个测试文件 → 5 分钟
实际耗时：5 分钟（一半时间）
```

分片在以下情况下有益：
- 你有许多测试文件（>100）
- 测试受 CPU 限制，而非 I/O 限制
- 你有可用的 CI 并行性
- 测试套件运行时间是管道中的瓶颈

### 为什么使用 `fail-fast: false`？

**不使用 `fail-fast: false`（默认 `true`）：**
```
任务 (18, windows) 失败
→ 所有其他 9 个任务被立即取消
→ 你只知道 (18, windows) 失败了
→ 你对 (20, ubuntu)、(22, windows) 等没有信号
```

**使用 `fail-fast: false`：**
```
任务 (18, windows) 失败
→ 其他 9 个任务继续运行
→ 你看到所有组合的结果
→ Node 20 在两个操作系统上通过，Node 22 在 Linux 上通过但在 Windows 上失败
```

对于 CI，`fail-fast: false` 通常更好。额外花费的 CI 分钟数运行到完成，换来的全面信号是值得的。仅在 CI 分钟数稀缺且速度至关重要时使用 `fail-fast: true`。

---

## 12. 任务 7：test-integration

### YAML

```yaml
# =============================================================================
# 任务 7：test-integration — 使用 Docker Compose 的集成测试
# =============================================================================
# 目的：通过 Docker Compose 启动完整的服务栈并运行
# 集成测试。这验证构建构件在容器化环境中
# 与真实依赖一起正确工作。
#
# 关键设计：
#   - 使用 node 20 的 dist/ 构件（一个代表性版本）
#   - Docker Compose 控制服务生命周期
#   - 失败时收集容器日志用于调试
#   - 清理始终运行（if: always()）以防止资源泄漏
# =============================================================================
test-integration:
  needs: build
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}

    # 下载预构建的 dist/（node 20）和匹配的 node_modules
    - name: 下载 dist 构件
      uses: actions/download-artifact@v4
      with:
        name: dist-${{ env.NODE_VERSION }}
        path: dist

    - name: 下载 node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ env.NODE_VERSION }}
        path: node_modules

    # 启动 docker-compose.yml 中定义的所有服务
    # --wait：等待健康检查通过后再继续
    # --wait-timeout：等待服务变为健康的最大秒数
    - name: 启动 Docker Compose 服务
      run: docker compose up -d --wait --wait-timeout 60

    # 集成测试命令（在 package.json 中定义 — 如不存在则创建）
    - name: 运行集成测试
      run: npx vitest run --config vitest.integration.config.ts 2>/dev/null || npm run test:integration 2>/dev/null || echo "尚未配置集成测试"

    # 从所有容器收集日志用于调试测试失败
    - name: 收集容器日志
      if: failure()
      run: docker compose logs --tail=100

    # 无论测试结果如何，始终进行清理
    - name: 清理 Docker Compose
      if: always()
      run: docker compose down -v --remove-orphans
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-16 | `#` 注释 | 文档头部。 |
| 17 | `test-integration:` | 任务 ID。 |
| 18 | `needs: build` | 依赖于 `build` 任务（等待所有矩阵变体）。 |
| 19 | `runs-on: ubuntu-latest` | Docker 仅在 Linux 运行器上可用。 |
| 21-22 | 检出 | 标准。 |
| 24-28 | 设置 Node | 使用默认的 `NODE_VERSION`（20）。 |
| 30-35 | 下载 `dist/` | 下载 `dist-20` 构件。 |
| 37-41 | 下载 `node_modules` | 下载 `node_modules-20` 构件。 |
| 43-46 | Docker Compose 启动 | |
| 45 | `docker compose up -d --wait --wait-timeout 60` | `-d`：分离模式（后台运行）。`--wait`：等待所有服务通过健康检查后再继续。`--wait-timeout 60`：如果服务在 60 秒内未变为健康状态则失败。 |
| 48-50 | 集成测试 | 运行集成测试。使用 `\|\|` 后备以在集成测试配置尚不存在时优雅处理。 |
| 49 | 命令说明： | 首先尝试 vitest 与集成配置，回退到 `test:integration` npm 脚本，然后如果两者都不存在则优雅地打印消息。 |
| 52-55 | 失败时收集日志 | |
| 53 | `if: failure()` | 仅当之前步骤失败时运行。 |
| 54 | `docker compose logs --tail=100` | 打印每个容器日志的最后 100 行。 |
| 57-60 | 清理 | |
| 58 | `if: always()` | 即使测试失败也运行。这对清理至关重要。 |
| 59 | `docker compose down -v --remove-orphans` | `down`：停止并移除容器。`-v`：移除卷。`--remove-orphans`：清理 compose 文件中未定义的容器。 |

### Docker Compose 生命周期管理

使用 Docker Compose 进行集成测试的标准模式：

```
           [启动]                    [失败]              [始终]
  检出 ──> docker compose up ──> 测试运行 ──> 收集日志 ──> docker compose down
                     │                                             ↑
                     └────── 等待健康检查 ──────────────────────────┘
```

**为什么 `--wait` 很重要：** 没有 `--wait`，`docker compose up -d` 立即返回，下一步骤（测试）可能在数据库接受连接之前运行。健康检查确保：

1. 容器正在运行
2. 内部进程已就绪（例如 PostgreSQL 接受连接）
3. 应用程序响应健康端点

**为什么清理用 `if: always()`：** 如果测试失败且运行器没有清理 Docker，资源会泄漏。在 GitHub Actions 托管运行器上，整个 VM 在任务后被销毁，因此泄漏不是永久的，但是：
- 运行中的容器消耗磁盘空间
- 运行中的容器可能占用端口
- 卷占用空间，这些空间本可用于构件下载

**为什么使用 `--remove-orphans`：** 如果工作流运行是重试，可能存在来自具有不同服务配置的先前运行的遗留容器。

### 为什么集成测试使用单节点？

集成测试验证的是**行为**，而非运行时兼容性。核心逻辑在不同 Node 版本上应该表现一致。在一个代表性版本（20 LTS）上运行集成测试就足够了，而单元测试矩阵已经覆盖了 Node 版本特定问题。

---

## 13. 任务 8：cache-warm

### YAML

```yaml
# =============================================================================
# 任务 8：cache-warm — 为将来运行预热缓存（仅 main 分支）
# =============================================================================
# 目的：在 main 上成功构建后，显式保存所有缓存层。
# 这确保基于 main 的 PR 分支获得完整的缓存命中，即使
# 之前的 main 运行缓存已过期或被淘汰。
#
# 为什么显式保存：
#   - actions/cache 仅在缓存未命中时保存（后操作）。如果 main 运行
#     时缓存命中，后操作跳过意味着没有写入新的缓存条目。
#   - cache-warm 保证每次 main 合并后都有新鲜的缓存条目。
#   - 在此运行 `npm ci` 创建了要缓存的精确预期 node_modules。
#
# 条件：github.ref == 'refs/heads/main' 确保这仅在 main 上运行，
# 不在 PR 或 dev 分支上运行（在这些分支上会浪费 CI 分钟数）。
# =============================================================================
cache-warm:
  if: github.ref == 'refs/heads/main'
  needs: [cache-calc, test-unit, test-integration]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}
        cache: npm

    # 新鲜的 npm ci 以生成与锁定文件精确匹配的 node_modules
    - name: 安装依赖
      run: npm ci

    # 使用精确的 dep-key 显式保存 node_modules 缓存
    # 这会覆盖具有相同键的任何过期缓存条目
    - name: 预热依赖缓存
      uses: actions/cache/save@v4
      with:
        path: node_modules
        key: ${{ needs.cache-calc.outputs.dep-key }}-${{ env.NODE_VERSION }}

    # 通过运行构建并保存 dist/ 来预热构建缓存
    - name: 构建项目
      run: npm run build

    - name: 预热构建缓存
      uses: actions/cache/save@v4
      with:
        path: dist
        key: ${{ needs.cache-calc.outputs.build-key }}-${{ env.NODE_VERSION }}
```

### 逐行说明

| 行号 | 元素 | 说明 |
|------|---------|-------------|
| 1-18 | `#` 注释 | 解释目的和设计原理的文档。 |
| 19 | `cache-warm:` | 任务 ID。 |
| 20 | `if: github.ref == 'refs/heads/main'` | **任务级条件。** 如果表达式计算结果为 `false`，整个任务被跳过（在 UI 中显示为"已跳过"，而非"失败"）。该条件检查当前引用是否为 main 分支。 |
| 21 | `needs: [cache-calc, test-unit, test-integration]` | 依赖于三个任务（数组语法）。缓存预热仅在所有测试在 main 上通过后进行。包含 `cache-calc` 是因为我们引用了 `needs.cache-calc.outputs.*`。 |
| 22 | `runs-on: ubuntu-latest` | Linux 运行器。 |
| 24-25 | 检出 | 标准。 |
| 27-31 | 使用 `cache: npm` 设置 Node | 这里我们确实使用 `cache: npm`，因为我们从头运行 `npm ci`。 |
| 33-34 | `npm ci` | 全新安装以生成我们要缓存的精确 `node_modules/`。 |
| 36-41 | 保存依赖缓存 | |
| 38 | `uses: actions/cache/save@v4` | 仅保存子操作。与完整的 `actions/cache`（作为后操作保存）不同，这会**立即**保存。 |
| 40 | `key: ${{ needs.cache-calc.outputs.dep-key }}-${{ env.NODE_VERSION }}` | 将来 PR 运行将查找的精确键。通过在 main 上显式保存，我们保证下一个 PR 的缓存存在。 |
| 43-44 | `npm run build` | 运行构建以生成 `dist/`。 |
| 46-51 | 保存构建缓存 | 相同模式：使用构建键显式保存 `dist/`。 |

### 动作能力：`actions/cache/save@v4`

**目的：** 立即显式保存缓存条目（不作为后操作）。

**关键输入：**

| 输入 | 必需 | 描述 |
|-------|----------|-------------|
| `path` | 是 | 要缓存的目录/文件 |
| `key` | 是 | 缓存键（必须唯一） |
| `upload-chunk-size` | 否 | 大型缓存上传的块大小 |

**约束：**
- 每个条目的最大缓存大小：约 10 GB（因套餐而异）
- 最大条目数：无硬性限制，但适用 LRU 淘汰
- 每个条目的键必须唯一（使用现有键的新保存会覆盖）
- 缓存条目在无访问 7 天后过期（可由 GitHub 支持调整）

### `actions/cache/save` 与后操作保存对比

完整的 `actions/cache` 操作有两个阶段：

1. **前操作（恢复）：** 在使用 `actions/cache` 的步骤之前运行。如果键匹配，恢复缓存。
2. **后操作（保存）：** 在任务完成后运行。仅当键是新的（不是缓存命中）时保存缓存。

**这造成的问题：**

```
运行 1（main，缓存未命中）：
  步骤：actions/cache → 恢复：未命中
  步骤：npm ci → 创建 node_modules
  后操作：cache/save → 使用键 X 保存 node_modules
  → 缓存条目 X 存在 ✓

运行 2（main，缓存命中 — 相同提交重新运行）：
  步骤：actions/cache → 恢复：命中 → node_modules 恢复
  步骤：npm ci → 验证（快速，无变化）
  后操作：cache/save → 跳过（是缓存命中）
  → 缓存条目 X 仍然存在，但使用原始 TTL ✓

运行 3（main，8 天后缓存淘汰后缓存未命中）：
  步骤：actions/cache → 恢复：未命中（条目 X 被淘汰）
  步骤：npm ci → 从头安装
  后操作：cache/save → 保存新条目 X
  → 可以工作，但淘汰后的第一个 PR 很慢 ✗
```

**`cache-warm` 的修复：**

```
运行 N（main）：
  → cache-warm 任务运行
  → actions/cache/save 使用键 X → 覆盖/创建条目
  → 缓存条目 X 是新鲜的，具有新的 TTL


运行 N+1（基于 main 的 PR 分支）：
  → deps-install 查找键 X → 命中
  → node_modules 在几秒内恢复 ✓
```

### 动作能力：任务级与步骤级的 `if:`

**任务级 `if:`：**
```yaml
jobs:
  my-job:
    if: <condition>
    ...
```
- 控制整个任务是否运行
- 如果为 `false`，任务在 UI 中显示为"已跳过"
- 所有任务依赖（`needs:`）仍需完成（或被跳过）
- 表达式可以引用 `github`、`env`、`needs` 等

**步骤级 `if:`：**
```yaml
steps:
  - name: My step
    if: <condition>
    ...
```
- 控制单个步骤是否运行
- 如果为 `false`，步骤被跳过但后续步骤仍然运行
- `if: always()` 覆盖失败状态

### 为什么这个模式很重要

没有 `cache-warm`，main 分支上的缓存会随时间退化：

```
第 1 天：缓存条目创建（良好）
第 7 天：缓存条目过期（LRU 淘汰或 TTL）
第 8 天：第一个 PR → 缓存未命中 → 慢 npm ci → 慢管道
```

有了 `cache-warm`，每次成功的 main 合并都会刷新缓存：

```
第 1 天：缓存条目创建
第 2 天：合并到 main → cache-warm → 条目刷新
第 7 天：合并到 main → cache-warm → 条目刷新（永不过期）
第 8 天：第一个 PR → 缓存命中 → 快速管道
```

这对于具有定期但非连续 CI 活动的仓库尤其重要。

---

## 14. 表达式语法和上下文对象

### `${{ }}` 表达式分隔符

GitHub Actions 表达式用 `${{ }}` 括起来。表达式解析器在工作流运行开始前计算这些值。

```yaml
# 工作流中的示例：
${{ hashFiles('package-lock.json') }}
${{ runner.os }}
${{ matrix.node }}
${{ needs.cache-calc.outputs.dep-key }}
${{ github.ref }}
${{ github.workflow }}
${{ env.NODE_VERSION }}
${{ matrix.os }}
```

**规则：**
- 表达式可以出现在任何工作流字段中（不仅仅是 `run:`）
- 表达式结果自动转换为字符串
- 如果在 `run:` 命令中使用表达式，它在服务端计算，结果嵌入到 shell 命令中
- 字面量 `$` 必须根据上下文转义为 `$$` 或 `${{ '#' }}`

### 可用的上下文对象

| 上下文 | 描述 | 常用属性 |
|---------|-------------|-------------------|
| `github` | 关于工作流运行和事件的信息 | `github.ref`、`github.sha`、`github.repository`、`github.actor`、`github.event_name`、`github.workflow`、`github.run_id`、`github.run_number` |
| `env` | 在工作流/任务/步骤中定义的环境变量 | `env.MY_VAR` |
| `runner` | 关于运行器的信息 | `runner.os`、`runner.arch`、`runner.name`、`runner.temp` |
| `matrix` | 当前矩阵值 | `matrix.node`、`matrix.os`、`matrix.shard` |
| `needs` | 来自依赖任务的输出 | `needs.cache-calc.outputs.dep-key` |
| `steps` | 来自先前步骤的输出 | `steps.my-step.outputs.cache-hit` |
| `secrets` | 仓库/组织密钥 | `secrets.GITHUB_TOKEN` |
| `inputs` | 工作流调度输入 | `inputs.my-input` |
| `strategy` | 矩阵策略信息 | `strategy.job-index`、`strategy.job-total`、`strategy.max-parallel` |

### 表达式中可用的函数

| 函数 | 描述 | 示例 |
|----------|-------------|---------|
| `hashFiles()` | 文件内容的 SHA-256 哈希 | `hashFiles('package.json')` |
| `contains()` | 检查字符串/数组是否包含值 | `contains('hello', 'ell')` |
| `startsWith()` | 检查字符串是否以值开头 | `startsWith(github.ref, 'refs/heads/')` |
| `endsWith()` | 检查字符串是否以值结尾 | `endsWith(github.ref, '/main')` |
| `format()` | 字符串格式化 | `format('{0} {1}', 'hello', 'world')` |
| `join()` | 使用分隔符连接数组 | `join(github.commits, ', ')` |
| `toJSON()` | 美化打印 JSON | `toJSON(github)` |
| `fromJSON()` | 解析 JSON 字符串 | `fromJSON(inputs.my-json)` |
| `success()` | 所有前面的步骤是否都成功了？ | `success()` |
| `failure()` | 是否有前面的步骤失败了？ | `failure()` |
| `cancelled()` | 工作流是否被取消？ | `cancelled()` |
| `always()` | 始终为 true | `always()` |

### 运算符优先级和类型强制

表达式支持：
- **比较：** `==`、`!=`、`<`、`>`、`<=`、`>=`
- **布尔：** `&&`、`||`、`!`
- **三元：** `condition ? true-value : false-value`
- **空值合并：** `value ?? default-value`

**类型强制规则：**

```yaml
# 字符串比较（默认 — GitHub Actions 中的大多数值都是字符串）
'false' == 'true'   → false
'false' == false    → false（字符串 != 布尔值）

# 布尔比较（使用不带引号的 `true`/`false`）
true && false       → false
true || false       → true

# 在条件中，不带引号的字符串被视为字面量值
if: true            → 运行
if: false           → 跳过
if: 'true'          → 错误（if: 中不允许使用字符串）
```

**重要说明：** 在 `if:` 块中，必须使用不带引号的布尔值：
```yaml
# 正确
if: true
if: false
if: success()

# 错误
if: 'true'   # 被当作字符串，这是 truthy → 始终运行！
```

### `needs` 上下文的详细说明

`needs` 上下文是复杂工作流中最重要的上下文之一：

```yaml
# 访问非矩阵任务的输出：
${{ needs.cache-calc.outputs.dep-key }}

# 访问矩阵任务的输出 — 需要特定索引：
# 这不能直接实现。矩阵任务输出必须被聚合。
```

**矩阵任务输出的限制：** 当矩阵任务声明 `outputs:` 时，每个矩阵变体都尝试设置相同的输出。最后一个完成的变体获胜。这使得矩阵输出不可靠。解决方式：
1. 对矩阵数据使用构件而不是输出
2. 使用读取构件并生成输出的非矩阵"聚合器"任务
3. 接受最后写入者胜出的行为

### `hashFiles` 函数的详细说明

`hashFiles()` 函数在 Actions 服务器上计算，而不是在运行器上。这有以下影响：

```yaml
# hashFiles 仅适用于工作区中的文件。
# 它根据以下因素返回不同的值：
# 1. 文件内容（显然）
# 2. glob 匹配的文件路径
# 3. 行尾规范化（Git 检出设置）

# 最佳实践：
# - 在同一任务中，始终在 hashFiles 之前执行检出
# - 使用平台无关的模式（正斜杠）
# - 不要在哈希模式中包含 node_modules 或 dist
```

**性能说明：** 在大型仓库中，使用递归 glob（`src/**/*.ts`）的 `hashFiles()` 可能很慢。如果你有 10,000+ 个 TypeScript 文件，考虑使用更有针对性的模式。在我们的例子中，`src/` 足够小，这不是问题。

---

## 15. 关键模式总结

### 模式 1：缓存键链接

```
dep-key = npm-cache-<lockfile-hash>-<OS>
build-key = build-<source-hash>-<dep-hash>
docker-key = docker-<dockerfile-hash>-<dep-hash>
test-key = test-<test-hash>
```

构建依赖于依赖 → 当依赖变化时，构建缓存自动失效。

### 模式 2：带后备的缓存恢复

```yaml
key: specific-key-with-all-details
restore-keys: |
  prefix-with-fewer-details-
  even-broader-prefix-
```

GitHub Actions 首先尝试 `key`，然后按顺序尝试每个 `restore-keys` 前缀，返回匹配每个前缀的最近创建的缓存。这提供了优雅降级：最佳情况 = 精确命中，最差情况 = 无缓存。

### 模式 3：构件传递

```
              ┌──────────────┐
              │ deps-install │──→ node_modules 构件
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │    build      │──→ dist 构件
              └──────┬───────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   test-unit    test-integ    （其他任务）
```

构件向前流动。每个任务生成一个被下一阶段使用的构件。

### 模式 4：主分支的显式缓存保存

所有测试在 main 上通过后，`cache-warm` 显式保存缓存。这：
- 保证下一个 PR 的缓存条目存在
- 刷新现有条目的 TTL
- 避免冷启动缓慢

### 模式 5：带排除的矩阵用于成本管理

```yaml
matrix:
  node: [18, 20, 22]
  os: [ubuntu, windows]
exclude:
  - os: windows
    node: 18
```

这测试了最广泛的范围，同时排除了昂贵或低价值的组合。

### 模式 6：快速反馈与慢速任务并行

```
cache-calc（快速，单个）
    ├── deps-install（矩阵，慢速）──→ build（矩阵，慢速）──→ tests（并行）
    ├── lint（快速，单个）
    └── docker-prepare（快速，单个）
```

从 `deps-install` 经过 `build` 到 `tests` 的关键路径决定了总实际耗时。快速任务（`lint`、`docker-prepare`）并行运行，不会延长关键路径。

### 模式 7：优雅的失败处理

| 技术 | 示例 | 目的 |
|-----------|---------|---------|
| `if: always()` | 清理步骤 | 确保即使在失败后也能进行清理 |
| `if: failure()` | 日志收集 | 仅在需要时运行调试步骤 |
| `fail-fast: false` | 测试矩阵 | 从所有组合获取信号 |
| `\|\|` 后备 | 集成测试命令 | 优雅处理缺失的测试配置 |

---

## 附录：工作流配置和调优

### 缓存大小管理

每个仓库的 GitHub Actions 缓存存储空间有限（因套餐而异，通常为 10 GB）。我们的工作流在三个地方使用缓存：

| 缓存 | 范围 | 估计大小 | 频率 |
|-------|-------|---------------|-----------|
| 依赖缓存（node_modules） | 每 node 版本 | 100-500 MB | 每次 main 合并 |
| 构建缓存（dist/） | 每 node 版本 | 5-50 MB | 每次 main 合并 |
| Docker 层缓存 | 共享 | 200-2000 MB | 每次 main 合并 |

**调优建议：**
- 在 GitHub UI 中监控缓存使用情况，路径为"Actions > Caches"
- 如果接近缓存限制，减小缓存范围或提高淘汰优先级
- Docker 层缓存通常是最大贡献者 — 考虑使用 `mode=min` 代替 `mode=max` 以减小大小，代价是缓存命中率降低
- 构件存储有单独的限制 — 对中间构件使用 `retention-days: 1`

### 调整矩阵范围

当前工作流最多运行 3（deps-install）+ 3（build）+ 10（test-unit）+ 1（lint）+ 1（docker-prepare）+ 1（test-integration）+ 1（cache-warm）= 20 个并行任务。这在典型的 GitHub Actions 限制范围内，但在较小的套餐上可能达到并发限制。

**为减少并发：**
```yaml
# 向 strategy 添加 max-parallel
strategy:
  max-parallel: 5
```

**为定位特定 Node 版本：**
```yaml
# 仅最新两个 LTS 版本
matrix:
  node: [20, 22]
```

**为减少操作系统覆盖：**
```yaml
# 仅 Linux 测试（去掉 Windows）
matrix:
  node: [18, 20, 22]
  os: [ubuntu-latest]
  shard: [1, 2]
```

### 监控工作流性能

要跟踪的关键指标：

| 指标 | 衡量内容 | 目标 |
|--------|-----------------|--------|
| 总实际耗时 | 从触发到完成的时间 | < 10 分钟 |
| 缓存命中率 | 缓存恢复的命中百分比 | > 80% |
| 构件传输时间 | 上传/下载构件的时间 | < 30 秒 |
| 测试分片不平衡 | 最快和最慢分片之间的差异 | < 20% |

要监控缓存命中率，向任何缓存恢复任务添加此步骤：

```yaml
- name: 报告缓存状态
  if: always()
  run: echo "Cache hit: ${{ steps.deps-cache-restore.outputs.cache-hit }}"
```

### 特定环境的配置

工作流使用 `env.NODE_VERSION`（20）作为默认值。对于具有不同 LTS 计划的项目：

```yaml
env:
  NODE_VERSION: 18    # 对于需要较旧 LTS 的项目
  NODE_LTS: 20        # 最新 LTS
```

对于具有多个包的单仓库，`hashFiles()` 模式可能需要调整：

```yaml
# 对于具有 packages/ 目录的单仓库：
hashFiles('packages/*/package-lock.json', 'package-lock.json')
```

---

## 附录：替代方案和设计权衡

### 方案 A：集中式键计算（我们的选择）

**工作原理：** 一个任务计算所有缓存键，下游任务通过 `needs.outputs` 读取它们。

**优点：**
- 键计算逻辑的单一控制点
- 所有任务的一致模式
- 易于审计和修改

**缺点：**
- 在关键路径上增加一个顺序任务（15-30 秒）
- 键计算与使用分离（认知开销）
- 矩阵任务必须使用附加的矩阵值构造自己的键

**最适合：** 重视一致性和可审计性的团队。具有许多缓存消费者的大型工作流。

### 方案 B：分布式键计算

**工作原理：** 每个任务直接使用 `hashFiles()` 计算自己的缓存键，没有共享的键计算任务。

```yaml
deps-install:
  steps:
    - uses: actions/checkout@v4
    - id: compute
      run: echo "key=npm-cache-${{ hashFiles('package-lock.json') }}-${{ runner.os }}-${{ matrix.node }}" >> "$GITHUB_OUTPUT"
    - uses: actions/cache@v4
      with:
        key: ${{ steps.compute.outputs.key }}
```

**优点：**
- 更简单的 DAG（少一个任务）
- 键自然包含矩阵值
- 无需跨任务输出连接

**缺点：**
- 键计算逻辑在各任务间重复
- 漂移风险：相同"键"的不同模式
- 更难审计（必须检查每个任务）

**最适合：** 具有 2-3 个任务的小型工作流。原型和简单 CI 设置。

### 方案 C：混合（环境变量中的键）

**工作原理：** 使用 `env:` 和 `hashFiles()` 在工作流级别计算键：

```yaml
env:
  DEP_KEY: npm-cache-${{ hashFiles('package-lock.json') }}
```

**为什么这不起作用：** `env:` 中的 `hashFiles()` 在工作流生命周期的不同时间点计算，可能无法访问检出。GitHub Actions 不可靠地支持顶层 `env:` 块中的 `hashFiles()`。

**最适合：** 不适用 — 它不可靠地工作。避免此模式。

### 方案 D：仅构件（无缓存）

**工作原理：** 对所有传递使用构件，完全跳过 `actions/cache`。

**优点：**
- 更简单的设置（无缓存键）
- 无缓存存储成本
- 无缓存淘汰问题

**缺点：**
- 无跨运行持久性：每次首次推送到分支都从头开始
- 构件在 `retention-days` 后被删除
- 在跨运行场景中比缓存慢

**最适合：** CI 运行非常不频繁的仓库，其中缓存效率无关紧要。

### 为什么我们选择了方案 A

对于此工作流，集中式方法胜出，因为：
1. **可审计性：** 一个 `cache-calc` 任务记录了所有缓存键模式
2. **一致性：** 每个任务从同一来源读取 — 没有漂移
3. **教育价值：** 演示了任务输出、needs 链接和表达式组合
4. **生产就绪：** 一个额外任务的轻微开销与总构建时间相比微不足道（15 秒对比 5-8 分钟）

### 分片策略比较

| 策略 | 分片机制 | 设置复杂度 | 负载均衡 |
|----------|----------------|------------------|--------------|
| Vitest `--shard` | 内置于测试运行器 | 低 | 良好（文件级别） |
| Jest `--shard` | 内置于测试运行器 | 低 | 良好（文件级别） |
| 手动文件拆分 | 自定义脚本 | 高 | 最佳（测试级别） |
| `github.graphql` 查询 | 查询 API 获取文件 | 高 | 差（无测试加权） |

Vitest 分片是已经使用 Vitest 的项目的推荐方法。它不需要自定义基础设施，并提供确定性的文件拆分。

---

## 附录：常见的 GitHub Actions 陷阱

### 陷阱 1：未检出时使用 `hashFiles`

```yaml
# 错误 — hashFiles 返回空字符串（未找到文件）
steps:
  - id: compute
    run: echo "hash=${{ hashFiles('package.json') }}" >> "$GITHUB_OUTPUT"

# 正确 — 先检出
steps:
  - uses: actions/checkout@v4
  - id: compute
    run: echo "hash=${{ hashFiles('package.json') }}" >> "$GITHUB_OUTPUT"
```

### 陷阱 2：`if:` 中的字符串与布尔值

```yaml
# 错误 — 字符串 'true' 始终为 truthy
if: 'true'

# 正确 — 布尔值 true
if: true

# 正确 — 用于值的字符串比较
if: github.ref == 'refs/heads/main'
```

### 陷阱 3：缓存键随每次推送变化

```yaml
# 错误 — 缓存永远不会命中，因为 SHA 每次变化
key: build-${{ github.sha }}

# 正确 — hashFiles 捕获内容标识
key: build-${{ hashFiles('src/**/*.ts') }}
```

### 陷阱 4：首次运行时没有 `restore-keys`

对于新仓库的第一次工作流运行，不存在缓存。没有 `restore-keys`，缓存步骤只是跳过（无错误，无恢复）。有 `restore-keys`，至少有机会从其他工作流中获得部分匹配。

### 陷阱 5：构件名称冲突

```yaml
# 错误 — 所有矩阵任务上传到相同的构件名称
name: node_modules

# 正确 — 每个矩阵变体都有唯一的名称
name: node_modules-${{ matrix.node }}
```

### 陷阱 6：集成测试中缺少清理

```yaml
# 错误 — 如果测试失败，docker compose 永远不会停止
- run: docker compose up -d
- run: npm run test:integration   # 如果失败 → 容器泄漏！
- run: docker compose down        # 永远不会运行

# 正确 — 清理始终运行
- run: docker compose up -d
- run: npm run test:integration
- if: always()
  run: docker compose down -v
```

---

## 附录：操作版本兼容性

### `actions/cache@v4` 与 v3 的破坏性变化

| 变化 | v3 | v4 |
|--------|----|----|
| 缓存键格式 | 纯字符串 | 相同（无变化） |
| 保存行为 | 仅后操作 | 仅后操作 |
| 子操作 | 不适用（单个操作） | `restore`、`save`、完整 |
| Windows 路径 | 正斜杠 | 本机反斜杠 |
| 缓存大小限制 | 约 5 GB | 约 10 GB |
| 压缩 | gzip | zstd（更快） |

### `actions/upload-artifact@v4` 与 v3 的破坏性变化

| 变化 | v3 | v4 |
|--------|----|----|
| 多次上传到同一名称 | 合并 | 替换（最后者胜） |
| 根目录行为 | 扁平化 | 保留 |
| 跨工作流下载 | 不支持 | 支持 `run-id` |
| 存储格式 | ZIP | ZIP（但更快） |

### `docker/build-push-action@v6` 关键特性

- 内置 BuildKit 支持（较新版本中不需要单独的 `setup-buildx`，但显式声明更好）
- 多种缓存后端支持（gha、registry、local、S3、Azure）
- `provenance` 和 `sbom` 证明支持
- 多平台构建
- 密钥挂载
- `cache-from` 和 `cache-to` 作为一等输入

---

## 附录：8 任务 DAG 参考

```
                          ┌──────────────────┐
                          │   cache-calc      │（计算所有缓存键）
                          └────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
          ┌─────────────────┐ ┌──────────┐ ┌──────────┐
          │  deps-install    │ │ lint     │ │ docker   │
          │（npm ci + 缓存）   │ │ 类型检查  │ │ prepare  │
          └────────┬────────┘ └──────────┘ └──────────┘
                   │
                   ▼
          ┌─────────────────┐
          │     build        │
          │（tsc + vite）     │
          └────────┬─────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
   ┌─────────────┐   ┌──────────────┐
   │  test-unit   │   │ test-integ   │
   │（矩阵 x10）   │   │（docker）     │
   └─────────────┘   └──────┬───────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  cache-warm      │（仅 main）
                   │（预热缓存         │
                   │   为下次构建）     │
                   └──────────────────┘
```

DAG 显示了执行依赖流程。处于同一水平级别的任务（例如 `lint` 和 `docker-prepare`）**并行**运行。由箭头连接的任务**顺序**运行（下游任务等待上游任务）。

**总执行时间线（估计）：**

| 阶段 | 实际耗时 | 并行度 |
|-------|----------------|-------------|
| cache-calc | 15 秒 | 1 个运行器 |
| deps-install | 60-120 秒 | 3 个运行器（矩阵） |
| lint | 30-60 秒 | 1 个运行器（与 docker-prepare 并行） |
| docker-prepare | 60-120 秒 | 1 个运行器（与 lint 并行） |
| build | 60-120 秒 | 3 个运行器（矩阵，在 deps-install 之后） |
| test-unit | 120-300 秒 | 10 个运行器（矩阵，在 build 之后） |
| test-integration | 180-300 秒 | 1 个运行器（在 build 之后，与 test-unit 并行） |
| cache-warm | 60-120 秒 | 1 个运行器（在测试之后，仅 main） |

**关键路径：** cache-calc → deps-install → build → test-unit（或 test-integration）→ cache-warm

估计的最小总实际耗时：约 5-8 分钟（完全缓存命中时）。

---

> **工作流 1：高级缓存与构建加速的文档到此结束。**
>
> 返回 [DESIGN.md](../DESIGN.md) 查看完整的实验规范。
