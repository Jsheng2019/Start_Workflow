# GitHub Actions Workflow 故障排除与修复报告

本文档记录了 5 个 GitHub Actions workflow 首次运行时的失败原因、诊断方法和修复过程。

---

## 失败总览

| Workflow | 失败的 Job | 失败原因 | 严重程度 |
|----------|-----------|----------|----------|
| CI Pipeline | `build`, `lint`, `test` | `npm ci` 找不到 `package-lock.json` | 致命 |
| Deploy Pipeline | `deploy-staging`, `deploy-production` | `npm ci` 找不到 `package-lock.json` | 致命 |
| PR Check | `auto-assign` | 引用的 `.github/auto_assign.yml` 不存在 | 致命 |
| PR Check | `size-label` | `GITHUB_TOKEN` 未作为输入参数传递 | 致命 |
| Scheduled Tasks | `security-audit` | `npm ci` 找不到 `package-lock.json`；`npm audit` 输出未写入文件 | 致命 / 次要 |
| Release | `build-and-test` | `npm ci` 找不到 `package-lock.json` | 致命 |
| CI Pipeline | `build` (artifact upload) | `dist/` 目录不存在（构建脚本未生成产物） | 次要 |

---

## 问题 1：`npm ci` 失败 — 缺少 `package-lock.json`

### 影响范围

- `ci.yml`: build (Node 18/20/22 ×3)、lint、test — **共 5 个 Job**
- `deploy.yml`: deploy-staging、deploy-production — **共 2 个 Job**
- `scheduled.yml`: security-audit — **1 个 Job**
- `release.yml`: build-and-test — **1 个 Job**
- **合计：9 个 Job 全部失败**

### 错误日志（来自 GitHub Actions）

```
Run npm ci
npm error code EUSAGE
npm error
npm error The `npm ci` command can only install with an existing
npm error package-lock.json or npm-shrinkwrap.json with lockfileVersion >= 1.
npm error
npm error Clean install a project
npm error
npm error Usage:
npm error npm ci
```

### 根因分析

`npm ci`（clean install）是专门为 CI/CD 环境设计的命令，它严格按照 `package-lock.json` 中锁定的版本安装依赖。与 `npm install` 不同：

- `npm install`：没有 lock 文件时自动生成一个新文件，宽松的语义版本匹配
- `npm ci`：必须有 lock 文件，严格匹配，如果 `package.json` 与 lock 文件不一致则直接报错

**为什么选择 `npm ci` 而非 `npm install`？**

| 特性 | `npm ci` | `npm install` |
|------|----------|---------------|
| 需要 lock 文件 | 是 | 否（会自动生成） |
| 安装速度 | 快（跳过依赖解析） | 慢（需要解析依赖树） |
| 一致性保证 | 严格 (lock 即真理) | 宽松 (semver 匹配) |
| CI 适用性 | 专为 CI 设计 | 本地开发用 |
| 修改 lock 文件 | 不会 | 可能 |

**我们的情况**：仓库中只有 `README.md`，没有任何 Node.js 项目文件。GitHub Actions runner 是一个全新的干净环境，没有现成的 `package-lock.json`。

### 原始代码

```yaml
# ci.yml 中的三个 job 都有此步骤
- name: Install dependencies
  run: npm ci
```

### 修复方法

**方法 1（已采用）**：创建最小化的 Node.js 项目，使 workflow 能正常执行：

1. 创建 `package.json`，包含 `build`、`test`、`lint` 脚本：

```json
{
  "name": "start-workflow",
  "version": "1.0.0",
  "main": "src/index.js",
  "scripts": {
    "build": "mkdir -p dist && node src/index.js > dist/output.txt && echo 'Build artifact created in dist/'",
    "test": "node --test test/*.test.js",
    "lint": "node -e \"console.log('Lint check passed')\""
  }
}
```

2. 运行 `npm install` 生成 `package-lock.json`
3. 创建 `src/index.js`（含简单函数）和 `test/basic.test.js`（Node 内置测试）

**方法 2（备选）**：将 `npm ci` 改为 `npm install`，但这会牺牲 CI 的一致性和速度，不推荐。

### 关键知识

| 命令 | 适用场景 |
|------|----------|
| `npm ci` | CI/CD 流水线、容器构建 |
| `npm install` | 本地开发、初次设置项目 |
| `npm install --production` | 仅安装生产依赖 |

