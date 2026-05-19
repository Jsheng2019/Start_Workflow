# Docker 多架构构建指南

## 概述

本项目的 Docker 工作流支持构建 **linux/amd64** 和 **linux/arm64** 双平台镜像，推送到 GitHub Container Registry (GHCR)。同一标签下包含两种架构的镜像，用户 `docker pull` 时自动匹配本地 CPU 架构，无需手动选择。

### 核心原理

```text
┌──────────────────────────────────────┐
│ ghcr.io/jsheng2019/start-workflow:v1 │  ← 同一个 tag
├──────────────────────────────────────┤
│ linux/amd64 digest: sha256:abc...    │  ← x86 机器自动拉取
│ linux/arm64 digest: sha256:def...    │  ← ARM 机器自动拉取
└──────────────────────────────────────┘
```

- **QEMU**: 在 x86 runner 上模拟 ARM 指令集，无需 ARM 硬件即可编译 ARM 镜像
- **Buildx**: Docker 的多平台构建器，同时构建多个架构并生成 manifest list
- **manifest list**: 一个 tag 指向多个架构的镜像 digest，Docker 根据 `uname -m` 自动匹配

---

## 文件说明

| 文件 | 用途 |
|---|---|
| `Dockerfile` | 多阶段构建：编译期 + 运行期，最终镜像约 60MB |
| `.github/workflows/docker-build.yml` | 手动触发构建，可自定义 tag 和平台 |
| `.github/workflows/docker-release.yml` | 推送 `v*` tag 时自动构建发布 |

---

## 工作流一：手动构建 (docker-build.yml)

### 触发方式

在 GitHub 仓库 → **Actions** → **Docker Build (Multi-Arch)** → **Run workflow**，填写参数：

| 参数 | 说明 | 默认值 |
|---|---|---|
| `tag` | 镜像标签 | `latest` |
| `platforms` | 目标平台 | `linux/amd64,linux/arm64` |

### 执行步骤

1. **Checkout** — 拉取代码
2. **QEMU** — 安装 ARM 模拟器
3. **Buildx** — 创建多平台构建器
4. **GHCR Login** — 使用 `GITHUB_TOKEN` 登录 `ghcr.io`
5. **Metadata** — 生成 OCI 标签和注解
6. **Build & Push** — 构建多平台镜像、生成 provenance (SLSA) 和 SBOM，推送至 GHCR

---

## 工作流二：Tag 自动发布 (docker-release.yml)

### 触发方式

推送符合 `v*` 格式的 tag 时自动触发：

```bash
git tag v1.0.0
git push origin v1.0.0
```

### 自动生成的标签

推送 `v1.2.3` 会生成三个标签：

| 标签 | 含义 |
|---|---|
| `1.2.3` | 完整版本 |
| `1.2` | 次版本（可拉取最新补丁） |
| `1` | 主版本（可拉取最新次版本） |

### 执行步骤

与手动构建相同，差异在于 tag 自动从 `github.ref_name` 提取，平台固定为 `linux/amd64,linux/arm64`。

---

## 使用方式

### 拉取镜像

```bash
# 自动匹配架构（推荐）
docker pull ghcr.io/jsheng2019/start-workflow:latest

# 指定架构拉取
docker pull ghcr.io/jsheng2019/start-workflow:latest --platform linux/arm64
docker pull ghcr.io/jsheng2019/start-workflow:latest --platform linux/amd64
```

### 运行容器

```bash
docker run --rm ghcr.io/jsheng2019/start-workflow:latest
# 输出: Hello, Developer! Welcome to GitHub Actions.
```

---

## GitHub 仓库设置

使用前需确保以下设置正确：

1. **Actions → General → Workflow permissions**
   - 勾选 **Read and write permissions**（允许 GITHUB_TOKEN 推送包）

2. **Packages**（可选）
   - 在仓库右侧 → Packages → 找到 `start-workflow` 包
   - Package Settings → 将可见性改为 **Public**（默认 Private）

无需额外配置 Secrets，`GITHUB_TOKEN` 由 Actions 自动注入。

---

## 验证方法

### 1. 查看 manifest list

```bash
docker manifest inspect ghcr.io/jsheng2019/start-workflow:latest
```

输出应包含 `linux/amd64` 和 `linux/arm64` 两个 manifests。

### 2. 在 GHCR 包页面确认

仓库首页 → 右侧 Packages → 点击镜像 → 查看 **OS/Arch** 列，应显示 `linux/amd64, linux/arm64`。

### 3. 查看构建日志

Actions 中 `Build and push multi-arch image` 步骤的输出会显示每个平台的 digest：

```text
linux/amd64: digest: sha256:abc123... size: 1234
linux/arm64: digest: sha256:def456... size: 1234
```

---

## 相关 Action 参考

| Action | 版本 | 用途 |
|---|---|---|
| `docker/setup-qemu-action` | v3 | ARM 指令集模拟 |
| `docker/setup-buildx-action` | v3 | 多平台构建器 |
| `docker/login-action` | v3 | GHCR 登录 |
| `docker/metadata-action` | v5 | OCI 标签和注解 |
| `docker/build-push-action` | v6 | 构建 + 推送 + provenance + SBOM |
