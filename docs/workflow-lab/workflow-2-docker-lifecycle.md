# 工作流 2：Docker 全生命周期 — 完整文档

> **文件：** `.github/workflows/docker-full-lifecycle.yml`
>
> **目的：** 一个生产级的 Docker 镜像生命周期工作流，涵盖多架构构建、漏洞扫描、SBOM（软件物料清单）生成、Cosign 无密钥签名、SLSA（软件供应链级别）出处证明、镜像验证、GitHub Release 创建和存储清理。
>
> **读者对象：** 学习 GitHub Actions 和 Docker 安全的开发者和 DevOps 工程师

## 目录

1. [概述](#1-概述)
2. [触发器配置（`on:`）](#2-触发器配置-on)
3. [权限](#3-权限)
4. [环境变量](#4-环境变量)
5. [作业 1：docker-setup](#5-作业-1-docker-setup)
6. [作业 2：docker-lint](#6-作业-2-docker-lint)
7. [作业 3：metadata](#7-作业-3-metadata)
8. [作业 4：build-push](#8-作业-4-build-push)
9. [作业 5：image-scan](#9-作业-5-image-scan)
10. [作业 6：sbom-attest](#10-作业-6-sbom-attest)
11. [作业 7：verify-image](#11-作业-7-verify-image)
12. [作业 8：release](#12-作业-8-release)
13. [作业 9：cleanup](#13-作业-9-cleanup)
14. [Docker 概念参考](#14-docker-概念参考)
15. [GitHub Actions 概念参考](#15-github-actions-概念参考)

---

## 1. 概述

### 本工作流的功能

该工作流实现了一个 **Docker 容器镜像生命周期流水线** — 每个镜像在发布前都要经过构建、扫描、签名、验证和发布。它展示了：

1. **多架构设置** — QEMU 仿真 + BuildKit 用于 amd64/arm64 构建
2. **Dockerfile 静态检查** — Hadolint 最佳实践验证，并上传 SARIF 结果
3. **元数据生成** — 基于 Git 上下文生成符合 OCI 标准的标签和标记
4. **多平台构建与推送** — 并行 amd64/arm64 构建，支持层缓存
5. **漏洞扫描** — Trivy 深度 CVE 扫描 + Docker Scout 策略评估
6. **SBOM（软件物料清单）与签名** — SPDX 物料清单 + Cosign 无密钥签名
7. **镜像验证** — 基于摘要的拉取、签名验证、清单检查
8. **发布创建** — 创建包含所有产物的 GitHub Release
9. **存储清理** — 清理未标记的镜像版本

### 架构图

```
on: workflow_dispatch or release:published
         │
         ▼
  ┌──────────────┐
  │ docker-setup  │  ←── QEMU + Buildx（docker-container 驱动）
  └──────┬───────┘
         │
         ├──────────────────────────┐
         ▼                          ▼
  ┌──────────────┐         ┌────────────────┐
  │  docker-lint  │         │   metadata     │  ←── 并行执行
  │ (Hadolint)    │         │（标签+标记）    │
  └──────┬───────┘         └───────┬────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
          ┌──────────────────┐
          │   build-push      │  ←── 多架构 + 出处证明 + SBOM
          └────────┬─────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
  ┌──────────────┐   ┌──────────────┐
  │  image-scan   │   │ sbom-attest  │  ←── 并行执行
  │(Trivy+Scout)  │   │(SBOM+Cosign) │
  └──────┬───────┘   └──────┬───────┘
         │                    │
         └────────┬──────────┘
                  ▼
         ┌──────────────────┐
         │  verify-image     │  ←── 拉取 + 验证 + 检查
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │     release       │  ←── GitHub Release（可选）
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │     cleanup       │  ←── 清理未标记版本（仅 main 分支）
         └──────────────────┘
```

### 关键设计原则

1. **摘要不可变性优于标签：** 每个使用镜像的作业都使用 SHA256 摘要（`@sha256:...`），而不是标签。标签是可变的，可能被覆盖；摘要是内容寻址的，且对镜像内容唯一。

2. **纵深防御：** 多种扫描工具（Trivy + Docker Scout）提供更广泛的 CVE 覆盖范围。多种签名机制（Cosign + SLSA 证明 + GitHub 证明）提供冗余验证。

3. **左移验证、右移确认：** Dockerfile 静态检查在构建前发现问题。构建后的验证在推送后检测镜像仓库篡改。

4. **作业 DAG 实现并行效率：** 独立作业（docker-lint + metadata，image-scan + sbom-attest）并行运行，以最小化总耗时。

5. **紧急绕过：** `skip-scan` 输入允许在紧急热修复时绕过安全扫描，同时保持所有其他流水线步骤。

---

## 2. 触发器配置（`on:`）

### YAML 代码块

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      image-name:
        description: 'Container image name (default: ghcr.io/${{ github.repository }})'
        required: false
        type: string
      platforms:
        description: 'Target platforms (comma-separated, e.g. linux/amd64,linux/arm64)'
        required: false
        default: 'linux/amd64,linux/arm64'
        type: string
      skip-scan:
        description: 'Skip vulnerability scan (emergency use only)'
        required: false
        default: false
        type: boolean
```

### 逐行说明

**`on:`** — 定义哪些事件触发工作流的顶级键。GitHub Actions 支持多种事件类型，包括 `push`、`pull_request`、`release`、`schedule`、`workflow_dispatch`、`workflow_call`、`repository_dispatch`、`issue_comment`、`registry_package` 等。

**`release:`** — 当 GitHub Release 事件发生时触发。这对于发布与软件官方版本对应的镜像非常有用。

**`types: [published]`** — release 事件的子过滤器。仅在发布被发布时触发（而不是在创建为草稿、编辑或删除时）。其他 release 类型包括：`created`、`edited`、`deleted`、`prereleased`、`unpublished`。

**`workflow_dispatch:`** — 允许从 GitHub UI、REST API 或 CLI（`gh workflow run`）手动触发工作流。这对于在不创建 release 的情况下测试流水线至关重要。

**`inputs:`** — 定义 `workflow_dispatch` 的输入参数。这些参数在 GitHub UI 的"运行工作流"对话框中显示为表单字段。

**`image-name:`** — 用于覆盖容器镜像名称的可选字符串输入。当未提供时，工作流默认为 `ghcr.io/${{ github.repository }}`，展开后为 `ghcr.io/owner/repo-name`。

**`description:`** — 在 GitHub UI 表单中显示的人类可读标签。始终提供清晰的描述，以便团队成员了解每个输入的功能。

**`required: false`** — 用户是否必须提供值。当为 false 时，输入默认为空或指定的 `default` 值。

**`type: string`** — 输入的数据类型。支持的类型：`string`、`number`、`boolean`、`choice`、`environment`。

**`platforms:`** — 用于指定目标构建平台的字符串输入。默认值 `linux/amd64,linux/arm64` 涵盖了两种最常见的服务器架构。AWS Graviton 和 Apple Silicon 使用 arm64；传统服务器使用 amd64。

**`default: 'linux/amd64,linux/arm64'`** — 用户未提供时使用的默认值。对于多架构构建，可以添加诸如 `linux/arm/v7`（树莓派）、`linux/s390x`（IBM 大型机）或 `linux/ppc64le`（PowerPC）等平台。

**`skip-scan:`** — 用于紧急绕过漏洞扫描的布尔输入。将此设置为 `true` 将跳过 `image-scan` 作业。这是一个有意的风险接受机制，适用于安全热修复场景，其中修复本身解决了扫描会检测到的漏洞。

**`type: boolean`** — 在 GitHub UI 中呈现为复选框。有效值：`true` 或 `false`。

### 关键概念

**带类型输入的工作流调度（workflow_dispatch）** 是 GitHub Actions 在运维工作流中最强大的功能之一。输入类型映射到原生 HTML 表单元素：
- `string` → 文本输入字段
- `choice` → 下拉选择（需要 `options:` 数组）
- `boolean` → 复选框
- `number` → 带验证的数字输入

与自动运行的 `pull_request` 或 `push` 触发器不同，`workflow_dispatch` 需要手动发起。它适用于：
- 部署工作流
- 发布流水线
- 维护任务（清理、迁移）
- 测试/调试工作流

`release` 事件与标签有特殊关系。当发布被发布时：
1. 如果不存在匹配的 Git 标签，GitHub 会创建一个与 release 标签匹配的 Git 标签
2. `github.ref` 变量被设置为该标签（例如 `refs/tags/v1.2.3`）
3. `github.event.release` 对象包含所有发布元数据

这就是为什么我们工作流中的 `release` 作业会检查 `github.event_name == 'release'` — 它决定是创建一个新的 release（workflow_dispatch）还是附加到一个现有的 release（release 事件）。

---

## 3. 权限

### YAML 代码块

```yaml
permissions:
  contents: write
  packages: write
  id-token: write
  attestations: write
  security-events: write
```

### 逐行说明

**`permissions:`** — 设置 GITHUB_TOKEN 权限的顶级键。默认情况下，GitHub Actions 授予一个仅具有 `contents: read` 范围的缩减令牌。您必须显式请求其他权限。

**`contents: write`** — 需要用于：
- 推送提交/标签（如果适用）
- 创建 releases（`softprops/action-gh-release`）
- 上传 release 资产
- 读取/写入仓库内容

如果没有 `contents: write`，`release` 作业在尝试创建 GitHub Release 时会失败。

**`packages: write`** — 需要用于：
- 推送容器镜像到 GHCR（`docker/build-push-action`）
- 删除包版本（`actions/delete-package-versions`）
- 任何 GitHub Packages API 写入操作

如果没有 `packages: write`，`build-push` 作业在推送到 GHCR 时会收到 403 错误。

**`id-token: write`** — 需要用于：
- OIDC（OpenID Connect，开放ID连接）令牌生成
- Cosign 无密钥签名（与 Fulcio 交换 OIDC 令牌）
- `actions/attest-build-provenance`（SLSA 证明）
- `slsa-framework/slsa-github-generator`

OIDC 令牌从 GitHub 的 OIDC 提供商 `https://token.actions.githubusercontent.com` 请求获取。Cosign 使用此令牌向 Fulcio（证书颁发机构）证明工作流的身份。

如果没有 `id-token: write`，Cosign 签名和证明步骤将因 OIDC 令牌不可用而失败。

**`attestations: write`** — 需要用于：
- `actions/attest-build-provenance@v2` 在镜像仓库中存储证明
- 创建加密签名的证明对象

这是一个相对较新的权限（随证明操作一起添加）。它控制对证明 API 端点的写入访问。

如果没有 `attestations: write`，构建出处证明步骤将失败。

**`security-events: write`** — 需要用于：
- 上传 SARIF 文件到 GitHub Security 选项卡
- 创建代码扫描告警
- `github/codeql-action/upload-sarif`

SARIF 格式（静态分析结果交换格式）是用于交换静态分析结果的 OASIS 标准。GitHub 接收 SARIF 文件并将其显示为代码扫描告警。

如果没有 `security-events: write`，SARIF 上传步骤将失败并返回 403 错误。

### 关键概念

**GITHUB_TOKEN** 是一个自动生成的、作用域限定在工作流运行范围内的令牌。它：
- 每次工作流运行都重新创建
- 仅在运行期间有效
- 在运行结束时自动过期
- 作为 `secrets.GITHUB_TOKEN` 暴露
- 作用域限定在包含工作流的仓库

最小权限原则也适用于 CI/CD 令牌。切勿设置 `permissions: write-all`。相反，应明确列出仅所需的权限。

**OIDC（OpenID Connect，开放ID连接）** 是一种允许一个系统验证另一个系统身份的身份验证协议。在 GitHub Actions 中，OIDC 允许工作流获取一个令牌，用于证明：
- 它在哪个仓库中运行
- 由哪个工作流文件发起
- 由哪个分支/标签触发
- 由哪个运行 ID 和运行编号标识

此 OIDC 令牌是无密钥签名的基础。工作流不存储私钥（可能泄露），而是使用其临时身份来证明它有权对产物进行签名。

---

## 4. 环境变量

### YAML 代码块

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  TRIVY_SEVERITY: CRITICAL,HIGH
```

### 逐行说明

**`env:`** — 在工作流级别定义环境变量。这些变量可用于工作流中的所有作业和步骤。作业级别和步骤级别的 `env:` 块可以在更窄的范围内覆盖这些值。

**`REGISTRY: ghcr.io`** — 容器镜像仓库主机名。`ghcr.io` 是 GitHub Container Registry（GitHub 容器镜像仓库）。其他可选值：
- `docker.io` — Docker Hub（需要 `DOCKER_USERNAME` 和 `DOCKER_PASSWORD` 密钥）
- `quay.io` — Red Hat Quay
- `<account>.dkr.ecr.<region>.amazonaws.com` — AWS ECR
- `<name>.azurecr.io` — Azure ACR

使用 `env` 变量可以轻松更改镜像仓库，而无需编辑工作流中的多个位置。

**`IMAGE_NAME: ${{ github.repository }}`** — 镜像名称，默认为 GitHub 仓库名称（`owner/repo`）。在 GHCR 中，镜像路径变为 `ghcr.io/owner/repo`。`${{ github.repository }}` 变量是一个内置的 GitHub 上下文变量。

**`TRIVY_SEVERITY: CRITICAL,HIGH`** — Trivy 漏洞扫描的严重级别阈值。只有达到这些级别的漏洞才会导致扫描失败。这是一个有意的选择 — MEDIUM 和 LOW 级别的发现很少需要阻塞构建。

### 关键概念

**GitHub 上下文（`github.*`）：** GitHub Actions 提供了一个丰富的上下文对象，可通过 `${{ github.* }}` 访问。关键变量：
- `github.repository` — 当前仓库（格式：`owner/repo`）
- `github.ref` — 分支或标签引用（格式：`refs/heads/main` 或 `refs/tags/v1.0.0`）
- `github.sha` — 触发工作流的提交 SHA
- `github.actor` — 触发工作流的用户
- `github.run_id` — 唯一的运行编号
- `github.run_number` — 运行次数（每个工作流递增）
- `github.workflow` — 工作流名称
- `github.event_name` — 触发工作流的事件
- `github.event` — 完整的事件负载对象
- `github.token` — GITHUB_TOKEN 本身

**表达式语法（`${{ }}`）：** `${{ }}` 内的任何内容都会被评估为表达式。不能使用任意的 shell 命令 — 仅限 GitHub 表达式语法，包括：
- 三元运算符：`${{ condition && 'value1' || 'value2' }}`
- 逻辑运算符：`==`、`!=`、`&&`、`||`、`!`
- 字符串方法：`startsWith`、`endsWith`、`contains`、`format`
- 对象方法：`join`、`fromJSON`、`toJSON`
- 哈希函数：`hashFiles`

在 `env:` 块中设置的环境变量可在 Shell 步骤中作为标准环境变量（`$REGISTRY`）访问，也可在表达式中作为 `${{ env.REGISTRY }}` 访问。

---

## 5. 作业 1：docker-setup

### YAML 代码块

```yaml
docker-setup:
  runs-on: ubuntu-latest
  outputs:
    builder-name: ${{ steps.buildx.outputs.name }}
  steps:
    - uses: actions/checkout@v4

    - name: 设置 QEMU 用于多架构仿真
      uses: docker/setup-qemu-action@v3
      with:
        platforms: arm64,arm

    - name: 设置 Docker Buildx
      id: buildx
      uses: docker/setup-buildx-action@v3
      with:
        driver: docker-container
        driver-opts: |
          image=moby/buildkit:latest
        buildkitd-flags: --debug

    - name: 检查构建器
      run: |
        echo "构建器名称: ${{ steps.buildx.outputs.name }}"
        echo "驱动: docker-container"
        echo "支持的平台:"
        docker buildx inspect --bootstrap | grep -E "Platforms:|linux/"
```

### 逐行说明

**`docker-setup:`** — 作业 ID。在工作流内必须唯一。其他作业通过 `needs: docker-setup` 或 `${{ needs.docker-setup.outputs.* }}` 引用此作业。

**`runs-on: ubuntu-latest`** — 指定运行环境。`ubuntu-latest` 是默认的 Linux 运行器，预装了 Docker。其他选项包括 `windows-latest`、`macos-latest`、`ubuntu-24.04`、`ubuntu-22.04`、`self-hosted` 或自定义运行器标签。

**`outputs:`** — 定义作业的输出值，下游作业可以使用这些值。输出是由各个步骤写入 `$GITHUB_OUTPUT` 的键值对。

**`builder-name: ${{ steps.buildx.outputs.name }}`** — 一个名为 `builder-name` 的输出，捕获 Buildx 构建器实例名称。该值来自 `id: buildx` 步骤，具体来自该步骤的 `outputs.name`。

**`steps:`** — 作业中的有序步骤列表。每个步骤可以运行命令（`run:`）或使用预构建的操作（`uses:`）。

**`- uses: actions/checkout@v4`** — 标准检出操作。需要因为：
- 运行器以干净的工作空间启动
- 其他步骤需要仓库源代码
- 某些步骤（如 metadata）需要 Git 历史记录以检测标签/分支
- `hashFiles()` 依赖于工作目录中的文件

`actions/checkout@v4` 的关键输入：
- `fetch-depth: 0` — 获取所有历史记录（semver 标签需要）
- `fetch-tags: true` — 随历史记录获取标签
- `persist-credentials: true` — 保存令牌供后续 Git 操作使用
- `path: ./some-dir` — 检出到子目录
- `ref: ${{ github.ref }}` — 检出特定引用

**`- name: 设置 QEMU...`** — 人类可读的步骤名称。显示在 GitHub UI 工作流可视化中。

**`uses: docker/setup-qemu-action@v3`** — Docker 维护的社区操作。它安装 QEMU（快速仿真器）静态二进制文件，并将其注册到 Linux 内核的 binfmt_misc 子系统中。

**`with:`** — 向操作传递输入参数。

**`platforms: arm64,arm`** — 指定要安装哪些架构的仿真器。每个平台需要不同的 QEMU 静态二进制文件。常见值：
- `arm64` — 64 位 ARM（AArch64），AWS Graviton 和 Apple Silicon 使用
- `arm` — 32 位 ARM，树莓派和较老的移动设备使用
- `s390x` — IBM 大型机
- `ppc64le` — PowerPC 小端序
- `riscv64` — RISC-V 64 位（开放标准 ISA）

没有 QEMU，在 amd64 运行器上的 Docker 构建只能生成 amd64 镜像。QEMU 在运行时将 ARM 指令转换为 x86 指令，从而实现跨架构构建。

**`- name: 设置 Docker Buildx`** — 初始化 Docker Buildx，这是 Docker 基于 BuildKit 技术的扩展构建系统。

**`id: buildx`** — 为此步骤分配一个标识符。其他步骤使用此 ID 通过 `${{ steps.buildx.outputs.* }}` 引用此步骤的输出。

**`uses: docker/setup-buildx-action@v3`** — 用于配置 Buildx 的官方 Docker 操作。它处理：
- 创建/选择构建器实例
- 安装 BuildKit（如果需要）
- 配置构建器驱动
- 连接到远程构建器

**`driver: docker-container`** — 指定 Buildx 驱动。这是多架构构建的关键选择：

| 驱动 | 描述 | 多架构 | 缓存导出 | 使用场景 |
|---|---|---|---|---|
| `docker` | 内置 Docker BuildKit（嵌入式） | 否 | 有限 | 简单的本地构建 |
| `docker-container` | 外部 BuildKit 容器 | 是 | 完整 | CI/CD 多架构 |
| `kubernetes` | K8s 集群中的 BuildKit Pod | 是 | 完整 | 企业 CI |
| `remote` | 连接到远程 BuildKit | 是 | 完整 | 共享构建集群 |

`docker-container` 驱动启动一个独立的 BuildKit 容器（`moby/buildkit`）来处理实际构建。这是必需的，因为：
1. 嵌入式的 `docker` 驱动只能为主机构建
2. `docker-container` 支持所有缓存导出类型
3. 它更好地处理并发构建
4. 它支持构建证明（出处、SBOM）

**`driver-opts:`** — 传递给 Buildx 驱动的额外选项。

**`image=moby/buildkit:latest`** — 指定要使用的 BuildKit 镜像。`:latest` 标签方便但不可变。对于生产环境，应固定到特定摘要：`image=moby/buildkit@sha256:abcdef...`。

**`buildkitd-flags: --debug`** — 传递给 BuildKit 守护进程的标志。`--debug` 启用详细日志记录，有助于排查构建故障。对于生产环境，如有需要可考虑使用 `--allow-insecure-entitlement network.host`。

**`- name: 检查构建器`** — 一个诊断步骤，在 CI 日志中显示构建器配置。

**`docker buildx inspect --bootstrap`** — The `--bootstrap` flag ensures the builder
is running (pulls the BuildKit image if needed). This command outputs:
```
Name:   builder-abc123
Driver: docker-container
Nodes:
  Name:      builder-abc1230
  Endpoint:  unix:///var/run/docker.sock
  Status:    running
  Platforms: linux/amd64, linux/arm64, linux/arm/v7, linux/arm/v8, ...
```

**`| grep -E "Platforms:|linux/"`** — Filters the output to show only the relevant
platform lines. This makes the CI log more readable by showing just the architecture
information.

### docker/setup-qemu-action@v3 — Full Capability Reference

Key inputs:
| Input | Default | Description |
|---|---|---|
| `platforms` | `all` | Comma-separated list of platforms to install |
| `image` | `tonistiigi/binfmt:latest` | QEMU binfmt image |
| `install` | `true` | Whether to register binfmt_misc handlers |

What this action does internally:
1. Runs a privileged container with `tonistiigi/binfmt` image
2. The container installs QEMU static binaries to `/proc/sys/fs/binfmt_misc/`
3. Registers QEMU interpreters for each requested platform
4. After this step, `docker run --platform linux/arm64 alpine uname -m` returns `aarch64`

### docker/setup-buildx-action@v3 — Full Capability Reference

Key inputs:
| Input | Default | Description |
|---|---|---|
| `driver` | `docker` | Builder driver (docker, docker-container, kubernetes, remote) |
| `driver-opts` | — | Driver-specific options (image, network, env) |
| `buildkitd-flags` | — | Flags for BuildKit daemon |
| `buildkitd-config` | — | BuildKit daemon config TOML |
| `endpoint` | — | Remote builder endpoint |
| `install` | `false` | Set builder as default for `docker build` |

Key outputs:
| Output | Description |
|---|---|
| `name` | Builder instance name |
| `platforms` | Comma-separated supported platforms |

### Why This Specific Approach

QEMU emulation is chosen over cross-compilation for several reasons:
1. **Transparency:** The Dockerfile builds the same way for every platform — no platform-specific
   branches or conditionals
2. **Compatibility:** Some packages don't cross-compile cleanly (native addons, C extensions)
3. **Simplicity:** One Dockerfile, one build command, multiple architectures
4. **Verification:** The same build process runs under emulation as on native hardware

The tradeoff is build speed — QEMU emulation is approximately 2-5x slower than native
execution for arm64 builds on amd64 runners. For projects with many native extensions,
consider using native arm64 runners with GitHub's larger hosted runners or self-hosted
options.

---

## 6. 作业 2：docker-lint

### YAML 代码块

```yaml
docker-lint:
  needs: docker-setup
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: 使用 Hadolint 对 Dockerfile 进行静态检查
      uses: hadolint/hadolint-action@v3
      with:
        dockerfile: Dockerfile
        failure-threshold: warning
        format: sarif
        output-file: hadolint-results.sarif

    - name: 上传 SARIF 到 GitHub Security
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: hadolint-results.sarif
        category: hadolint
```

### 逐行说明

**`needs: docker-setup`** — 声明对 `docker-setup` 作业的依赖。此作业在 `docker-setup` 成功完成之前不会启动。虽然此作业不直接使用任何 Buildx/QEMU 功能，但该依赖确保了 DAG 可视化中的正确排序。

**`uses: hadolint/hadolint-action@v3`** — 一个封装了 Hadolint Dockerfile 检查器的社区操作。Hadolint 是一个静态分析工具，用于检查 Dockerfile 是否符合最佳实践。

**`dockerfile: Dockerfile`** — 要检查的 Dockerfile 路径。相对于仓库根目录。该操作读取此文件并应用 100 多条 lint 规则。

**`failure-threshold: warning`** — 确定哪个严重级别会导致操作失败。选项：
- `error` — 仅实际错误使构建失败
- `warning` — 警告和错误使构建失败（更严格）
- `info` — 信息级别的发现也会使构建失败
- `style` — 样式建议也会使构建失败
- `none` — 从不基于 lint 结果失败

使用 `warning` 是一个很好的平衡 — 它能捕获实际问题而不过于教条。

**`format: sarif`** — lint 结果的输出格式。SARIF（静态分析结果交换格式）是一种 OASIS 标准 JSON 格式。其他格式：
- `tty` — 终端彩色输出（默认）
- `json` — 机器可读的 JSON
- `checkstyle` — Checkstyle XML 格式
- `gitlab_codeclimate` — GitLab 格式
- `codeclimate` — Code Climate 格式

**`output-file: hadolint-results.sarif`** — 输出文件路径。此文件随后上传到 GitHub Security 扫描。

**`uses: github/codeql-action/upload-sarif@v3`** — 将 SARIF 文件上传到 GitHub，使结果显示在 Security 选项卡中。尽管属于 CodeQL 操作包，但它可以处理任何 SARIF 文件，而不仅仅是 CodeQL 结果。

**`sarif_file: hadolint-results.sarif`** — 要上传的 SARIF 文件路径。

**`category: hadolint`** — 一个分类标签，用于在 Security 选项卡中将这些结果与其他扫描工具（CodeQL、Trivy 等）区分开来。

### 重要 Hadolint 规则说明

**DL3006 — 始终显式指定版本标签：** 切勿使用 `FROM ubuntu`（隐式 `:latest`）。始终使用 `FROM ubuntu:22.04` 或 `FROM node:20-bookworm-slim`。`:latest` 标签是可变的，可能意外更改，导致构建失败。

**DL3008 — 在 apt-get install 中固定软件包版本：** 使用 `apt-get install curl=7.68.0-1` 而不是 `apt-get install curl`。没有版本固定，构建将不可重现。

**DL3009 — 删除 apt-get 列表：** 在 `apt-get update` 之后，始终在同一 RUN 层中运行 `rm -rf /var/lib/apt/lists/*` 以保持镜像较小。

**DL3018 — 在 apk add 中固定软件包版本：** Alpine 的 `apk` 应使用固定版本，如 `apk add curl=7.79.1-r0`。

**DL3020 — 使用 COPY 而不是 ADD：** `ADD` 具有特殊行为（自动解压归档文件、获取 URL），可能导致意外结果。除非需要 ADD 的特殊功能，否则对本地文件使用 `COPY`。

**DL3025 — 对 ENTRYPOINT/CMD 使用 JSON 数组形式：** 使用 `CMD ["node", "app.js"]` 而不是 `CMD node app.js`。Shell 形式将命令包装在 `/bin/sh -c` 中，无法正确处理信号。

**DL3042 — 使用 --no-install-recommends：** 始终在 `apt-get install` 中添加 `--no-install-recommends`，以避免拉取推荐但不必要的软件包。

**DL4006 — 为 RUN --mount 模式设置 SHELL：** 使用 `RUN --mount=type=cache` 时，设置 SHELL 以使用 `-e` 标志进行正确的错误处理。

### 为什么采用这种方法

Hadolint 在构建之前运行，提供快速反馈而不消耗构建时间。尽早捕获诸如缺少 `USER` 指令或未固定基础镜像等问题，可以防止安全问题进入生产环境。

SARIF 上传确保 Dockerfile 质量问题与其他漏洞告警一起出现在 GitHub 的 Security 选项卡中。这为所有仓库安全问题提供了集中视图。

---

## 7. 作业 3：metadata

### YAML 代码块

```yaml
metadata:
  needs: docker-setup
  runs-on: ubuntu-latest
  outputs:
    tags:     ${{ steps.meta.outputs.tags }}
    labels:   ${{ steps.meta.outputs.labels }}
    json:     ${{ steps.meta.outputs.json }}
    version:  ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}
    digest:   ${{ steps.meta.outputs.digest }}
  steps:
    - uses: actions/checkout@v4

    - name: 生成 Docker 元数据
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        labels: |
          org.opencontainers.image.title=${{ github.event.repository.name }}
          org.opencontainers.image.description=Docker Full Lifecycle workflow demo image
          org.opencontainers.image.vendor=${{ github.repository_owner }}
          org.opencontainers.image.licenses=MIT
          maintainer=${{ github.repository_owner }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=semver,pattern={{major}}
          type=sha,format=short
          type=raw,value=latest,enable={{is_default_branch}}
          type=raw,value=edge,enable=${{ github.ref == 'refs/heads/dev' }}
        flavor: |
          latest=false
          prefix=
          suffix=

    - name: 提取备用版本号
      id: meta-latest
      run: |
        if [ -z "${{ steps.meta.outputs.version }}" ]; then
          VERSION=$(node -p "try{require('./package.json').version}catch(e){'latest'}" 2>/dev/null || echo "latest")
          echo "version=${VERSION}" >> "$GITHUB_OUTPUT"
        else
          echo "version=${{ steps.meta.outputs.version }}" >> "$GITHUB_OUTPUT"
        fi

    - name: 打印生成的元数据
      run: |
        echo "Tags:"
        echo "${{ steps.meta.outputs.tags }}" | tr ',' '\n' | sed 's/^/  /'
        echo "Labels:"
        echo "${{ steps.meta.outputs.labels }}" | tr ',' '\n' | sed 's/^/  /'
        echo "Version: ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}"
```

### 逐行说明

**`outputs:`** — 声明此作业为下游消费生成的内容。

**`tags: ${{ steps.meta.outputs.tags }}`** — 生成的 Docker 标签，以逗号分隔的字符串形式提供（例如 `ghcr.io/owner/repo:main,ghcr.io/owner/repo:sha-abc123`）。

**`labels: ${{ steps.meta.outputs.labels }}`** — OCI 标记，以逗号分隔的字符串形式提供（例如 `org.opencontainers.image.created=2024-01-01T00:00:00Z,...`）。

**`json: ${{ steps.meta.outputs.json }}`** — 包含所有元数据的完整 JSON 输出。

**`version: ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}`** — 检测到的版本号。使用短路求值：如果 `meta-latest` 产生了版本号，则使用它；否则回退到 `meta` 步骤的版本号。这处理了没有 Git 标签的情况。

**`uses: docker/metadata-action@v5`** — Docker 官方元数据生成操作。它读取 Git 上下文并生成符合 OCI 标准的标签和标记。

**`images:`** — 基础镜像名称。所有生成的标签都以此作为前缀。例如，使用 `images: ghcr.io/owner/repo`，`type=sha` 标签会生成 `ghcr.io/owner/repo:sha-abc123`。

**`labels:`** — 要应用的自定义 OCI 标记。该操作还会自动生成以下标记：
- `org.opencontainers.image.created` — RFC 3339 构建时间戳
- `org.opencontainers.image.source` — 仓库 URL
- `org.opencontainers.image.version` — 检测到的版本号
- `org.opencontainers.image.revision` — Git 提交 SHA
- `org.opencontainers.image.licenses` — 来自仓库
- `org.opencontainers.image.title` — 镜像标题
- `org.opencontainers.image.description` — 仓库描述
- `org.opencontainers.image.ref.name` — Git 引用名称

**`tags:`** — 标签生成策略。每行是一个标签规则。

**`type=ref,event=branch`** — 从分支名称创建标签。对于 `main` 分支，生成 `ghcr.io/owner/repo:main`。

**`type=ref,event=pr`** — 从 PR 编号创建标签。对于 PR #42，生成 `ghcr.io/owner/repo:pr-42`。

**`type=semver,pattern={{version}}`** — 从类似 `v1.2.3` 的 Git 标签生成 `ghcr.io/owner/repo:1.2.3`。`v` 前缀会自动去除。

**`type=semver,pattern={{major}}.{{minor}}`** — 从 `v1.2.3` 生成 `1.2`。范围标签允许用户拉取特定次版本的最新补丁。

**`type=semver,pattern={{major}}`** — 从 `v1.2.3` 生成 `1`。仅主版本标签让用户可以跟踪最新的主版本发布。

**`type=sha,format=short`** — 从提交 SHA 生成 `sha-abc123`。短格式为 7 个字符。

**`type=raw,value=latest,enable={{is_default_branch}}`** — `latest` 标签，但仅在默认分支上。`enable` 条件防止非 main 分支获得 `latest` 标签。

**`type=raw,value=edge,enable=${{ github.ref == 'refs/heads/dev' }}`** — 为 dev 分支提供的 `edge` 标签，允许拉取前沿镜像。

**`flavor:`** — 控制自动标签行为。

**`latest=false`** — 阻止操作自动添加 `latest`。我们通过上面的 `type=raw` 规则显式管理 `latest`。

**`prefix=`** 和 **`suffix=`** — 不为标签添加前缀或后缀。

**`提取备用版本号：`** — 一个纯 Shell 步骤，当没有 Git 标签时从 `package.json` 提取版本号。这确保了下游作业始终有 `version` 输出。

**`echo "version=${VERSION}" >> "$GITHUB_OUTPUT"`** — 设置步骤输出 `version`。`$GITHUB_OUTPUT` 文件是 GitHub Actions 设置步骤输出的约定方式。

### docker/metadata-action@v5 — 完整功能参考

关键输入：
| 输入 | 默认值 | 描述 |
|---|---|---|
| `images` | （必需） | 基础镜像名称，空格分隔 |
| `tags` | — | 标签生成规则 |
| `labels` | — | 自定义标记 |
| `flavor` | — | 标签风格（latest, prefix, suffix） |
| `sep-tags` | `,` | 多标签输出的分隔符 |
| `sep-labels` | `,` | 多标记输出的分隔符 |
| `bake-target` | `gha-docker` | Bake 目标文件 |
| `github-token` | GITHUB_TOKEN | 用于 API 访问的令牌 |

标签类型：
| 类型 | 示例 | 描述 |
|---|---|---|
| `type=ref,event=branch` | `main` | 分支引用 |
| `type=ref,event=pr` | `pr-42` | 拉取请求编号 |
| `type=ref,event=tag` | `v1.2.3` | Git 标签（原始） |
| `type=semver,pattern={{version}}` | `1.2.3` | 语义版本解析 |
| `type=sha` | `sha-a1b2c3d` | 提交 SHA |
| `type=raw,value=my-tag` | `my-tag` | 自定义静态标签 |
| `type=schedule` | `nightly` | 计划运行标签 |
| `type=match,pattern=...` | — | 正则匹配组 |
| `type=pep440,pattern={{version}}` | — | Python PEP 440 |

### 为什么采用这种方法

集中式元数据生成确保所有下游作业使用一致的标签和标记。没有这个，build-push 作业、release 作业和任何通知步骤都需要各自实现自己的标签逻辑，导致漂移和不一致。

多级 semver 方案（版本号、主版本.次版本、主版本）为消费者提供了灵活性：
- `docker pull myimage:1.2.3` — 固定到精确版本
- `docker pull myimage:1.2` — 获取 1.2 的最新补丁
- `docker pull myimage:1` — 获取 1 的最新次版本

---

## 8. 作业 4：build-push

### YAML 代码块

```yaml
build-push:
  needs: [metadata, docker-lint]
  runs-on: ubuntu-latest
  outputs:
    digest: ${{ steps.build.outputs.digest }}
    tags: ${{ steps.build.outputs.tags }}
    image-with-digest: ${{ steps.build.outputs.digest && format('{0}@{1}', env.REGISTRY, steps.build.outputs.digest) || steps.build-full-ref.outputs.ref }}
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
      with:
        driver: docker-container

    - name: Build and push multi-platform image
      id: build
      uses: docker/build-push-action@v6
      with:
        context: .
        file: ./Dockerfile
        platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}
        push: true
        tags: ${{ needs.metadata.outputs.tags }}
        labels: ${{ needs.metadata.outputs.labels }}
        provenance: true
        sbom: true
        cache-from: type=gha
        cache-to: type=gha,mode=max
        build-args: |
          BUILDKIT_CONTEXT_KEEP_GIT_DIR=1
          VERSION=${{ needs.metadata.outputs.version }}
        annotations: ${{ needs.metadata.outputs.labels }}

    - name: Output image reference
      id: build-full-ref
      run: |
        echo "ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}" >> "$GITHUB_OUTPUT"
        echo "Image built and pushed successfully"
        echo "  Registry: ${{ env.REGISTRY }}"
        echo "  Image: ${{ env.IMAGE_NAME }}"
        echo "  Digest: ${{ steps.build.outputs.digest }}"
        echo "  Tags: ${{ needs.metadata.outputs.tags }}"
        echo "  Platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}"
```

### 逐行说明

**`needs: [metadata, docker-lint]`** — 依赖于 metadata 和 docker-lint 两个作业。这确保了在投入 CI 构建时间之前，lint 检查已通过。

**`image-with-digest: ${{ steps.build.outputs.digest && format(...) || steps.build-full-ref.outputs.ref }}`** — 一个防御性表达式，生成带有摘要的完整镜像引用。使用短路求值：如果 `digest` 已设置，则格式化完整引用；否则使用备用输出。

**`uses: docker/login-action@v3`** — 向容器镜像仓库进行身份验证。对于 GHCR，凭据为：
- `username: ${{ github.actor }}` — 触发工作流的 GitHub 用户
- `password: ${{ secrets.GITHUB_TOKEN }}` — 自动生成的令牌

GITHUB_TOKEN 的作用域由 `permissions` 块决定。由于我们设置了 `packages: write`，此令牌拥有对 GHCR 的推送权限。

**`uses: docker/build-push-action@v6`** — 核心构建操作。它使用 BuildKit 编排整个 Docker 构建过程。

**`context: .`** — Docker 构建上下文目录。这作为构建输入发送到 BuildKit 守护进程。只有上下文中的文件在构建期间可用。

**`file: ./Dockerfile`** — Dockerfile 的路径，相对于上下文目录。

**`platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}`** — 目标平台。当 `workflow_dispatch` 提供了平台时使用它们；否则默认为 `linux/amd64,linux/arm64`。BuildKit 并行构建每个平台。

**`push: true`** — 构建后将镜像推送到镜像仓库。推送包括平台特定镜像和多架构清单列表。

**`tags: ${{ needs.metadata.outputs.tags }}`** — 来自 metadata 作业的标签。

**`labels: ${{ needs.metadata.outputs.labels }}`** — 来自 metadata 作业的 OCI 标记。

**`provenance: true`** — 生成 SLSA Build Level 2 出处证明作为镜像内层。这会创建一个证明清单，记录：
- 构建器 ID（GitHub Actions 运行器）
- 构建配置（工作流文件、输入）
- 源代码仓库和提交 SHA
- 镜像摘要
- 构建时间戳

该证明作为与镜像关联的独立清单存储在镜像仓库中。可以使用 `docker buildx imagetools inspect <image>` 查看。

**`sbom: true`** — 生成软件物料清单（SBOM）作为镜像内层。这记录了镜像中安装的所有软件包，包括：
- 操作系统软件包（来自 apt、apk、yum 等）
- 语言特定软件包（npm、pip、gem 等）
- 软件包版本和许可证

同时将 `provenance` 和 `sbom` 设置为 `true` 相当于向 `docker buildx build` 命令传递 `--attest type=provenance` 和 `--attest type=sbom`。

**`cache-from: type=gha`** — 在构建开始时从 GitHub Actions 缓存恢复缓存的层。当只做了微小更改时，这能显著加速后续构建。

**`cache-to: type=gha,mode=max`** — 在构建结束时将构建缓存保存到 GitHub Actions 缓存。`mode=max` 导出所有中间层，最大化缓存复用。

缓存类型：
| 类型 | 后端 | 最适合 |
|---|---|---|
| `gha` | GitHub Actions 缓存 | 简单 CI，无需外部基础设施 |
| `registry` | 容器镜像仓库 | 跨 CI 系统共享 |
| `local` | 本地文件系统 | 自托管运行器 |
| `s3` | AWS S3 | 企业 CI |
| `azblob` | Azure Blob 存储 | Azure 原生 CI |

**`build-args:`** — 通过 `ARG` 指令传递给 Dockerfile 的构建参数。`BUILDKIT_CONTEXT_KEEP_GIT_DIR=1` 保留构建上下文中的 `.git` 目录，这对于在构建期间提取版本信息非常有用。

**`annotations: ${{ needs.metadata.outputs.labels }}`** — 镜像清单的额外注解。这些作为 OCI 注解嵌入到清单元数据中。

### 关键输出

**`digest`** — 多架构清单列表的 SHA256 摘要。这不是平台特定镜像的摘要 — 它引用指向每个平台清单的 OCI 索引（清单列表）。

摘要示例：`sha256:a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1`

### docker/build-push-action@v6 — 完整功能参考

除上述已使用的输入外，其他关键输入：
| 输入 | 描述 |
|---|---|
| `target` | 多阶段构建目标 |
| `no-cache` | 禁用层缓存 |
| `pull` | 始终拉取基础镜像 |
| `network` | 构建网络模式 |
| `secret-files` | 安全挂载密钥文件 |
| `secrets` | 构建密钥（环境变量） |
| `ssh` | SSH 代理转发 |
| `extra-from` | COPY --from 的源镜像 |
| `github-token` | 用于身份验证的 GitHub 令牌 |
| `export-cache` | 导出缓存到其他后端 |
| `import-cache` | 从其他后端导入缓存 |
| `outputs` | 构建输出（type=local, type=tar 等） |

### 为什么采用这种方法

`provenance: true` 和 `sbom: true` 的组合非常重要，因为这些证明是在构建过程中（而非构建后）生成的。BuildKit 在构建时拥有所需的所有信息（每条 `RUN` 命令、每个已安装的软件包）。构建后的 SBOM 生成（如我们使用 anchore/sbom-action 所做的那样）分析最终镜像，可能会遗漏中间构建产物或多阶段构建细节。

选择 GHA 缓存后端（`type=gha`）而非 `type=registry` 是因为：
- 无需额外存储成本（使用现有的 GHA 缓存配额）
- 自动缓存键管理（无需手动失效）
- 无需镜像仓库身份验证即可工作
- 缓存隔离到仓库级别

其代价：GHA 缓存在仓库中的所有工作流之间共享，因此缓存密集型工作流可能会驱逐 Docker 层缓存。

---

## 9. 作业 5：image-scan

### YAML 代码块

```yaml
image-scan:
  needs: build-push
  runs-on: ubuntu-latest
  if: ${{ github.event.inputs.skip-scan != 'true' }}
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        scan-type: image
        scan-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        format: sarif
        output: trivy-results.sarif
        exit-code: 1
        severity: ${{ env.TRIVY_SEVERITY }}
        vuln-type: os,library
        ignore-unfixed: true
        scanners: vuln,secret

    - name: Upload Trivy SARIF results
      if: always()
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: trivy-results.sarif
        category: trivy

    - name: Run Docker Scout
      id: scout
      uses: docker/scout-action@v1
      with:
        command: quickview,recommendations
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        severity: ${{ env.TRIVY_SEVERITY }}
        github-token: ${{ secrets.GITHUB_TOKEN }}
        exit-code: true

    - name: Print scan summary
      if: always()
      run: |
        echo "=== Trivy Scan Summary ==="
        echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
        echo "Severity threshold: ${{ env.TRIVY_SEVERITY }}"
        echo "SARIF results uploaded to GitHub Security tab"
```

### 逐行说明

**`if: ${{ github.event.inputs.skip-scan != 'true' }}`** — 当 `skip-scan` 输入设置为 `true` 时，有条件地跳过整个作业。比较是字符串比较，因为工作流调度输入始终是字符串，即使是布尔类型也是如此。

**`uses: aquasecurity/trivy-action@master`** — Aqua Security 的官方 Trivy 操作。Trivy（发音为"trivee"）是一个全面的容器漏洞扫描器。

**`scan-type: image`** — 告诉 Trivy 扫描容器镜像。其他模式：
- `fs` — 文件系统扫描（IaC 配置错误、密钥）
- `repo` — Git 仓库扫描
- `config` — Kubernetes/YAML/Terraform 配置扫描
- `sbom` — SBOM 文件扫描

**`scan-ref:`** — 要扫描的目标。使用 `@digest` 确保我们扫描的是刚刚构建的镜像，而不是可能被推送到同一标签的其他镜像。

**`format: sarif`** — SARIF 输出用于 GitHub Security 选项卡集成。其他格式：
- `table` — 人类可读的表格（最适合本地运行）
- `json` — 机器可读的 JSON
- `template` — 自定义 Go 模板

**`exit-code: 1`** — 当在指定的严重级别发现漏洞时，以退出码 1 退出。设置为 `0` 将报告发现但不使构建失败。

**`severity: ${{ env.TRIVY_SEVERITY }}`** — 仅报告 CRITICAL 和 HIGH 级别的漏洞。这防止了构建因 MEDIUM 和 LOW 级别的发现而失败。

**`vuln-type: os,library`** — 扫描操作系统级别软件包（apt、apk、rpm）和应用程序库（npm、pip、gem 等）。

**`ignore-unfixed: true`** — 仅报告已有修复方案的漏洞。这减少了尚无补丁的漏洞带来的噪音。

**`scanners: vuln,secret`** — 启用漏洞扫描和密钥检测。密钥检测会查找镜像中的硬编码凭据、API 密钥和令牌。

**`if: always()`** — 即使前面的步骤失败也运行此步骤。这确保了即使 Trivy 发现漏洞并以退出码 1 退出，SARIF 结果也能被上传。

**`uses: docker/scout-action@v1`** — Docker 自己的镜像分析工具。Docker Scout 超越了 CVE 扫描，提供上下文相关的建议。

**`command: quickview,recommendations`** — 运行两个 Scout 命令：
- `quickview` — 按严重级别汇总漏洞
- `recommendations` — 减少漏洞的建议（例如，基础镜像升级）

**`exit-code: true`** — 如果发现超过严重阈值，以非零退出码退出。

### Trivy 与 Docker Scout：互补的方法

| 方面 | Trivy | Docker Scout |
|---|---|---|
| 数据库 | NVD、GHSA、OSV、RedHat 等 | Docker 自己的 CVE 数据库 |
| 速度 | 快（编译的 Go 二进制文件） | 中等（云端分析） |
| 策略引擎 | 自定义脚本 | 内置策略 |
| 建议 | 否（仅报告） | 是（可操作的修复建议） |
| 格式 | 多种（SARIF、JSON、表格） | 文本/报告 |
| 许可 | 开源（Apache 2.0） | 有限制的免费层级 |

同时运行两个扫描器提供纵深防御。一个工具的数据库可能包含另一个尚未索引的 CVE，而 Docker Scout 的建议提供了 Trivy 不具备的可操作修复步骤。

### Trivy 严重级别

| 级别 | 含义 | 示例 |
|---|---|---|
| CRITICAL（严重） | 利用简单，危害范围广 | 面向网络服务中的 RCE（远程代码执行） |
| HIGH（高危） | 可利用，影响显著 | SQL 注入、身份验证绕过 |
| MEDIUM（中危） | 需要特定条件 | 带 CSP 的 XSS、本地权限提升 |
| LOW（低危） | 影响有限，难以利用 | 通过错误消息泄露信息 |
| UNKNOWN（未知） | 尚未评级 | 没有 CVSS 评分的新 CVE |

### 为什么采用这种方法

`exit-code: 1` 设置将 Trivy 发现转化为构建门禁 — 如果存在 CRITICAL 或 HIGH 级别的漏洞，工作流将失败。这防止了存在漏洞的镜像进入发布阶段。

SARIF 上传上的 `if: always()` 是关键：即使 Trivy 使构建失败，我们也希望漏洞数据显示在 GitHub 的 Security 选项卡中，以便分类和跟踪。

`skip-scan` 绕过机制用于紧急热修复（例如，修补生产环境中的严重漏洞）。在这种情况下，修复本身解决了 CVE，因此扫描将是多余的。然而，这创建了审计线索 — 每次绕过都在工作流运行历史中可见。

---

## 10. 作业 6：sbom-attest

### YAML 代码块

```yaml
sbom-attest:
  needs: build-push
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Generate SBOM
      id: sbom
      uses: anchore/sbom-action@v0
      with:
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        format: spdx-json
        output-file: ${{ github.event.repository.name }}-sbom.spdx.json
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Install Cosign
      uses: sigstore/cosign-installer@v3
      with:
        cosign-release: 'v2.4.1'

    - name: Sign container image with Cosign keyless signing
      env:
        COSIGN_EXPERIMENTAL: false
      run: |
        cosign sign \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --yes \
          --annotations "repo=${{ github.repository }}" \
          --annotations "workflow=${{ github.workflow }}" \
          --annotations "ref=${{ github.ref }}"

    - name: Sign SBOM with Cosign
      run: |
        cosign attest-blob \
          ${{ github.event.repository.name }}-sbom.spdx.json \
          --yes \
          --sign ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}

    - name: Attach build provenance
      uses: actions/attest-build-provenance@v2
      with:
        subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        subject-digest: ${{ needs.build-push.outputs.digest }}
        push-to-registry: true
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Upload SBOM and attestation artifacts
      uses: actions/upload-artifact@v4
      with:
        name: sbom-and-attestation
        path: |
          ${{ github.event.repository.name }}-sbom.spdx.json
          ${{ github.event.repository.name }}-sbom.spdx.json.bundle
        retention-days: 90
```

### 逐行说明

**`uses: anchore/sbom-action@v0`** — Anchore 的 SBOM 生成操作。它使用 Syft（一个开源 SBOM 工具）生成容器镜像的详细物料清单。

**`format: spdx-json`** — 输出格式。SPDX（Software Package Data Exchange，软件包数据交换）是用于 SBOM 交换的 ISO 标准（ISO/IEC 5962:2021）。JSON 变体是最机器可读的格式。其他格式：
- `cyclonedx-json` — CycloneDX 标准（OWASP）
- `spdx-tag-value` — SPDX 标签:值格式（更易读但更难解析）

**`output-file:`** — 生成的 SBOM 文件路径。以仓库名称命名以便清晰识别：`my-repo-sbom.spdx.json`。

**`image:`** — 要分析的镜像。使用 `@digest` 实现不可变引用。

**`uses: sigstore/cosign-installer@v3`** — 安装 Cosign 二进制文件。Cosign 是 Sigstore 项目的一部分，该项目提供了一套用于软件供应链安全性的工具。

**`cosign-release: 'v2.4.1'`** — 固定特定的 Cosign 版本。这确保了跨工作流运行的可重现行为。版本 2.4.1 是一个稳定版本，自 v2.0 起无密钥签名已正式发布（GA）。

### Cosign 无密钥签名 — 深度解析

**`cosign sign` 期间发生的事情：**

1. **OIDC 令牌请求：** Cosign 向 GitHub Actions 请求 OIDC 令牌。令牌的身份信息包括：
   - 仓库：`github.com/owner/repo`
   - 工作流：`.github/workflows/docker-full-lifecycle.yml`
   - 引用：`refs/heads/main`

2. **Fulcio 证书交换：** Cosign 将 OIDC 令牌发送到 Fulcio（Sigstore 的证书颁发机构）。Fulcio 使用 GitHub 的 OIDC 提供商验证令牌，并颁发短期有效的 X.509 代码签名证书。该证书包括：
   - 主题：OIDC 身份（工作流身份）
   - 颁发者：`https://token.actions.githubusercontent.com`
   - 有效期：约 10 分钟
   - 公钥：Cosign 生成的临时密钥对

3. **签名生成：** Cosign：
   - 生成临时密钥对（私钥 + 公钥）
   - 使用私钥对镜像摘要进行签名
   - 将签名、公钥和证书包装为标准容器签名格式
   - 将签名作为单独的清单上传到容器镜像仓库

4. **Rekor 透明度日志：** Cosign 在 Rekor（Sigstore 的透明度日志）中创建一个条目。这提供了：
   - 公开可审计性（任何人都可以搜索 Rekor 查找签名）
   - 时间戳证明（签名在特定时间存在）
   - 抗密钥泄露能力（旧签名仍然有效）

**为什么称为"无密钥"：** 私钥是临时的 — 它仅在签名操作期间存在于内存中，从未被存储。公钥嵌入在签名证书中，该证书由 Fulcio 的根 CA 签名。没有人需要管理、轮换或分发长期有效的签名密钥。

**`cosign attest-blob`** — 对任意文件（blob）进行签名并生成证明包。与将签名附加到容器的 `cosign sign` 不同，此命令生成独立的 `.bundle` 文件。

**`--sign ${{ env.REGISTRY }}/...@digest`** — 将 blob 证明链接到特定的容器镜像。这证明了 SBOM 属于这个确切的镜像。

**`uses: actions/attest-build-provenance@v2`** — GitHub 自己的证明机制。这与 Cosign 分开，提供：
- SLSA Build Level 2 出处证明
- 与 GitHub 证明 API 的集成
- 可通过 GitHub 的信任服务验证

**`subject-name:`** 和 **`subject-digest:`** — 标识正在被证明的产物。这些必须完全匹配，验证才能成功。

**`push-to-registry: true`** — 将证明与 GHCR 中的镜像一起推送。这以 OCI 制品的形式将证明存储在与镜像相同的仓库中。

### SBOM 格式对比

| 方面 | SPDX | CycloneDX |
|---|---|---|
| 标准机构 | Linux Foundation（ISO/IEC 5962） | OWASP |
| 最新版本 | 2.3 | 1.6 |
| 重点 | 法律/许可证合规 | 安全漏洞关联 |
| 字段 | 包名称、版本、许可证、关系 | SPDX 全部内容外加：漏洞、利用、风险评分 |
| 漏洞映射 | 外部引用 | 内置漏洞章节 |
| 工具支持 | 广泛（Syft、Trivy、Fossa） | 广泛（Syft、OWASP 工具） |
| GitHub 集成 | 支持 | 支持 |

这里选择 SPDX 是因为它是更成熟的标准，具有更广泛的 GitHub 集成，但两种格式都服务于相同的基本目的。

### 为什么采用这种方法

三种独立的签名/证明机制提供了纵深防御：
1. **Cosign sign：** 容器镜像的标准 Sigstore 签名
2. **Cosign attest-blob：** 将 SBOM 链接到镜像的签名证明
3. **GitHub 证明：** 通过 GitHub 基础设施提供的 SLSA 出处证明

每种机制使用不同的信任根，因此任何一个被攻破都不会影响其他机制。这对于受监管环境尤其重要，在这些环境中需要通过多个独立渠道证明产物的出处。

---

## 11. 作业 7：verify-image

### YAML 代码块

```yaml
verify-image:
  needs: [build-push, sbom-attest]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Pull image by digest
      run: |
        docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        echo "Successfully pulled image by digest"

    - name: Inspect multi-arch manifest list
      run: |
        echo "=== Manifest List ==="
        docker buildx imagetools inspect ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        echo ""
        echo "=== Platform Breakdown ==="
        docker buildx imagetools inspect --raw ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} | jq -r '.manifests[] | "  \(.platform.os)/\(.platform.architecture) → \(.digest)"' 2>/dev/null || echo "  (jq not available, raw output above)"

    - name: Verify Cosign signature
      run: |
        cosign verify \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --certificate-identity-regexp "https://github.com/${{ github.repository }}/.github/workflows/.*@${{ github.ref }}" \
          --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
          --verbose
        echo "Signature verification passed"

    - name: Docker Scout final check
      uses: docker/scout-action@v1
      with:
        command: quickview
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Print verification summary
      run: |
        echo "=== Image Verification Summary ==="
        echo "Status: PASSED"
        echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
        echo "Signature: Verified (Cosign keyless)"
        echo "Multi-arch: Confirmed"
        echo "Scout check: Passed"
        echo ""
        echo "Pull command: docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
```

### 逐行说明

**`docker pull ...@digest`** — 使用内容可寻址的摘要（而非可变的标签）拉取镜像。这保证我们获取到的是刚刚构建和推送的确切字节。

**`docker buildx imagetools inspect`** — 显示多架构镜像的 OCI 索引（清单列表）。输出示例：
```
Name:      ghcr.io/owner/repo@sha256:abc...
MediaType: application/vnd.oci.image.index.v1+json
Manifests:
  [0] linux/amd64  digest: sha256:def...
  [1] linux/arm64  digest: sha256:ghi...
```

**`docker buildx imagetools inspect --raw`** — 显示清单列表的原始 JSON。通过 `jq` 管道提取仅平台信息，以可读格式呈现。

**`cosign verify`** — 验证镜像上的 Cosign 签名。在无密钥模式下，此过程：
1. 从镜像仓库获取签名
2. 验证证书链（临时证书 -> Fulcio 中间证书 -> Fulcio 根证书）
3. 检查证书的 OIDC 身份是否与预期的工作流身份匹配
4. 验证 Rekor 透明度日志条目
5. 确认签名覆盖镜像摘要

**`--certificate-identity-regexp`** — 预期身份的正则表达式模式。我们不匹配精确身份（这将包括特定的工作流运行），而是使用正则表达式匹配此仓库此分支上的任何工作流。

**`--certificate-oidc-issuer "https://token.actions.githubusercontent.com"`** — 验证 OIDC 令牌是由 GitHub Actions 颁发的，而不是由不同的 OIDC 提供商颁发的。这防止了身份欺骗。

### 为什么在推送后验证？

在推送和验证之间，老练的攻击者可能：
1. 用被篡改的镜像覆盖镜像标签
2. 篡改镜像仓库存储后端
3. 利用镜像仓库漏洞交换清单

通过按摘要（而非标签）拉取并根据身份验证签名，我们能够检测所有这些场景：
- 摘要不匹配 -> 拉取失败或签名验证失败
- 标签覆盖 -> 无关紧要，我们使用摘要
- 镜像仓库篡改 -> 签名验证会捕获

## 12. 作业 8：release

### YAML 代码块

```yaml
release:
  needs: [verify-image, image-scan]
  runs-on: ubuntu-latest
  if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'release' }}
  steps:
    - uses: actions/checkout@v4

    - name: Download all artifacts
      uses: actions/download-artifact@v4
      with:
        path: release-artifacts/
        merge-multiple: true

    - name: List release artifacts
      run: |
        echo "=== Release Artifacts ==="
        find release-artifacts/ -type f -ls

    - name: Create GitHub Release
      uses: softprops/action-gh-release@v2
      with:
        tag_name: ${{ github.event_name == 'release' && github.event.release.tag_name || format('v{0}', needs.metadata.outputs.version) }}
        name: Release ${{ needs.metadata.outputs.version }}
        body: |
          ## Docker Image

          ### Pull by digest (recommended — immutable):
          ```bash
          docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
          ```

          ### Pull by tag:
          ```bash
          docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.metadata.outputs.version }}
          ```
          ...
        files: |
          release-artifacts/**/*
        draft: ${{ github.event_name != 'release' }}
        prerelease: ${{ !startsWith(github.ref, 'refs/tags/v') }}
        generate_release_notes: true
        make_latest: true
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 逐行说明

**`if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'release' }}`** — 仅在 main 分支推送或由 GitHub Release 事件触发时创建 release。这防止了每个开发/功能分支推送都创建 release。

**`uses: actions/download-artifact@v4`** — 下载先前从 sbom-attest 作业（以及任何其他产物）上传的产物。

**`path: release-artifacts/`** — 存储下载产物的目录。

**`merge-multiple: true`** — 下载多个产物时，将其合并到单个目录中，而不是为每个产物创建单独的子目录。

**`uses: softprops/action-gh-release@v2`** — 一个流行的社区操作，用于创建和管理 GitHub Releases。

**`tag_name:`** — release 的 Git 标签。当由 `release` 事件触发时，使用现有 release 的标签。对于 `workflow_dispatch`，从版本号创建新标签。

**`draft: ${{ github.event_name != 'release' }}`** — 当手动触发时创建为草稿，允许在发布前进行审查。

**`generate_release_notes: true`** — 根据自上次 release 以来的提交历史自动生成发布说明。

**`make_latest: true`** — 将此 release 标记为"最新"release。

**`files:`** — 要附加到 release 的文件 glob 模式。所有下载的产物都被包含。

### 为什么采用这种方法

条件行为（草稿 vs. 已发布）处理两种不同的使用场景：
1. 由 `release` 事件触发 — 产物附加到现有的已发布 release
2. 由 `workflow_dispatch` 触发 — 创建用于审查的草稿 release

发布正文中包含带有摘要和标签两种变体的 Docker 拉取命令，使消费者能够轻松拉取正确的镜像。

---

## 13. 作业 9：cleanup

### YAML 代码块

```yaml
cleanup:
  needs: release
  runs-on: ubuntu-latest
  if: ${{ github.ref == 'refs/heads/main' }}
  steps:
    - name: Delete untagged package versions
      uses: actions/delete-package-versions@v5
      with:
        package-name: ${{ env.IMAGE_NAME }}
        package-type: container
        min-versions-to-keep: 5
        delete-only-untagged-versions: true
        token: ${{ secrets.GITHUB_TOKEN }}

    - name: Report cleanup
      run: |
        echo "=== Package Cleanup ==="
        echo "Package: ${{ env.IMAGE_NAME }}"
        echo "Action: Deleted untagged versions"
        echo "Min kept: 5"
        echo "Registry: ${{ env.REGISTRY }}"
```

### 逐行说明

**`uses: actions/delete-package-versions@v5`** — GitHub 的官方操作，用于从 GitHub Packages 中删除旧的包版本。

**`package-name: ${{ env.IMAGE_NAME }}`** — 要清理的包。对于 GHCR，这与镜像名称相同。

**`package-type: container`** — 指定包类型。选项包括 `container`、`npm`、`maven`、`rubygems`、`nuget`、`docker`。

**`min-versions-to-keep: 5`** — 安全网：永远不会删除到低于 5 个版本。这确保你始终有几个最近的版本可用于回滚。

**`delete-only-untagged-versions: true`** — 关键安全标志：仅删除没有标签指向的"孤立"版本。有标签的版本被保留。

### 何时创建未标记版本

未标记版本在 GHCR 中积累的情况：
1. 新构建使用与先前构建相同的标签推送 — 旧版本失去其标签
2. 标签从仓库中删除 — 所有具有该标签的版本变为未标记
3. 包在仓库之间迁移 — 迁移过程中可能丢失标签

如果不进行清理，这些孤立版本将无限期地消耗存储配额。

### 为什么采用这种方法

`delete-only-untagged-versions: true` 标志是最重要的安全机制。它防止意外删除可能在以下环境中被引用的有标签版本：
- 生产部署清单
- 按标签拉取的 CI/CD 流水线
- 开发者的本地 Docker 缓存

条件 `github.ref == 'refs/heads/main'` 将清理限制在 main 分支运行，防止 PR 或 dev 分支上的清理作业干扰活跃开发。

---

## 14. Docker 概念参考

### 14.1 多架构构建（amd64 vs arm64）

**为什么两种架构很重要：**

| 架构 | 通用名称 | 典型硬件 |
|---|---|---|
| `linux/amd64` | x86_64 | Intel Xeon、AMD EPYC、Intel Core |
| `linux/arm64` | AArch64 | AWS Graviton、Apple M 系列、Ampere Altra |

行业正在向 arm64 迁移，因为其更高的每瓦性能：
- AWS Graviton 实例比同等 x86 实例便宜 20-40%
- Apple Silicon（M1/M2/M3/M4）基于 arm64
- 主流云提供商为所有服务类别提供 arm64 选项

为 amd64 构建的 Docker 镜像在没有仿真的情况下无法在 arm64 上运行。Docker 镜像是架构特定的，因为它们包含编译后的二进制文件。

**多架构镜像的工作原理：**

OCI 镜像清单列表（也称为"胖清单"）是一个 JSON 文档，引用多个平台特定的清单：

```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.index.v1+json",
  "manifests": [
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:amd64-specific-digest",
      "platform": { "architecture": "amd64", "os": "linux" }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:arm64-specific-digest",
      "platform": { "architecture": "arm64", "os": "linux" }
    }
  ]
}
```

当用户运行 `docker pull ghcr.io/owner/repo:latest` 时，Docker：
1. 获取清单列表
2. 读取用户的 CPU 架构（`uname -m`）
3. 选择匹配的平台特定清单
4. 仅拉取该平台的层

这对最终用户是透明的 — 他们始终使用相同的镜像名称，Docker 自动处理架构选择。

**为什么需要 QEMU 仿真：**

GitHub Actions 运行器仅为 amd64（x86_64）。要构建 arm64 镜像，我们需要：
1. **交叉编译：** 为 Dockerfile 中的每种语言设置交叉编译器
2. **QEMU 仿真：** 通过指令转换器透明地运行 arm64 二进制文件

QEMU 仿真更简单但更慢。QEMU 在运行时将每条 arm64 指令转换为等效的 x86 指令序列。对于 CPU 密集型构建（编译、软件包安装），速度会慢 2-5 倍。

对于频繁构建的项目，考虑：
- GitHub 更大的 [arm64 托管运行器](https://github.com/features/github-actions)
- 自托管 arm64 运行器（例如，在 AWS Graviton 实例上）

### 14.2 BuildKit 与 docker-container 驱动

**什么是 BuildKit？**

BuildKit 是 Docker 的下一代构建子系统。它在 Docker 18.09 中引入，并在 Docker 23.0 中成为默认构建器。与旧版构建器相比的关键改进：

| 能力 | 旧版构建器 | BuildKit |
|---|---|---|
| 并发构建 | 单队列 | 并行 |
| 层缓存 | 基础 | 高级（多后端） |
| 多阶段构建 | 可用 | 优化（跳过未使用的阶段） |
| SSH 挂载 | 否 | 是 |
| 密钥挂载 | 否 | 是（不会出现在镜像历史中） |
| 缓存挂载 | 否 | 是（apt、npm 等） |
| SBOM/出处证明 | 否 | 是（通过证明） |
| 多架构 | 有限 | 完整 |

**BuildKit 的工作原理：**

BuildKit 使用客户端-服务器架构：
1. `buildctl` 客户端（或 Docker CLI）向 BuildKit 守护进程发送构建定义
2. 守护进程将构建作为操作 DAG（有向无环图）处理（而非线性脚本）
3. 每个操作都被缓存，可以在构建之间共享
4. 在依赖允许的情况下，操作并行运行

**docker 与 docker-container 驱动：**

`docker` 驱动使用嵌入在 Docker 守护进程中的 BuildKit。它方便但有限：嵌入式 BuildKit 与 Docker 的运行时操作共享资源，不支持高级功能。

`docker-container` 驱动启动一个专用的 BuildKit 容器。该容器：
- 作为独立进程运行，拥有自己的资源限制
- 支持所有缓存导出类型（gha、registry、local、s3、azblob）
- 可以使用自定义 buildkitd.toml 进行配置
- 支持 SBOM 和出处证明
- 通过 QEMU 注册实现多架构构建

### 14.3 Docker 层缓存

**Docker 层缓存的工作原理：**

每条 Dockerfile 指令都会创建一个层。Docker 根据内容哈希缓存每一层。构建时，Docker 检查具有相同哈希的层是否已存在于缓存中。如果是，则重用缓存的层，而不是重新执行指令。

**缓存失效规则：**
1. 如果某一层的缓存未命中，所有后续层也会未命中（缓存链断裂）
2. 当文件内容更改时，`COPY`/`ADD` 层失效
3. 当命令或前一层更改时，`RUN` 层失效
4. `ARG`/`ENV` 更改根据其在 Dockerfile 中的位置决定失效

**优化策略 — 按更改频率排序 Dockerfile 指令：**
```
# Rarely changes — cached almost always
FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# Changes with package.json — cache invalidated when deps change
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Changes on every source edit — last for maximum cache reuse
COPY src/ ./src/
COPY dist/ ./dist/
CMD ["node", "dist/index.js"]
```

**GitHub Actions 缓存后端（`type=gha`）：**

GHA 缓存后端将构建缓存存储在 GitHub 的 Actions 缓存基础设施中。关键特性：
- **范围：** 仓库级别，在所有工作流之间共享
- **持久性：** 自上次访问起最多 7 天
- **大小限制：** 因套餐而异（免费：10GB，付费：包含在分钟数中）
- **驱逐策略：** 超过限制时，最近最少使用（LRU）算法

**`mode=max` vs `mode=min` 缓存导出：**

| 模式 | 缓存的层 | 最适合 |
|---|---|---|
| `mode=max` | 所有中间层 | 高变更率，需要最大复用 |
| `mode=min` | 仅最终镜像层 | Dockerfile 稳定，需要更小的缓存 |

`mode=max` 推荐用于 CI，因为：
- 它缓存所有中间层，而不仅仅是最终镜像
- 当一层更改时，只需要重建该层
- 后续构建在几秒内完成，而非几分钟

**缓存后端对比：**

| 后端 | 设置 | 速度 | 共享 | 成本 |
|---|---|---|---|---|
| `type=gha` | 零（内置） | 快 | 同一仓库 | 免费 |
| `type=registry` | 需要仓库认证 | 中等 | 任何仓库 | 仓库存储费用 |
| `type=local` | 本地文件系统 | 最快 | 自托管运行器 | 免费 |
| `type=s3` | AWS 凭据 | 中等 | 跨 CI | S3 存储费用 |
| `type=azblob` | Azure 凭据 | 中等 | 跨 CI | Azure 存储费用 |

### 14.4 清单列表与摘要固定

**什么是清单列表（OCI 索引）？**

OCI 镜像索引（通常称为"清单列表"或"胖清单"）是一个 JSON 文档，引用多个平台特定的清单。它是使 `docker pull` 能够自动为任何架构选择正确镜像的机制。

**清单列表结构（OCI 格式）：**

OCI 镜像索引包含：
- `mediaType`：始终为 `application/vnd.oci.image.index.v1+json`
- `manifests`：描述符对象数组，每个包含：
  - `mediaType`：对平台特定清单的引用
  - `digest`：平台特定清单的 SHA256
  - `size`：所引用清单的大小
  - `platform`：操作系统、架构、变体（例如 `linux/arm64/v8`）
  - `annotations`：可选元数据

**标签与摘要 — 根本区别：**

| 属性 | 标签 | 摘要 |
|---|---|---|
| 可变性 | 是（可被覆盖） | 否（内容寻址） |
| 人类可读 | 是（`v1.2.3`） | 否（`sha256:a1b2...`） |
| 唯一性 | 不唯一（多个标签，一个镜像） | 唯一（一个摘要，一个镜像） |
| 安全性 | 可能被标签劫持 | 不可变引用 |
| 拉取语法 | `image:tag` | `image@sha256:...` |

**为什么在生产中使用摘要固定：**

1. **不可变性：** 今天标记为 `v1.2.3` 的镜像明天可能被不同的内容覆盖。摘要 `sha256:a1b2...` 始终指向相同的内容。

2. **供应链安全：** 如果攻击者获得镜像仓库的写入权限，他们可以用被篡改的镜像覆盖标签。他们无法在不重新构建的情况下更改摘要背后的内容。

3. **部署一致性：** 使用摘要引用时，集群中的每个节点拉取完全相同的镜像内容。基于标签的拉取可能会在部署期间因标签更新而产生竞态条件，获取不同版本。

4. **验证：** 签名附加到摘要，而非标签。经过验证的摘要签名证明正是该内容被签名。

### 14.5 OCI 注解与标记

OCI 注解是可以附加到镜像、清单和索引的键值元数据。它们由 [OCI Image Spec](https://github.com/opencontainers/image-spec) 规范定义。

**标准 OCI 注解（预定义）：**

| 注解 | 描述 |
|---|---|
| `org.opencontainers.image.created` | 构建时间戳（RFC 3339） |
| `org.opencontainers.image.authors` | 联系信息 |
| `org.opencontainers.image.url` | 了解更多信息的 URL |
| `org.opencontainers.image.documentation` | 文档 URL |
| `org.opencontainers.image.source` | 源代码 URL |
| `org.opencontainers.image.version` | 打包软件的版本 |
| `org.opencontainers.image.revision` | 版本控制修订版本（提交 SHA） |
| `org.opencontainers.image.vendor` | 分发镜像的供应商 |
| `org.opencontainers.image.licenses` | SPDX 许可证标识符 |
| `org.opencontainers.image.ref.name` | 引用名称（类似标签） |
| `org.opencontainers.image.title` | 人类可读的标题 |
| `org.opencontainers.image.description` | 人类可读的描述 |
| `org.opencontainers.image.base.digest` | 基础镜像的摘要 |
| `org.opencontainers.image.base.name` | 基础镜像的引用 |

**标记的使用方式：**

1. **发现：** 用户可以在镜像仓库中按标记搜索镜像
2. **合规：** 标记证明哪个版本和来源产生了镜像
3. **自动化：** 工具可以读取标记以确定镜像出处
4. **文档：** 嵌入的元数据消除了外部查找的需要

### 14.6 Cosign 无密钥签名

**Sigstore 生态系统：**

Cosign 是 Sigstore 的一部分，Sigstore 是一套用于签名和验证软件的工具。生态系统包括：

| 组件 | 作用 |
|---|---|
| **Cosign** | 用于签名容器镜像和 blob 的 CLI 工具 |
| **Fulcio** | 颁发短期代码签名证书的证书颁发机构（CA） |
| **Rekor** | 用于记录签名的透明度日志 |
| **Gitsign** | 使用 Sigstore 进行 Git 提交签名 |
| **Policy Controller** | 用于签名验证的 Kubernetes 准入控制器 |

**无密钥签名端到端流程：**

```
1. 工作流启动 → GitHub 生成 OIDC 令牌
                         │
2. cosign sign → 向 GitHub 请求 OIDC 令牌
                         │
3. 与 Fulcio 交换 → OIDC 令牌证明身份
     Fulcio 颁发短期 X.509 证书
     证书包含：公钥、OIDC 身份、Fulcio 链
                         │
4. 加密签名镜像摘要
     使用临时私钥（签名后删除）
                         │
5. 上传到镜像仓库：签名 + 证书 + 链
     作为与镜像关联的独立清单存储
                         │
6. Rekor 条目：签名 + 证书 + 时间戳的哈希
     公开账本证明签名在此时间存在
```

**签名证明的内容：**

当有人验证签名时，他们确认：
1. 镜像由持有绑定到 OIDC 身份的临时密钥的人签名
2. OIDC 身份与预期的工作流/仓库匹配
3. 使用时证书是有效的（在其短生命周期内）
4. 签名在声称的时间记录在 Rekor 中

**它不证明的内容：**
- 镜像没有漏洞（应使用 Trivy）
- 镜像经过了人工审查（两人审查覆盖这一点）
- 构建是封闭/可重现的（SLSA L3+ 覆盖这一点）

### 14.7 SLSA 出处级别

**SLSA（软件产物的供应链级别）** 是一个安全框架，定义了递增的供应链安全级别：

| 级别 | 要求 | 本工作流 |
|---|---|---|
| **L0** | 无保证 | |
| **L1** | 构建过程已记录 | 是（工作流文件） |
| **L2** | 签名的出处证明 + OIDC 认证 | 是（attest-build-provenance） |
| **L3** | 托管构建 + 隔离 | 部分满足（GitHub Actions 是托管的） |
| **L4** | 封闭构建 + 两人审查 + 完整依赖 | 否 |

我们的工作流达到 SLSA Build Level 2，因为：
- 出处证明作为加密签名的证明生成
- 证明使用 OIDC 身份（而非共享密钥）
- 构建托管在 GitHub Actions 上（而非开发者的笔记本）
- 源代码仓库和提交被记录

要达到 L3，我们需要：
- 构建隔离（构建期间无网络访问）
- 预先声明的依赖关系

要达到 L4，我们还需要：
- 所有更改需两人审查
- 封闭构建（无外部网络访问）
- 完整的依赖关系图

### 14.8 SBOM（软件物料清单）

**SBOM 包含的内容：**

容器镜像的 SPDX 2.3 SBOM 包括：

1. **文档信息：** 创建者（工具）、创建时间戳、SPDX 版本
2. **包信息：** 对于镜像中的每个包：
   - 包名称和版本
   - 包供应商（谁创建/维护了它）
   - 包下载位置
   - 包许可证（SPDX 标识符）
   - 包版权文本
   - 外部引用（CVE URL、主页）
3. **关系信息：** 包之间的关系：
   - `DESCENDANT_OF` — 包衍生自另一个包
   - `DEPENDENCY_OF` — 包是一个依赖项
   - `CONTAINS` — 镜像包含此包

**SBOM 对安全的重要性：**

1. **漏洞关联：** 当宣布新的 CVE 时，你可以检查你的 SBOM 以确定是否受影响，而无需逐个扫描每个镜像

2. **许可证合规：** 跟踪你的依赖项使用的开源许可证

3. **供应链透明度：** 了解软件中的每个组件，包括传递性依赖

4. **监管合规：** 美国行政命令 14028 及类似法规要求政府软件提供 SBOM

### 14.9 Trivy 漏洞扫描

**Trivy 的工作原理：**

Trivy 维护一个本地漏洞数据库，聚合来自以下来源的数据：
- NVD（美国国家漏洞数据库）
- RedHat CVE 数据库
- Debian 安全跟踪器
- Alpine CVE 数据库
- GitHub 安全公告（GHSA）
- OSV（开源漏洞）
- AWS ECR 漏洞数据
- Go 漏洞数据库
- RustSec 公告数据库
- Photon CVE 数据库
- SUSE CVRF/CVE 数据库
- Ubuntu CVE 跟踪器
- Chainguard CVE 数据库

对于镜像中的每个包，Trivy：
1. 识别包名称和版本
2. 在其漏洞数据库中查找包
3. 返回影响此版本的所有 CVE
4. 应用严重级别过滤器和修复可用性过滤器
5. 以请求的格式报告结果

**Trivy 可用的扫描器：**

| 扫描器 | 检测内容 | 示例发现 |
|---|---|---|
| `vuln` | 已知漏洞 | curl 中的 CVE-2024-1234 |
| `secret` | 硬编码的密钥 | AWS 密钥、GitHub 令牌 |
| `misconfig` | 基础设施配置错误 | 容器以 root 身份运行 |

### 14.10 Docker Scout

**Docker Scout 与 Trivy 的区别：**

Docker Scout 是一个基于策略的分析工具，它：
- 分析镜像层和包清单
- 提供策略评估（不仅仅是 CVE 列表）
- 提供可操作的建议（基础镜像升级）
- 与 Docker Hub 和 Docker Desktop 集成
- 拥有独立的漏洞数据库

**Scout 命令：**

| 命令 | 描述 |
|---|---|
| `quickview` | 按严重级别汇总漏洞 |
| `compare` | 将镜像与基线进行比较 |
| `recommendations` | 建议减少漏洞的操作 |
| `policy` | 针对组织的安全策略进行评估 |
| `cves` | 详细的 CVE 信息 |
| `sync` | 同步镜像到 Scout 进行远程分析 |

---

## 15. GitHub Actions 概念参考

### 15.1 带类型输入的工作流调度（workflow_dispatch）

`workflow_dispatch` 允许使用用户提供的输入手动触发工作流。输入类型在 GitHub Actions UI 中呈现为原生 HTML 表单元素：

**字符串输入**呈现为文本字段：
```yaml
platforms:
  description: 'Target platforms'
  required: false
  default: 'linux/amd64,linux/arm64'
  type: string
```

**布尔输入**呈现为复选框：
```yaml
skip-scan:
  description: 'Skip vulnerability scan'
  required: false
  default: false
  type: boolean
```

**选择输入**呈现为下拉菜单：
```yaml
environment:
  description: 'Target environment'
  required: true
  type: choice
  options:
    - staging
    - production
```

输入通过 `${{ github.event.inputs.<name> }}` 访问。重要提示：所有输入都是字符串，即使是布尔类型也是如此。比较布尔输入时应使用字符串比较：
```yaml
if: ${{ github.event.inputs.skip-scan != 'true' }}
```

### 15.2 权限块

`permissions` 块控制 GITHUB_TOKEN 的作用域。默认情况下，在没有 GitHub Pages 的仓库中，令牌只有 `contents: read` 权限。

**此工作流中使用的权限范围：**

| 范围 | 操作 |
|---|---|
| `contents: write` | 创建 release、上传资产、推送标签 |
| `packages: write` | 推送镜像到 GHCR、管理包版本 |
| `id-token: write` | 请求 OIDC 令牌用于 Cosign/SLSA |
| `attestations: write` | 存储构建出处证明 |
| `security-events: write` | 上传 SARIF 到 Security 选项卡 |

**最小权限模式：** 始终遵循最小权限原则。从最小权限开始，仅添加所需内容：

```yaml
permissions:
  contents: read     # 默认 — 检出源码
  # ... 仅添加你的工作流需要的内容
```

### 15.3 作业输出

作业可以通过 `outputs` 将数据传递给下游作业。这对于在作业之间传递摘要、标签和版本信息至关重要。

**定义输出（在产生数据的作业中）：**
```yaml
job-name:
  outputs:
    my-output: ${{ steps.my-step.outputs.my-value }}
  steps:
    - id: my-step
      run: echo "my-value=some-data" >> "$GITHUB_OUTPUT"
```

**消费输出（在下游作业中）：**
```yaml
downstream-job:
  needs: job-name
  steps:
    - run: echo "${{ needs.job-name.outputs.my-output }}"
```

**作业输出规则：**
1. 输出必须在作业的 `outputs:` 块中声明
2. 值通过 `$GITHUB_OUTPUT` 从步骤中获取
3. 输出只能是字符串（不支持复杂对象）
4. 任何声明了 `needs: <producer>` 的作业都可以访问输出
5. 输出是只读的 — 下游作业不能修改它们

### 15.4 Needs（作业依赖）

`needs:` 关键字在作业之间创建依赖关系，形成有向无环图（DAG）。GitHub Actions 自动并行化没有依赖关系的作业。

**单一依赖：**
```yaml
job-b:
  needs: job-a
```
Job-b 仅在 job-a 成功完成后启动。

**多重依赖：**
```yaml
job-c:
  needs: [job-a, job-b]
```
Job-c 仅在 job-a 和 job-b 都完成后启动。

**隐式并行：** `docker-lint` 和 `metadata` 作业都依赖 `docker-setup`，但互不依赖，因此它们自动并行运行。

**DAG 执行规则：**
1. 没有 `needs:` 的作业立即启动（根级作业）
2. 单一 `needs:` 的作业在依赖作业完成后启动
3. 多个 `needs:` 的作业等待所有依赖完成
4. 如果依赖失败，依赖作业将被跳过（除非 `if: always()`）
5. 循环依赖在解析时被检测到并导致错误

### 15.5 if: 条件

`if:` 关键字控制作业或步骤是否运行。它评估 GitHub 表达式，仅当表达式为真时才运行。

**作业级条件（跳过整个作业）：**
```yaml
image-scan:
  if: ${{ github.event.inputs.skip-scan != 'true' }}
```

**步骤级条件（跳过单个步骤）：**
```yaml
- name: Upload SARIF
  if: always()  # 即使前面的步骤失败也运行
```

**常用条件表达式：**

| 表达式 | 评估结果 |
|---|---|
| `always()` | 始终运行，即使依赖项失败 |
| `success()` | 仅当前面所有步骤都成功时运行（默认） |
| `failure()` | 仅当前面有步骤失败时运行 |
| `cancelled()` | 仅在运行被取消时运行 |
| `github.ref == 'refs/heads/main'` | 仅在 main 分支 |
| `startsWith(github.ref, 'refs/tags/')` | 仅用于标签推送 |
| `github.event_name == 'release'` | 仅当由 release 触发时 |
| `contains(github.event.issue.labels.*.name, 'bug')` | Issue 有 'bug' 标签 |

**重要提示：** 在 YAML 中，裸露的 `if:` 值如 `if: always()` 可能被解析为布尔值。始终将 GitHub 表达式包裹在 `${{ }}` 中：
```yaml
if: ${{ always() }}
```
没有 `${{ }}`，YAML 可能将 `always()` 解释为字符串或抛出错误。

### 15.6 用于默认值的 env

工作流、作业或步骤级别的 `env:` 块用于设置环境变量：

```yaml
env:
  REGISTRY: ghcr.io           # 工作流级默认值
  TRIVY_SEVERITY: CRITICAL,HIGH

job:
  env:
    JOB_VAR: value            # 作业级覆盖
  steps:
    - env:
        STEP_VAR: value       # 步骤级覆盖
      run: echo $STEP_VAR
```

**变量优先级（最高优先）：**
1. 步骤级 `env:` — 覆盖所有
2. 作业级 `env:` — 覆盖工作流默认值
3. 工作流级 `env:` — 基准
4. 通过在步骤中使用 `$GITHUB_ENV` 设置的环境变量

### 15.7 表达式语法

**`${{ }}` 语法规则：**

在 `${{ }}` 内部，可以使用：
- 字面量：字符串（用引号）、数字、布尔值
- 上下文对象：`github.*`、`env.*`、`needs.*`、`steps.*`、`secrets.*`、`inputs.*`
- 函数：`contains()`、`startsWith()`、`endsWith()`、`format()`、`join()`、`hashFiles()`
- 运算符：`==`、`!=`、`&&`、`||`、`!`、`<`、`>`、`+`、`-`、`*`、`/`

**重要规则：**
1. `${{ }}` 在步骤运行之前被评估（对于 `if:` 在解析时，对于步骤内容在运行时）
2. `run:` 中使用 `${{ }}` 的 Shell 命令，在 Shell 看到它们之前表达式已被评估
3. 始终在 Shell 上下文中引用表达式：`echo "${{ env.REGISTRY }}"`（而不是 `echo ${{ env.REGISTRY }}`，后者在值包含空格时可能出错）

**`secrets` 上下文：**

密钥通过 `${{ secrets.SECRET_NAME }}` 访问。GITHUB_TOKEN 始终可通过 `${{ secrets.GITHUB_TOKEN }}` 获取。其他密钥必须在仓库的 Settings > Secrets and variables > Actions 中配置。

**用于跨作业引用的 `needs` 上下文：**

```yaml
${{ needs.metadata.outputs.tags }}
${{ needs.build-push.outputs.digest }}
```

结构为：`needs.<job-id>.outputs.<output-name>`。

### 15.8 OIDC 认证

**什么是 OIDC，为什么需要它？**

OpenID Connect（OIDC，开放ID连接）是 OAuth 2.0 协议之上的身份层。在 GitHub Actions 中，OIDC 允许工作流获取一个令牌，向外部服务（如 Sigstore 的 Fulcio）证明其身份，而无需存储任何长期有效的密钥。

**OIDC 在 GitHub Actions 中的工作原理：**

```yaml
permissions:
  id-token: write    # OIDC 令牌生成所需
```

当设置了 `id-token: write` 时：
1. GitHub Actions 暴露一个 OIDC 令牌端点，URL 存储在环境变量 `ACTIONS_ID_TOKEN_REQUEST_URL` 中
2. 工作流向此端点请求令牌，提供工作流运行身份的证明（仓库、引用、运行 ID）
3. 外部服务可以使用 GitHub 的 OIDC 公钥验证此令牌

**OIDC 令牌包含的内容（声明）：**

```json
{
  "sub": "repo:owner/repo:ref:refs/heads/main",
  "aud": "sigstore",
  "iss": "https://token.actions.githubusercontent.com",
  "job_workflow_ref": "owner/repo/.github/workflows/workflow.yml@refs/heads/main",
  "runner_environment": "github-hosted",
  "repository": "owner/repo",
  "ref": "refs/heads/main",
  "sha": "commit-sha"
}
```

对于 Cosign，关键声明是：
- `job_workflow_ref` — 正在运行哪个工作流文件
- `repository` — 哪个仓库触发了运行
- `ref` — 哪个分支/标签触发了运行

这些声明在签名期间嵌入到 Fulcio 证书中，并在验证期间提取。

---

## 快速参考：创建的关键文件

| 文件 | 用途 |
|---|---|
| `.github/workflows/docker-full-lifecycle.yml` | 工作流定义 |
| `.github/workflow-lab/docs/workflow-2-docker-lifecycle.md` | 本文档 |

## 文档结束

---

## 16. Dockerfile 扩展优化指南

### 16.1 基础镜像选择

选择正确的基础镜像是 Docker 开发中最重要的决策之一。基础镜像决定了安全面、镜像大小、构建时间和运行时行为。

**镜像大小对比（近似值，针对 Node.js 应用）：**

| 基础镜像 | 近似大小 | 包含包 | 使用场景 |
|---|---|---|---|
| `node:22` (full) | ~1.1 GB | Full build toolchain | Development, CI |
| `node:22-slim` | ~250 MB | Minimal + glibc | Production (needs glibc) |
| `node:22-alpine` | ~180 MB | musl libc + apk | Production (smallest) |
| `node:22-bookworm-slim` | ~260 MB | Debian 12 slim | Production (Debian base) |
| `scratch` (distroless) | ~0 MB | Nothing | Go binary, static apps |

**建议：**
- Use `-slim` variants for general production use — they strip unnecessary packages while
  retaining glibc compatibility
- Use Alpine for smallest possible images, but test thoroughly — musl libc can cause
  subtle compatibility issues with native Node.js addons
- Use `bookworm-slim` or `bullseye-slim` (Debian-based) when you need specific apt packages
- Avoid `:latest` — pin to a specific version tag or better, a digest

**安全考虑：**
- Smaller images = fewer packages = smaller attack surface
- Each package in the image is a potential CVE vector
- Alpine images typically have fewer CVEs because they have fewer packages
- Regular base image updates are critical — a patched base image fixes hundreds of CVEs

### 16.2 多阶段构建

多阶段构建在单个 Dockerfile 中使用多个 `FROM` 语句。只有最后一个阶段生成运行时镜像；前面的阶段用于构建，可以使用具有完整工具链的不同基础镜像。

```dockerfile
# Stage 1: Build
FROM node:22 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Production
FROM node:22-slim AS production
WORKDIR /app
RUN addgroup --system app && adduser --system app
COPY --from=builder --chown=app:app /app/dist ./dist
COPY --from=builder --chown=app:app /app/node_modules ./node_modules
USER app
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

**多阶段构建的好处：**
1. **显著更小的镜像：** 最终镜像仅包含运行时依赖项，不包含 TypeScript 编译器、开发依赖项或构建工具
2. **每个阶段使用不同的基础镜像：** 构建阶段使用 `node:22`（完整版，需要编译器），生产阶段使用 `node:22-slim`（最小化）
3. **安全隔离：** 具有已知漏洞的构建工具（如较旧版本的 npm）被排除在最终镜像之外
4. **COPY --from 选择精确的产物：** 仅复制所需的特定文件 — 不污染构建上下文

### 16.3 层优化策略

**合并相关操作以减少层数：**

```dockerfile
# BAD — 4 layers, 4x the space for apt lists
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y ca-certificates
RUN rm -rf /var/lib/apt/lists/*

# GOOD — 1 layer, one filesystem snapshot
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
```

**利用 Docker 缓存挂载来优化包管理器：**

```dockerfile
# Cache npm packages across builds (BuildKit only)
RUN --mount=type=cache,target=/root/.npm \
    npm ci --only=production

# Cache apt packages across builds (BuildKit only)
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y curl
```

**优化 COPY 顺序以获得最大缓存命中：**

```dockerfile
# 1. First, copy dependency definitions (changes rarely)
COPY package.json package-lock.json ./
# 2. Install dependencies (cached unless package.json changes)
RUN npm ci
# 3. Last, copy source code (changes every commit)
COPY . .
```

### 16.4 非 root 用户最佳实践

以 root 身份运行容器是一个众所周知的安全反模式。如果攻击者利用以 root 身份运行的容器中的应用程序漏洞，他们将获得容器的 root 访问权限，并可能获得宿主系统的访问权限。

```dockerfile
# Create a non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Set ownership of application files
COPY --chown=app:app . .

# Switch to the non-root user
USER app
```

**为什么这很重要：**
- 以 root 身份运行的容器具有与宿主机 root 相同的权限（有些限制）
- 被攻破的 root 容器可以通过内核漏洞逃逸到宿主机
- 非 root 用户无法绑定特权端口（<1024）— Kubernetes 可以映射这些端口
- 许多安全扫描器（包括 Trivy）将 root 容器标记为 HIGH 严重级别

### 16.5 HEALTHCHECK 指令

`HEALTHCHECK` 指令告诉 Docker 如何测试容器是否正常运行：

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1
```

**参数：**
- `--interval=30s`：每 30 秒检查一次
- `--timeout=3s`：每次检查必须在 3 秒内完成
- `--start-period=5s`：首次检查前等待 5 秒（宽限期）
- `--retries=3`：连续 3 次失败后标记为不健康

健康检查可以实现：
- Docker 编排自动重启不健康的容器
- 负载均衡器将流量从不健康的实例路由走
- 部署系统中的回滚触发器

### 16.6 Dockerignore 文件

`.dockerignore` 文件用于从 Docker 构建上下文中排除文件，类似于 `.gitignore`。这可以提高构建性能和安全性：

```dockerignore
.git
.gitignore
node_modules/
npm-debug.log*
Dockerfile
.dockerignore
README.md
*.md
test/
tests/
.gitlab-ci.yml
.github/
.vscode/
.idea/
*.log
.env
.env.*
coverage/
dist/          # If building inside Docker, exclude pre-built
```

**好处：**
- **更小的构建上下文：** 从客户端到 BuildKit 守护进程的上传速度更快
- **安全性：** 排除诸如 `.env` 文件之类的密钥
- **缓存效率：** 排除不必要的文件可防止无关文件更改导致的缓存失效
- **更快的构建：** BuildKit 需要处理的数据更少

---

## 17. 安全加固指南

### 17.1 纵深防御策略

本工作流实现了多层安全防护：

| 层 | 工具/机制 | 防止什么 |
|---|---|---|
| 代码分析 | Hadolint（docker-lint） | Dockerfile 反模式 |
| 漏洞扫描 | Trivy（image-scan） | 包中的已知 CVE |
| 策略评估 | Docker Scout（image-scan） | 策略违规 |
| 不可变引用 | 摘要固定（verify-image） | 标签劫持 |
| 签名验证 | Cosign verify（verify-image） | 镜像篡改 |
| 供应链证明 | SLSA 出处证明（sbom-attest） | 构建来源欺诈 |
| 组件清单 | SBOM（sbom-attest） | 未知依赖 |

### 17.2 供应链安全清单

要达到生产级供应链安全状态，请验证所有以下项目：

- [ ] 基础镜像固定到特定摘要，而非标签
- [ ] 所有 apt/apk 包已固定版本
- [ ] 容器以非 root 用户运行
- [ ] 镜像层中没有嵌入密钥（API 密钥、令牌）
- [ ] 层缓存不泄露密钥（对 BuildKit 使用 `--mount=type=secret`）
- [ ] 每次发布前对镜像进行 CVE 扫描
- [ ] 推送前使用 Cosign 签名镜像
- [ ] 生成 SBOM 并附加到 release
- [ ] 每次发布都有 SLSA 出处证明
- [ ] 部署前验证签名
- [ ] `.dockerignore` 排除敏感文件
- [ ] 最终镜像仅包含生产依赖项

---

## 18. 故障排除指南

### 18.1 构建失败

**"manifest list entries 中没有匹配 linux/arm64 的清单"**

_原因：_ 基础镜像不支持目标架构。并非所有发布到 Docker Hub 的镜像都包含 arm64 变体。

_解决方案：_
- 检查基础镜像支持的架构：`docker buildx imagetools inspect <image>`
- 切换到支持两种架构的基础镜像
- 对于官方镜像（node、python、alpine、ubuntu），多架构支持几乎是通用的
- 对于第三方镜像，检查镜像的 README 了解架构支持情况

**"buildx failed with: ERROR: multiple platforms feature is not supported"**

_原因：_ 使用了 `docker` 驱动而不是 `docker-container` 驱动。

_解决方案：_ 确保 `setup-buildx-action` 配置了 `driver: docker-container`。docker 驱动不支持多架构构建。

**"failed to push: denied: resource not accessible"**

_原因：_ GITHUB_TOKEN 没有足够的权限。

_解决方案：_
- 验证 `permissions:` 包含 `packages: write`
- 检查仓库是否已在目标名称下创建了包
- 对于 GHCR，如果权限正确，首次推送时会自动创建包

### 18.2 缓存未命中

**"cache miss: no cache entry found for key"**

_原因：_ 新分支上的首次运行，或缓存已被驱逐。

_影响：_ 构建时间更长（完全重建），但仍可成功。

_解决方案：_
- 这是首次运行的预期行为
- 同一分支上的后续运行将命中缓存
- 对于频繁被驱逐的缓存，考虑添加 `mode=max` 以导出更多层

**"cache import failed: specified credentials could not be used"**

_原因：_ 使用 `type=registry` 缓存后端时出现镜像仓库认证问题。

_解决方案：_ 确保登录操作在构建操作之前运行。

### 18.3 Cosign/签名问题

**"error: signing [IMAGE] at least one identity must be provided"**

_原因：_ Cosign 无法获取 OIDC 令牌。

_解决方案：_
- 验证 `permissions:` 包含 `id-token: write`
- 检查 Cosign 是否为 v2.0+（无密钥签名在 v2.0 中正式发布）
- 验证 `COSIGN_EXPERIMENTAL` 环境变量未设置为 `true`
  （该变量对于 v1.x 是必需的，但会干扰 v2.x 的无密钥签名）

**"error: verifying image: no matching signatures"**

_原因：_ 镜像已推送但未签名，或签名位于不同的镜像仓库中。

_解决方案：_
- 确认 `cosign sign` 已完成成功
- 检查镜像仓库中的签名清单（它们在镜像仓库 UI 中显示为单独的清单）
- 验证你正在使用正确的摘要

### 18.4 Trivy 问题

**"Trivy scan failed with exit code 1"**

_原因：_ 在配置的严重阈值发现了漏洞。

当设置了 `exit-code: 1` 时，这是预期行为。扫描正常工作 — 它发现了问题。检查 SARIF 输出和 CI 日志以获取详细信息。

判断是工具错误还是漏洞发现：
- 检查步骤输出中是否有"CRITICAL"或"HIGH"严重级别列表
- 如果输出显示漏洞，这些是可操作修复项
- 如果输出显示诸如"unable to initialize database"之类的错误，则属于工具问题

**"Trivy failed to download vulnerability database"**

_原因：_ 网络连接问题或 Docker Hub 速率限制。

_解决方案：_
- GitHub Actions 运行器默认有网络访问权限
- 对于速率限制，Trivy 会自动重试并回退
- 在离线环境中，配置本地 Trivy 镜像

### 18.5 Release 失败

**"Resource not accessible by integration" — release 创建失败**

_原因：_ GITHUB_TOKEN 没有 `contents: write` 权限。

_解决方案：_ 验证工作流 `permissions:` 块包含 `contents: write`。

**"Validation Error: Tag already exists" — tag_name 冲突**

_原因：_ 具有相同标签的 release 已经存在。

_解决方案：_
- 为每次构建使用唯一标签（基于 semver 或时间戳）
- `workflow_dispatch` 流程从版本号创建标签，这应该是唯一的
- 对于 `release` 事件触发器，标签已存在（GitHub 创建了它）

### 18.6 清理问题

**"delete failed: resource not accessible" — cleanup 操作失败**

_原因：_ GITHUB_TOKEN 需要默认可能未授予的包删除权限。

_解决方案：_
- 需要 `packages: write` 权限，但可能不够
- 对于 GHCR 包删除，可能需要具有 `delete:packages` 范围的 Personal Access Token（个人访问令牌）
- 将 PAT 配置为仓库密钥，并将其作为 `token` 输入传递

---

## 19. 成本与资源优化

### 19.1 运行器时间分析

此工作流中每个作业的预估运行时间：

| 作业 | 预估时间 | 并行对象 | 成本说明 |
|---|---|---|---|
| docker-setup | ~30秒 | — | 基础设置 |
| docker-lint | ~20秒 | metadata | 快速、轻量 |
| metadata | ~15秒 | docker-lint | 快速、轻量 |
| build-push | ~3-8分钟 | — | 最昂贵（多架构构建） |
| image-scan | ~2-3分钟 | sbom-attest | 首次运行下载数据库 |
| sbom-attest | ~2-3分钟 | image-scan | SBOM 生成 + Cosign |
| verify-image | ~1分钟 | — | 拉取 + 验证 |
| release | ~30秒 | — | API 调用 |
| cleanup | ~15秒 | — | API 调用 |

**总墙钟时间：** ~8-15 分钟（取决于构建复杂度和缓存命中率）

**总运行器分钟数：** ~10-18 分钟（由于并行执行）

### 19.2 缓存成本节省

没有缓存（`--no-cache`）时，典型的多架构构建需要 8-15 分钟。使用 GHA 缓存且命中率超过 50% 时，构建时间降至 2-5 分钟。

**成本计算（GitHub 托管运行器）：**
- Linux 运行器：$0.008/分钟
- 无缓存：平均 12 分钟 → $0.096/次运行
- 有缓存：平均 4 分钟 → $0.032/次运行
- 节省：每次运行约 67%
- 每天 50 次运行：每天约节省 $3.20

### 19.3 存储管理

GHCR 存储限制：
- 免费套餐：私有仓库 500 MB，公共仓库无限制
- 付费套餐：包含在分钟数中
- 清理（作业 9）对于保持在私有仓库限制内至关重要

管理 GHCR 存储的策略：
1. 删除未标记的版本（本工作流）
2. 设置包级别保留策略（GitHub UI > Packages > Settings）
3. 使用具有共享层的 OCI 索引（多架构镜像共享基础层）
4. 仅保留最后 N 个有标签的版本

---

## 20. 扩展本工作流

### 20.1 添加更多平台

要将 ARM v7（32 位，适用于树莓派）添加到构建矩阵中：

1. 更新 `platforms` 输入默认值：
```yaml
platforms:
  default: 'linux/amd64,linux/arm64,linux/arm/v7'
```

2. 验证 QEMU 设置包含 arm 仿真：
```yaml
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3
  with:
    platforms: arm64,arm
```

3. 验证基础镜像支持 arm/v7：
```bash
docker buildx imagetools inspect node:22-slim | grep arm
```

### 20.2 添加镜像升级

要添加镜像升级作业（例如，将 `edge` 升级为 `stable`）：

```yaml
promote:
  needs: verify-image
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Promote image to stable
      run: |
        docker buildx imagetools create \
          --tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:stable \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
```

### 20.3 添加部署

要将已验证的镜像部署到 Kubernetes 集群：

```yaml
deploy:
  needs: verify-image
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  environment: production
  steps:
    - uses: azure/setup-kubectl@v4

    - name: Update Kubernetes deployment
      run: |
        kubectl set image deployment/myapp \
          myapp=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --record
```

### 20.4 添加通知

要发送 Slack/钉钉/飞书通知：

```yaml
notify:
  needs: [verify-image, release, cleanup]
  runs-on: ubuntu-latest
  if: always()
  steps:
    - uses: slackapi/slack-github-action@v2
      with:
        webhook: ${{ secrets.SLACK_WEBHOOK }}
        webhook-type: incoming-webhook
        payload: |
          {
            "text": "Docker build complete: ${{ needs.build-push.outputs.digest }}"
          }
```

---

## 21. 工作流 DAG 参考

### Complete Job Dependency Graph

```
                           ┌─────────────────┐
                           │   docker-setup   │
                           └────────┬────────┘
                                    │
                    ┌───────────────┼──────────────────┐
                    ▼               ▼                   │
             ┌──────────┐   ┌──────────┐               │
             │docker-lint│   │ metadata │               │
             └─────┬─────┘   └─────┬────┘               │
                   │               │                    │
                   └───────┬───────┘                    │
                           ▼                            │
                    ┌──────────────┐                    │
                    │  build-push  │                    │
                    └──────┬───────┘                    │
                           │                            │
               ┌───────────┴───────────┐                │
               ▼                       ▼                │
        ┌──────────┐           ┌────────────┐          │
        │image-scan│           │sbom-attest │          │
        └─────┬────┘           └──────┬─────┘          │
              │                       │                │
              └───────────┬───────────┘                │
                          ▼                            │
                   ┌──────────────┐                    │
                   │ verify-image │                    │
                   └──────┬───────┘                    │
                          │                            │
                          ▼                            │
                   ┌──────────────┐                    │
                   │   release    │  (branch condition)│
                   └──────┬───────┘                    │
                          │                            │
                          ▼                            │
                   ┌──────────────┐                    │
                   │   cleanup    │  (branch condition)│
                   └──────────────┘                    │
```

### 条件矩阵

| 作业 | main 分支 | dev 分支 | 功能分支 | Release 事件 |
|---|---|---|---|---|
| docker-setup | 是 | 是 | 是 | 是 |
| docker-lint | 是 | 是 | 是 | 是 |
| metadata | 是 | 是 | 是 | 是 |
| build-push | 是 | 是 | 是 | 是 |
| image-scan | 是（skip-scan?） | 是（skip-scan?） | 是（skip-scan?） | 是（skip-scan?） |
| sbom-attest | 是 | 是 | 是 | 是 |
| verify-image | 是 | 是 | 是 | 是 |
| release | 是 | 否 | 否 | 是（附加） |
| cleanup | 是 | 否 | 否 | 否 |

---

## 22. 脚本与命令参考

### 有用的 Docker 命令

```bash
# List multi-arch platforms for an image
docker buildx imagetools inspect node:22-slim

# Pull specific architecture
docker pull --platform linux/arm64 node:22-slim

# Inspect an image's layers
docker history ghcr.io/owner/repo@sha256:digest

# View SBOM attestation in image
docker buildx imagetools inspect ghcr.io/owner/repo@sha256:digest --format '{{ json .Attestations }}'

# Export SBOM from image
docker buildx imagetools inspect ghcr.io/owner/repo@sha256:digest --format '{{ range .Manifests }}{{ if eq .Annotations "sbom" }}{{ .Digest }}{{ end }}{{ end }}'

# Verify Cosign signature manually
cosign verify ghcr.io/owner/repo@sha256:digest \
  --certificate-identity-regexp "https://github.com/owner/repo/.github/workflows/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Search Rekor for an image's signature
rekor-cli search --artifact sha256:digest

# Delete old images from GHCR manually
gh api --method DELETE "/orgs/owner/packages/container/repo-name/versions/version-id"
```

### 有用的 `gh` CLI 命令

```bash
# Trigger workflow manually
gh workflow run docker-full-lifecycle.yml \
  --field platforms="linux/amd64,linux/arm64" \
  --ref main

# List workflow runs
gh run list --workflow docker-full-lifecycle.yml

# View run logs
gh run view <run-id> --log

# Download artifacts from a run
gh run download <run-id> -n sbom-and-attestation

# Check package versions in GHCR
gh api /orgs/owner/packages/container/repo-name/versions --jq '.[].metadata.container.tags'
```

---

## 文档结束

---

## 23. YAML 语法深入解析

### 23.1 YAML 锚点与别名（用于 DRY 工作流）

GitHub Actions 支持 YAML 锚点（`&`）和别名（`*`）来减少重复：

```yaml
# 定义可复用的代码块
.base-setup: &base-setup
  - uses: actions/checkout@v4
  - uses: docker/login-action@v3
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}

jobs:
  job-a:
    steps:
      - *base-setup                  # 复用锚点
      - run: echo "doing something"

  job-b:
    steps:
      - *base-setup                  # 再次复用
      - run: echo "doing something else"
```

虽然本工作流未使用锚点（它们在调试时可能引起混淆），但这是减少包含许多作业的大型工作流中样板代码的有用技术。

### 23.2 矩阵策略

矩阵策略从单个作业定义创建多个作业变体。虽然本工作流使用单平台策略（无矩阵），但以下是矩阵构建多平台的方式：

```yaml
build-matrix:
  strategy:
    matrix:
      platform:
        - linux/amd64
        - linux/arm64
        - linux/arm/v7
    # 当其中一个失败时不取消所有运行器
    fail-fast: false
    # 使用最大并行限制
    max-parallel: 3
  steps:
    - uses: docker/build-push-action@v6
      with:
        platforms: ${{ matrix.platform }}
        tags: ghcr.io/owner/repo:${{ matrix.platform }}
```

然而，使用单个带有多个 `platforms:` 的 build-push 更可取，因为：
- BuildKit 内部并行构建所有平台
- 创建单个多架构清单列表
- 推送创建一个引用所有平台的 OCI 索引
- 矩阵构建为每个平台创建单独的镜像标签，而非清单列表

### 23.3 并发组

对于生产环境使用，添加 `concurrency` 块以防止冗余运行：

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

这会在新提交推送到同一分支时取消正在进行的运行，从而节省 CI 分钟数。没有这个设置，每次提交都会触发新的运行，同时前一次运行继续完成 — 在过时的构建上浪费资源。

### 23.4 超时

设置作业级超时以防止失控的构建：

```yaml
build-push:
  timeout-minutes: 30
```

GitHub 托管运行器的默认超时为 360 分钟（6 小时）。为了提高 CI 效率，设置反映实际预期的超时时间。启用缓存的多架构 Docker 构建很少需要超过 15-20 分钟。

### 23.5 环境 URL

将工作流运行 UI 链接到已部署的 release：

```yaml
release:
  steps:
    - name: Create Release
      uses: softprops/action-gh-release@v2
      # ...
    - name: Set deploy URL
      run: |
        echo "deploy_url=https://github.com/${{ github.repository }}/releases/tag/v${{ needs.metadata.outputs.version }}" >> "$GITHUB_ENV"
```

部署 URL 作为可点击链接出现在工作流运行摘要中。

---

## 24. 工作流输出摘要

### 作业输出表

| 作业 | 输出 | 类型 | 描述 | 被谁消费 |
|---|---|---|---|---|
| docker-setup | builder-name | string | Buildx 构建器实例名称 | 仅诊断 |
| metadata | tags | string（逗号分隔） | Docker 镜像标签 | build-push |
| metadata | labels | string（逗号分隔） | OCI 镜像标记 | build-push |
| metadata | json | string (JSON) | 完整元数据 JSON | 任意 |
| metadata | version | string | 检测到的版本号 | build-push, release |
| build-push | digest | string (sha256:) | 镜像清单摘要 | image-scan, sbom-attest, verify-image, release |
| build-push | tags | string | 构建的标签 | release |
| build-push | image-with-digest | string | 完整不可变引用 | 仅诊断 |

---

## 25. 环境变量参考

### 工作流级变量

| 变量 | 值 | 描述 | 用于 |
|---|---|---|---|
| `REGISTRY` | `ghcr.io` | 容器镜像仓库主机名 | login, build, push, verify |
| `IMAGE_NAME` | `${{ github.repository }}` | 镜像名称（owner/repo） | 所有镜像引用 |
| `TRIVY_SEVERITY` | `CRITICAL,HIGH` | 漏洞严重级别阈值 | image-scan |

### 使用的密钥

| 密钥 | 来源 | 描述 | 用于 |
|---|---|---|---|
| `GITHUB_TOKEN` | 自动生成 | 仓库范围的令牌 | login, release, cleanup, attest |

---

## 快速参考：创建的文件

| 文件 | 行数 | 用途 |
|---|---|---|
| `.github/workflows/docker-full-lifecycle.yml` | ~550 | 包含 9 个作业的工作流定义 |
| `.github/workflow-lab/docs/workflow-2-docker-lifecycle.md` | ~3000+ | 本文档 |

---

## 文档结束
