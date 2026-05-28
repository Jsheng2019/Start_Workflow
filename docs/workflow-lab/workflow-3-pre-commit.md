# Workflow 3: Pre-commit 代码门禁 — 完整指南

> **受众：** 想要理解 pre-commit 并在 CI 中部署代码门禁的开发者。
>
> **对应文件：**
> - `.pre-commit-config.yaml` — hook 配置
> - `.github/workflows/pre-commit.yml` — CI 工作流
>
> **涉及概念：** git hooks、pre-commit 框架、代码规范检查、GitHub Actions 缓存、YAML 配置

---

## 目录

1. [什么是 Pre-commit](#1-什么是-pre-commit)
2. [Pre-commit vs 传统脚本方式](#2-pre-commit-vs-传统脚本方式)
3. [核心概念：Hooks、Repos、Stages](#3-核心概念hooks-repos-stages)
4. [配置文件详解](#4-配置文件详解)
5. [常用 Hooks 推荐](#5-常用-hooks-推荐)
6. [本地使用](#6-本地使用)
7. [在 CI 中集成](#7-在-ci-中集成)
8. [缓存加速策略](#8-缓存加速策略)
9. [高级用法](#9-高级用法)
10. [常见问题](#10-常见问题)
11. [Workflow 结构说明](#11-workflow-结构说明)

---

## 1. 什么是 Pre-commit

pre-commit 是一个**多语言 git hook 管理框架**。它允许你在 `.pre-commit-config.yaml` 中声明需要执行的检查（hooks），然后自动在每次 `git commit` 或 CI 流水线中运行这些检查。

### 它解决什么问题？

- **统一规范**：团队所有人在 commit 前运行相同的检查，避免"我机器上能过"的问题
- **零配置分发**：只需一个 `.pre-commit-config.yaml` 文件，新成员执行 `pre-commit install` 即可
- **多语言支持**：Python、Node.js、Shell、Docker 等语言的 hook 都能管理
- **自动缓存**：首次安装后 hook 环境被缓存，后续运行极快（毫秒级）

### 安装方式

```bash
# 通过 pip（推荐）
pip install pre-commit

# 通过 brew（macOS）
brew install pre-commit

# 验证
pre-commit --version
```

### 快速上手

```bash
# 1. 在项目根目录创建配置文件
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
EOF

# 2. 安装 git hook 脚本
pre-commit install

# 3. 手动运行一次（对所有文件）
pre-commit run --all-files
```

---

## 2. Pre-commit vs 传统脚本方式

| 对比维度 | 传统脚本 | pre-commit |
|---------|---------|-----------|
| 配置方式 | 手动维护 shell 脚本 | YAML 声明式配置 |
| 环境隔离 | 依赖全局安装的工具 | 每个 hook 自动创建隔离的虚拟环境 |
| 版本锁定 | 依赖开发者的本地版本 | `rev` 字段锁定版本，全团队一致 |
| 缓存更新 | 手动 | `pre-commit autoupdate` 一键更新 |
| 文件过滤 | 手动 grep/find | `files`/`types`/`exclude` 声明式过滤 |
| 跨平台 | 需要分别写 .sh 和 .ps1 | 同一配置，Windows/macOS/Linux 通用 |
| CI 集成 | 需要维护两套脚本 | CI 中执行 `pre-commit run --all-files` 即可 |

---

## 3. 核心概念：Hooks、Repos、Stages

### Hook

一个 Hook 是**一个具体的检查动作**，比如"检查 YAML 语法"、"去除行尾空格"。每个 hook 有唯一的 `id`。

### Repo

Hook 按来源分组，每组称为一个 **repo**。一个 repo 可以包含多个相关的 hooks。

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0        # 锁定的版本
    hooks:
      - id: check-yaml
      - id: trailing-whitespace
```

### Stage

Hook 可以在不同的 git 阶段运行：

| Stage | 触发时机 |
|-------|---------|
| `commit`（默认） | `git commit` 时 |
| `push` | `git push` 前 |
| `commit-msg` | commit message 编辑时 |
| `manual` | 仅手动触发（`pre-commit run --hook-stage manual`） |

```yaml
hooks:
  - id: commitizen
    stages: [commit-msg]     # commit-msg hooks
  - id: check-yaml
    stages: [commit, push]   # commit + push 阶段
```

---

## 4. 配置文件详解

### 完整的 `.pre-commit-config.yaml` 结构

```yaml
# ---- 全局配置（可选）----
fail_fast: false                  # 遇到第一个失败是否立即停止
minimum_pre_commit_version: 3.0.0 # 要求的最低 pre-commit 版本
exclude: '^(node_modules/|dist/|coverage/)' # 全局排除

# ---- Hook 仓库列表 ----
repos:
  # 远程 hook 仓库
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0                  # tag / commit hash
    hooks:
      - id: trailing-whitespace  # hook ID
        args: [--markdown-linebreak-ext=md]  # 额外参数
        files: '\.(py|js|ts|yml|json|md)$'   # 只检查这些文件类型
        exclude: '^tests/fixtures/'           # 排除某些文件

      - id: check-added-large-files
        args: [--maxkb=500]      # 禁止 >500KB 的文件

      - id: check-merge-conflict
        name: 检查合并冲突       # 自定义显示名称

  # 本地 hook（不依赖远程仓库）
  - repo: local
    hooks:
      - id: my-local-check
        name: Local Check
        entry: bash -c 'echo "Running local check"'
        language: system
        pass_filenames: false
```

### Hook 配置项速查

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | Hook 标识（必需） |
| `name` | string | 覆盖默认显示名称 |
| `args` | list | 传递给 hook 的额外参数 |
| `files` | regex | 文件名过滤模式 |
| `types` | list | 文件类型过滤（AND 关系） |
| `types_or` | list | 文件类型过滤（OR 关系） |
| `exclude` | regex | 排除模式 |
| `exclude_types` | list | 排除的文件类型 |
| `always_run` | bool | 是否始终运行（即使无匹配文件） |
| `additional_dependencies` | list | 安装额外依赖 |
| `stages` | list | 限制运行的 git hook 阶段 |

---

## 5. 常用 Hooks 推荐

### 通用检查（pre-commit-hooks）

| Hook ID | 功能 | 适用场景 |
|---------|------|---------|
| `trailing-whitespace` | 去除行尾空格 | **任何项目** |
| `end-of-file-fixer` | 确保文件以换行结束 | **任何项目** |
| `check-yaml` | YAML 语法验证 | **任何项目** |
| `check-json` | JSON 语法验证 | 含 JSON 配置的项目 |
| `check-merge-conflict` | 检测合并冲突残留 | **任何项目** |
| `check-added-large-files` | 阻止提交大文件 | **任何项目** |
| `detect-private-key` | 检测私钥泄露 | **任何项目** |
| `mixed-line-ending` | 统一换行符 | 跨平台项目 |
| `debug-statements` | 检测调试语句（pdb, ipdb） | Python 项目 |
| `check-xml` | XML 语法验证 | 含 XML 的项目 |
| `check-toml` | TOML 语法验证 | Python/ Rust 项目 |

### 语言/工具专属

| 语言/工具 | Repo | 功能 |
|----------|------|------|
| Node.js | `pre-commit/mirrors-eslint` | ESLint 代码检查 |
| Node.js | `pre-commit/mirrors-prettier` | Prettier 格式化 |
| Python | `psf/black` | Black 代码格式化 |
| Python | `PyCQA/flake8` | Flake8 代码风格检查 |
| Docker | `hadolint/hadolint` | Dockerfile lint |
| Shell | `shellcheck-py/shellcheck-py` | Shell 脚本检查 |
| GitHub Actions | `python-jsonschema/check-jsonschema` | Workflow 文件验证 |
| Git | `jorisroovers/gitlint` | Commit message 检查 |
| Markdown | `igorshubovych/markdownlint-cli` | Markdown lint |

### 本项目使用的 Hooks

本项目（Start_Workflow）是 Node.js + GitHub Actions 项目，配置了：

| Hook | 用途 |
|------|------|
| `check-yaml` | CI 配置都是 YAML，这是必须的 |
| `check-json` | package.json、配置文件使用 JSON 格式 |
| `check-merge-conflict` | 防止合并后留下 `<<<<<<<` 标记 |
| `end-of-file-fixer` | 规范文件结尾 |
| `trailing-whitespace` | 清理编辑器的多余空格 |
| `mixed-line-ending` | 统一使用 LF（Linux 换行符） |
| `check-added-large-files` | 防止提交 500KB 以上的文件 |
| `detect-private-key` | 安全检查：私钥泄露 |
| `check-executables-have-shebangs` | Shell 脚本必须有 `#!/` 头 |
| `check-github-workflows` | 验证 GitHub Actions workflow 语法 |

---

## 6. 本地使用

### 安装 git hook

```bash
pre-commit install
```

安装后，每次 `git commit` 时 hooks 会自动运行：

```bash
$ git commit -m "fix: update config"
Check YAML 语法..................................Passed
Check JSON 语法..................................Passed
Check 合并冲突标记.................................Passed
Fix 文件末尾换行..................................Passed
Trim 行尾空白.....................................Passed
Fix 混合换行符....................................Passed
Check 大文件......................................Passed
```

### 手动运行

```bash
# 对所有文件运行
pre-commit run --all-files

# 对 staged 文件运行（模拟 commit 行为）
pre-commit run

# 只运行指定 hook
pre-commit run check-yaml

# 只对指定文件运行
pre-commit run --files src/index.ts
```

### 跳过检查（慎用）

```bash
# 跳过指定 hook
SKIP=check-yaml git commit -m "wip"

# 完全跳过所有 hooks
git commit --no-verify -m "wip"
```

### 更新 hooks 版本

```bash
pre-commit autoupdate
```

此命令会检查每个 repo 的最新 tag，并更新 `rev` 字段。

---

## 7. 在 CI 中集成

### 核心思想

CI 中不执行 `pre-commit install`（那是给本地用的），而是直接执行：

```bash
pre-commit run --all-files --show-diff-on-failure --color=always
```

- `--all-files`：检查所有文件，不只是 staged 的文件
- `--show-diff-on-failure`：失败时显示 diff，便于排查
- `--color=always`：保留彩色输出，便于阅读日志

### GitHub Actions 完整示例

```yaml
name: Pre-commit Checks
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pre-commit
      - run: pre-commit run --all-files --show-diff-on-failure
```

### 其他 CI 平台

| CI 平台 | 关键配置 |
|---------|---------|
| **GitLab CI** | 添加 `before_script: [pip install pre-commit]` 和 `script: [pre-commit run --all-files]` |
| **Jenkins** | 在 Pipeline 的 `Build` stage 中执行 `pip install pre-commit && pre-commit run --all-files` |
| **CircleCI** | 在 `.circleci/config.yml` 中添加 `run: pip install pre-commit && pre-commit run --all-files` |

---

## 8. 缓存加速策略

pre-commit 的首次运行需要下载和安装各 hook 的依赖环境，这个步骤耗时较长。通过缓存 `~/.cache/pre-commit` 目录可以显著加速。

### GitHub Actions 缓存

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pre-commit
    # 缓存 key 必须包含 Python 版本 + .pre-commit-config.yaml 的 hash
    # 这样 Python 版本变化或 hook 配置变化时，缓存会自动失效
    key: pre-commit|${{ env.pythonLocation }}|${{ hashFiles('.pre-commit-config.yaml') }}
    restore-keys: |
      pre-commit|${{ env.pythonLocation }}
      pre-commit
```

### 缓存 key 设计说明

| 组件 | 作用 |
|------|------|
| `${{ env.pythonLocation }}` | Python 版本变化时自动失效 |
| `${{ hashFiles('.pre-commit-config.yaml') }}` | Hook 配置变化时自动失效 |
| `restore-keys` | 部分匹配时也能复用旧缓存 |

---

## 9. 高级用法

### 9.1 本地 Hook（`repo: local`）

当检查逻辑紧密耦合于当前项目时，使用本地 hook：

```yaml
- repo: local
  hooks:
    - id: npm-test
      name: Run npm test
      entry: npm test
      language: system      # 使用系统当前环境
      pass_filenames: false # 不传递文件名参数
      always_run: true
```

### 9.2 按阶段运行不同 Hook

```yaml
repos:
  # commit 阶段运行
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
        stages: [commit]

  # push 阶段运行（耗时较长）
  - repo: local
    hooks:
      - id: full-tests
        name: Run full test suite
        entry: npm test
        language: system
        stages: [push]
        pass_filenames: false
```

### 9.3 CI-only Hook

只希望在 CI 中运行（不在本地 commit 时运行）：

```yaml
- repo: https://github.com/pre-commit/pre-commit-hooks
  rev: v5.0.0
  hooks:
    - id: check-yaml
      always_run: true   # CI 中 --all-files 时强制执行
```

### 9.4 pre-commit.ci

pre-commit.ci 是一个第三方免费服务，可以：
- 自动对 PR 运行 pre-commit
- 自动修复简单问题（如空格）并提交修复 commit
- 定期自动更新 hook 版本并创建 PR

只需要在仓库 Settings → Integrations 中安装即可，不需要额外配置。

---

## 10. 常见问题

### Q: 首次运行很慢？
A: 正常现象。pre-commit 需要为每个 hook 创建隔离环境。后续运行走缓存，会快很多。在 CI 中启用缓存（见第 8 节）可以解决。

### Q: commit 时不想运行 hooks？
A: 使用 `git commit --no-verify` 或 `SKIP=<hook_id> git commit`。

### Q: `.pre-commit-config.yaml` 应该提交到仓库吗？
A: **必须提交**。这是团队共享的代码规范配置，不提交的话每个人都要自己写一份。

### Q: hook 失败但代码没问题？
A: 检查 `files`/`exclude` 过滤规则是否正确。也可以在 hook 中添加 `args` 适配你的代码风格。

### Q: 和 ESLint/Prettier 有什么区别？
A: pre-commit 是 **框架**（管理工具），ESLint/Prettier 是 **具体工具**（检查/格式化）。pre-commit 负责"在什么时机、用哪个版本、对哪些文件"运行 ESLint。

### Q: 能在 Windows 上使用吗？
A: 可以。pre-commit 完全支持 Windows，通过 `pip install pre-commit` 安装即可。

---

## 11. Workflow 结构说明

本项目的 `.github/workflows/pre-commit.yml` 工作流包含以下关键设计：

```yaml
# 触发条件
on:
  push:
    branches: [main, dev]       # 推送时检查
  pull_request:
    branches: [main, dev]       # PR 时检查
  workflow_dispatch:             # 手动触发

# 并发控制：同一分支多次 push 只保留最新一次
concurrency:
  group: pre-commit-${{ github.ref }}
  cancel-in-progress: true

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # 1. 检出代码
      - uses: actions/setup-python@v5      # 2. 安装 Python
      - uses: actions/cache@v4             # 3. 缓存 hook 环境
      - run: pip install pre-commit        # 4. 安装 pre-commit
      - run: pre-commit run --all-files    # 5. 运行所有 hooks
```

### 设计要点

1. **Python 版本固定为 3.12**：避免版本差异
2. **缓存 key 含 Python 路径 + 配置文件 hash**：自动失效
3. **`--show-diff-on-failure`**：失败时展示 diff
4. **`cancel-in-progress: true`**：节约 CI 资源
5. **手动触发支持**：方便调试

---

## 资源链接

- [pre-commit 官方文档](https://pre-commit.com)
- [pre-commit-hooks 仓库](https://github.com/pre-commit/pre-commit-hooks)
- [pre-commit GitHub Action](https://github.com/pre-commit/action)
- [pre-commit.ci 服务](https://pre-commit.ci)