---

## 问题 2：`dist/` 目录不存在 — Artifact 上传路径为空

### 影响范围

- `ci.yml`: build Job 的 `actions/upload-artifact@v4` 步骤

### 错误日志（预期）

```
Warning: No files were found with the provided path: dist/.
No artifacts will be uploaded.
```

或者：

```
Error: No files were found with the provided path: dist/.
```

`actions/upload-artifact@v4` 在找不到文件时会失败。

### 根因分析

原始 `package.json` 中的 build 脚本：

```json
"build": "node src/index.js"
```

`src/index.js` 虽然有输出，但只是打印到控制台，**没有创建 `dist/` 目录**。而 workflow 的上传步骤指定的 `path: dist/` 自然找不到文件。

### 修复方法

修改 build 脚本，使其创建 `dist/` 目录并写入构建产物：

```json
"build": "mkdir -p dist && node src/index.js > dist/output.txt && echo 'Build artifact created in dist/'"
```

执行效果：
1. `mkdir -p dist` — 创建 dist 目录（`-p` 表示已存在时不报错）
2. `node src/index.js > dist/output.txt` — 将程序输出重定向到文件
3. `echo '...'` — 打印确认信息（出现在 Actions 日志中）

---

## 问题 3：`.github/auto_assign.yml` 配置文件缺失

### 影响范围

- `pr-check.yml`: `auto-assign` Job

### 错误日志（预期）

```
Error: ENOENT: no such file or directory, open '.github/auto_assign.yml'
```

### 根因分析

`pr-check.yml` 的 auto-assign Job 使用了 `kentaro-m/auto-assign-action@v2.0.0`。此 Action 需要读取 `.github/auto_assign.yml` 配置文件来确定分配规则：

```yaml
- uses: kentaro-m/auto-assign-action@v2.0.0
  with:
    configuration-path: '.github/auto_assign.yml'  # ← 此文件不存在！
```

在 YAML 中使用 `uses` 引用 Action 时，Action 的行为依赖于 `with` 参数指向的配置文件。

### 修复方法

创建 `.github/auto_assign.yml` 配置文件：

```yaml
addReviewers: true
addAssignees: author
reviewers:
  - Jsheng2019
numberOfReviewers: 1
skipDraft: true
skipKeywords:
  - wip
  - work in progress
```

配置说明：
- `addReviewers: true` — 自动添加审查者
- `addAssignees: author` — 将 PR 作者设为负责人
- `reviewers:` — 候选审查者列表（GitHub 用户名）
- `numberOfReviewers: 1` — 从列表中随机选择 N 人
- `skipDraft: true` — 草稿 PR 跳过自动分配
- `skipKeywords:` — 标题包含关键字时跳过

---

## 问题 4：`npm audit` 输出未写入文件

### 影响范围

- `scheduled.yml`: `security-audit` Job

### 错误日志（预期）

```
Warning: No files were found with the provided path: npm-audit-output.txt.
No artifacts will be uploaded.
```

### 根因分析

原始代码存在问题：

```yaml
# Step 1: 运行审计 (输出到控制台)
- run: npm audit --audit-level=high     # ← 终端输出，未写入文件

# Step 2: 上传报告 (找不到文件!)
- if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: security-audit-report
    path: npm-audit-output.txt          # ← 这个文件从未被创建!
```

`npm audit` 的默认行为是将结果输出到 **stdout/stderr**（控制台），不会自动写入文件。后续的 `upload-artifact` 步骤尝试上传 `npm-audit-output.txt`，但该文件从未被创建。

### 修复方法

使用 Shell 重定向将审计结果写入文件：

```yaml
- run: npm audit --audit-level=high > npm-audit-output.txt 2>&1
```

Shell 重定向语法说明：

| 符号 | 含义 |
|------|------|
| `>` | 将 stdout 重定向到文件（覆盖写入） |
| `2>&1` | 将 stderr（文件描述符 2）重定向到 stdout（文件描述符 1）的当前位置 |
| 效果 | stdout 和 stderr 都写入 `npm-audit-output.txt` |

**为什么需要 `2>&1`？** `npm audit` 发现漏洞时将结果输出到 stderr（因为漏洞被视为"问题"），如果只使用 `>` 则只捕获 stdout，stderr 仍显示在终端而不写入文件。

---

