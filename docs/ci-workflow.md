# CI Pipeline 工作流详解

文件路径：`.github/workflows/ci.yml`

---

## 整体结构概览

```
name → on → jobs → job → runs-on → strategy → steps → step
```

---

## 逐行说明

### 第 1 行：`name: CI Pipeline`

为工作流命名，此名称会显示在 GitHub Actions 面板中。如果没有 name 字段，GitHub 会使用文件名作为默认名称。

---

### 第 4-7 行：`on:` 触发器

```yaml
on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
```

- **`on:`** — 定义工作流何时被触发，是 Actions 的入口配置。
- **`push:`** — 当有代码推送到指定分支时触发。这里指向 `main` 和 `master`，覆盖两种常见的主分支命名。
- **`pull_request:`** — 当有人对指定分支发起 Pull Request 时触发（包括 PR 的后续推送更新）。
- **为什么两个都要？** `push` 确保代码合入后跑一次流水线；`pull_request` 确保合入前就能发现问题。

> 其他常见触发器：`workflow_dispatch`（手动触发）、`schedule`（定时）、`release`（发布时）。

---

### 第 9 行：`jobs:` 作业集合

所有实际执行的任务都定义在 `jobs:` 下面。一个工作流可以有多个 job，默认并行运行。

---

### 第 10-13 行：`build:` Job 基础配置

```yaml
build:
  runs-on: ubuntu-latest
```

- **`build:`** — job 的 ID（也是名字），可以自定义，用于在 `needs` 中被引用。
- **`runs-on: ubuntu-latest`** — 指定运行器（runner）的操作系统。可选值包括 `ubuntu-latest`、`windows-latest`、`macos-latest`，以及自托管 runner 的标签。

---

### 第 14-16 行：`strategy.matrix` 矩阵策略

```yaml
strategy:
  matrix:
    node-version: [18.x, 20.x, 22.x]
```

- **`strategy.matrix`** — 矩阵构建策略，是 GitHub Actions 最强大的功能之一。定义一组变量值后，系统会生成笛卡尔积的组合，每个组合并行运行。
- **效果**：当前配置会同时启动 3 个 `build` job，分别使用 Node.js 18、20、22。在日志中它们会显示为 `build (18.x)`、`build (20.x)`、`build (22.x)`。
- **使用方式**：在后续步骤中通过 `${{ matrix.node-version }}` 引用当前 job 的值。

---

### 第 18-42 行：`steps:` 执行步骤

#### Step 1 (第 20-21 行)：检出代码

```yaml
- name: Checkout code
  uses: actions/checkout@v4
```

- **`name:`** — 步骤的显示名称，会出现在 Actions 日志中。
- **`uses:`** — 引用一个社区/官方发布的 Action。`actions/checkout@v4` 是 GitHub 官方出品，用于将仓库代码克隆到 runner 的工作目录。
- **`@v4`** — 版本号。建议锁定大版本，既能获得补丁更新，又不会因 breaking change 导致流水线挂掉。

#### Step 2 (第 24-28 行)：安装 Node.js

```yaml
- name: Setup Node.js ${{ matrix.node-version }}
  uses: actions/setup-node@v4
  with:
    node-version: ${{ matrix.node-version }}
    cache: 'npm'
```

- **`with:`** — 传递给 Action 的参数（inputs）。
- **`node-version:`** — 使用矩阵变量 `${{ matrix.node-version }}`，运行时会被替换为实际版本号。
- **`${{ }}`** — 表达式语法，用于访问上下文变量和函数。
- **`cache: 'npm'`** — 自动缓存 `node_modules`，后续运行直接命中缓存，大幅加速。内部通过 hash `package-lock.json` 来判断缓存是否有效。

#### Step 3 (第 31-32 行)：安装依赖

```yaml
- name: Install dependencies
  run: npm ci
```

- **`run:`** — 直接在 runner 的 shell 中执行命令。与 `uses` 不同，`run` 不需要引用外部 Action。
- **`npm ci` vs `npm install`**：
  - `npm ci` 严格按 `package-lock.json` 安装，不会修改 lock 文件，适合 CI 环境。
  - `npm install` 可能更新依赖版本，导致 CI 与本地不一致。

#### Step 4 (第 35-36 行)：构建项目

```yaml
- name: Build project
  run: npm run build --if-present
```

- **`--if-present`** — 如果 `package.json` 中没有 `build` 脚本，此步骤不会报错，直接跳过。这使工作流可以适配没有构建步骤的项目。

#### Step 5 (第 39-42 行)：上传产物

```yaml
- name: Upload build artifact
  uses: actions/upload-artifact@v4
  with:
    name: build-output-${{ matrix.node-version }}
    path: dist/
```

- **`actions/upload-artifact@v4`** — 将文件上传为工作流产物，可在 Actions 页面下载，也可被后续 job 下载使用。
- **`name:`** — 产物的唯一标识，这里加入了矩阵版本号避免覆盖。
- **`path:`** — 要上传的文件/目录路径。`dist/` 是常见的前端构建输出目录。

---

### 第 45-53 行：`lint` Job

```yaml
lint:
  needs: build
  runs-on: ubuntu-latest
```

- **`needs: build`** — **依赖声明**。`lint` job 会等待所有矩阵组合的 `build` 全部成功后才会启动。如果没有 `needs`，`lint` 和 `build` 会并行运行。
- **为什么设置依赖？** 如果连构建都失败了，就没有必要跑检查，可以节省 runner 资源。
- 注意这里使用 `uses:` 的简写形式（不写 `name:`），效果相同但更简洁。

---

### 第 56-65 行：`test` Job

```yaml
test:
  needs: build
  runs-on: ubuntu-latest
```

结构同 `lint`，执行 `npm test`。`--if-present` 保证没有测试脚本时不会失败。

---

## 关键概念总结

| 概念 | 说明 |
|------|------|
| `on` | 触发器，决定工作流何时运行 |
| `jobs` | 任务集合，每个 job 独立运行 |
| `runs-on` | 指定运行的操作系统环境 |
| `steps` | 步骤序列，按顺序在同一个 runner 上执行 |
| `uses` | 引用外部 Action |
| `run` | 执行 Shell 命令 |
| `needs` | 声明 job 间的依赖关系 |
| `strategy.matrix` | 生成多版本并行任务 |
| `${{ }}` | 表达式语法，访问上下文变量 |
| `with` | 向 Action 传递参数 |
| `--if-present` | 脚本不存在时跳过而不报错 |