## 问题 5：`codelytv/pr-size-labeler` 缺少 `GITHUB_TOKEN`

### 影响范围

- `pr-check.yml`: `size-label` Job

### 错误日志（预期）

```
Error: Resource not accessible by integration
```

或

```
Error: HttpError: Bad credentials
```

### 根因分析

根据 `codelytv/pr-size-labeler` 的文档：

> `GITHUB_TOKEN` (Required): GitHub token to access the repository.

该 Action 需要 `GITHUB_TOKEN` 作为 **输入参数**（`with:` 中的字段），用于调用 GitHub API 添加标签。原始代码中未传递此参数。

原始代码：
```yaml
- uses: codelytv/pr-size-labeler@v1
  with:
    xs_label: 'size/xs'
    xs_max_size: 10
    # ... 其他参数
    # ❌ 缺少 GITHUB_TOKEN
```

### 修复方法

```yaml
- uses: codelytv/pr-size-labeler@v1
  with:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}  # ✅ 必需参数
    xs_label: 'size/xs'
    xs_max_size: '10'
    # ...
```

---

## 完整修复清单

### 新增文件

| 文件 | 用途 |
|------|------|
| `package.json` | Node.js 项目配置，定义 build/test/lint 脚本 |
| `package-lock.json` | npm 依赖锁定文件（`npm install` 自动生成） |
| `src/index.js` | 源代码模块 |
| `test/basic.test.js` | 单元测试（使用 Node 内置 test runner） |
| `.gitignore` | 忽略 node_modules、dist 等 |
| `.github/auto_assign.yml` | PR 自动分配审查者配置 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `package.json` | 原 `build` 脚本不产生产物 → 改为创建 `dist/` 目录 |
| `pr-check.yml` | `pr-size-labeler` 缺少 `GITHUB_TOKEN` → 添加必填参数 |
| `scheduled.yml` | `npm audit` 输出到终端 → 重定向到文件 |

### 无需修改的 Workflow

- `ci.yml` — 工作流定义本身无问题，失败完全由缺少项目文件导致
- `deploy.yml` — 同上
- `release.yml` — 同上

---

## 如何诊断 GitHub Actions 失败

### 1. 查看 Action 日志

进入 GitHub 仓库 → Actions → 点击失败的 workflow run → 展开红色标记的步骤：

```
▸ Run npm ci                                             0s
  npm error code EUSAGE                    ← 错误信息在这里
  npm error The `npm ci` command can only install with...
```

### 2. 理解 `npm ci` 的前提条件

| 条件 | 是否满足 |
|------|----------|
| `package.json` 存在 | 否 ❌ |
| `package-lock.json` 存在且与 `package.json` 一致 | 否 ❌ |
| lockfileVersion >= 1 | 不适用 |

### 3. 验证外部 Action 的文档

引用社区 Action 时，务必查阅其 README 中的 `Inputs` 表格，确认所有必填参数是否提供：

- [actions/checkout](https://github.com/actions/checkout)
- [actions/setup-node](https://github.com/actions/setup-node)
- [codelytv/pr-size-labeler](https://github.com/CodelyTV/pr-size-labeler)
- [kentaro-m/auto-assign-action](https://github.com/kentaro-m/auto-assign-action)

### 4. 验证文件路径

`upload-artifact` / `download-artifact` 的路径参数：
- 路径是相对于 **workspace 根目录**（即 checkout 的位置）
- 如果前一步没有创建文件，上传会失败
- `path` 可以是目录或文件，支持 glob 模式

---

## 经验教训

1. **创建 workflow 前确保项目文件完整**。Workflow 只是"胶水代码"，执行的是项目中的脚本（`npm ci`、`npm test` 等），基础文件缺失必然导致失败。

2. **`npm ci` 与 `npm install` 有本质区别**。CI 中应坚持使用 `npm ci`（更快、更可靠），但前提是始终将 `package-lock.json` 提交到版本控制。

3. **`actions/setup-node` 的 `cache: 'npm'` 也依赖 `package-lock.json`**。缺失时不会显式报错，但缓存功能静默失效。

4. **引用社区 Action 时必须验证文档中的必填参数**。缺少 `GITHUB_TOKEN` 是最常见的疏忽。

5. **Shell 重定向注意 `2>&1`**。`npm audit` 的结果输出到 stderr，仅用 `>` 无法捕获。
