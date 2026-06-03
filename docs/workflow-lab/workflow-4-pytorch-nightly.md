# Workflow 4: PyTorch Community Nightly Build — 完整指南

> **受众：** 想要理解并部署 PyTorch 社区 nightly 构建流水线的开发者。
>
> **对应文件：**
> - `.github/workflows/pytorch-nightly.yml` — 工作流定义
> - `.github/scripts/generate_nightly_matrix.py` — 构建矩阵生成器
> - `scripts/build_wheel.sh` — Wheel 构建脚本（真实编译）
>
> **涉及概念：** PyTorch 源码编译、manylinux wheel、构建矩阵、C++ 编译优化、GitHub Actions 大规模 CI

---

## 目录

1. [概述：这个 Workflow 做什么](#1-概述这个-workflow-做什么)
2. [Pipeline 架构](#2-pipeline-架构)
3. [真实编译过程](#3-真实编译过程)
4. [构建矩阵设计](#4-构建矩阵设计)
5. [Manylinux Docker 构建环境](#5-manylinux-docker-构建环境)
6. [ccache 编译缓存](#6-ccache-编译缓存)
7. [Smoke Test 验证](#7-smoke-test-验证)
8. [与 PyTorch 上游 CI 的对比](#8-与-pytorch-上游-ci-的对比)
9. [本地使用与调试](#9-本地使用与调试)
10. [常见问题](#10-常见问题)
11. [Workflow 结构说明](#11-workflow-结构说明)

---

## 1. 概述：这个 Workflow 做什么

这个 Workflow **真实地从 C++ 源码编译 PyTorch**，不是 mock 或 demo。它：

1. **克隆** `pytorch/pytorch` 主仓库（shallow clone, depth=1）
2. **编译** 3000+ 个 C++ 源文件 → libtorch + torch._C 共享库
3. **打包** 为一个 PEP 440 manylinux wheel（约 180–220 MB）
4. **Smoke test**：`import torch`, tensor 运算, autograd, nn.Module
5. **上传** wheel 作为 GitHub Artifact

### 与真正的 PyTorch Nightly 的关系

| 维度 | PyTorch 上游 CI | 本 Workflow |
|------|----------------|-------------|
| Docker 镜像 | `pytorch/manylinux2_28-builder:cpu` | **同一个镜像** |
| 编译内容 | 完整 PyTorch C++/CUDA 源码 | 完整 PyTorch C++ 源码（CPU-only） |
| 产出 | ~200MB manylinux wheel | ~180–220MB manylinux wheel |
| Runner | `linux.12xlarge` (72 vCPU, 144GB) | `ubuntu-latest` (2 vCPU, 7GB) |
| 构建时间 | 30 分钟 | 2–4 小时 |
| 矩阵规模 | 56+ 条目 (8 Python × 7 GPU 变体) | 1–12 条目 (可配置) |
| 上传目标 | AWS S3 / Cloudflare R2 | GitHub Artifacts |
| CUDA 支持 | cu126, cu130, cu132 + ROCm + XPU | CPU-only（免费 runner 无 GPU） |

---

## 2. Pipeline 架构

```
                         ┌──────────────────────────┐
                         │   generate-matrix          │
                         │   (Python → JSON matrix)   │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────┴────────────────────────────┐
                         │                                         │
                         ▼                                         ▼
              ┌──────────────────────┐                  ┌──────────────────────┐
              │  build (py3.12-cpu)  │                  │  build (py3.13-cpu)  │
              │  ┌────────────────┐  │                  │  ┌────────────────┐  │
              │  │ Clone PyTorch  │  │                  │  │ Clone PyTorch  │  │
              │  │ git submodule  │  │                  │  │ git submodule  │  │
              │  │ pip install -r │  │                  │  │ pip install -r │  │
              │  │ python setup.py│  │                  │  │ python setup.py│  │
              │  │   bdist_wheel  │  │                  │  │   bdist_wheel  │  │
              │  │ ↓ 2–4 hours ↓ │  │                  │  │ ↓ 2–4 hours ↓ │  │
              │  │ torch.whl      │  │                  │  │ torch.whl      │  │
              │  └────────┬───────┘  │                  │  └────────┬───────┘  │
              └───────────┼──────────┘                  └───────────┼──────────┘
                          │                                         │
                          ▼                                         ▼
              ┌──────────────────────────────────────────────────────────────┐
              │                        test (Matrix)                          │
              │  pip install torch.whl                                       │
              │  smoke test: import torch, mm, autograd, nn.Linear           │
              └────────────────────────────────┬─────────────────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────┐
                              │  summary (nightly report)      │
                              └──────────────────────────────┘
```

### Job 依赖图

| Job | 依赖 | 容器 | 超时 |
|-----|------|------|------|
| `generate-matrix` | — | bare runner | 2 min |
| `build` | `generate-matrix` | `pytorch/manylinux2_28-builder:cpu` | 360 min |
| `test` | `generate-matrix`, `build` | bare runner | 15 min |
| `summary` | `generate-matrix`, `build`, `test` | bare runner | 2 min |

---

## 3. 真实编译过程

### 编译命令

构建脚本 `scripts/build_wheel.sh` 执行以下步骤：

```bash
# 1. 克隆 PyTorch 源码（浅克隆，仅最新提交）
git clone --depth=1 --branch=main --single-branch \
    https://github.com/pytorch/pytorch.git

# 2. 初始化必要的子模块
git submodule update --init --depth=1 \
    third_party/pybind11 \
    third_party/cpuinfo \
    third_party/XNNPACK \
    ...

# 3. 安装构建依赖
/opt/python/cp312-cp312/bin/pip install -r requirements.txt

# 4. 编译 C++ 源码 + 打包 wheel
USE_CUDA=0 BUILD_TEST=0 MAX_JOBS=2 \
    /opt/python/cp312-cp312/bin/python setup.py bdist_wheel
```

### setup.py bdist_wheel 内部发生了什么

1. **CMake 配置** — 检测编译器、依赖库、CPU 特性
2. **编译 libtorch** — ~2000 个 C++ 文件 → `libtorch.so`
3. **编译 torch._C** — ~500 个 pybind11 绑定文件 → `_C.so`
4. **编译第三方库** — XNNPACK, cpuinfo, FXdiv, pthreadpool 等
5. **打包** — 将所有 .so 文件 + Python 代码打包为 .whl

### 构建环境变量

| 变量 | 值 | 说明 |
|------|-----|------|
| `USE_CUDA` | `0` | 禁用 CUDA（免费 runner 无 GPU） |
| `USE_CUDNN` | `0` | 禁用 cuDNN |
| `USE_FBGEMM` | `1` | 启用 FBGEMM（CPU 量化推理加速） |
| `USE_DISTRIBUTED` | `0` | 跳过分布式训练支持 |
| `USE_NCCL` | `0` | 跳过 NCCL |
| `BUILD_TEST` | `0` | 跳过 C++ 测试编译 |
| `MAX_JOBS` | `2` | 并行编译数（匹配 7GB RAM） |
| `CMAKE_BUILD_TYPE` | `Release` | 优化编译，无调试符号 |
| `ATEN_THREADING` | `NATIVE` | 使用原生线程池 |

### 构建时间分析

| Runner 规格 | MAX_JOBS | RAM | 预计构建时间 |
|------------|----------|-----|-------------|
| `ubuntu-latest` (2 vCPU) | 2 | 7 GB | 2–4 小时 |
| `ubuntu-latest-4` (4 vCPU) | 4 | 16 GB | 1–2 小时 |
| `ubuntu-latest-16` (16 vCPU) | 8 | 64 GB | 30–60 分钟 |
| PyTorch CI (72 vCPU) | 40 | 144 GB | ~30 分钟 |

---

## 4. 构建矩阵设计

### 动态生成

矩阵由 `.github/scripts/generate_nightly_matrix.py` 动态生成：

```bash
python3 generate_nightly_matrix.py \
  --python-versions "3.10 3.11 3.12 3.13" \
  --cuda-versions "cpu cu124 cu126"
```

输出示例：

```json
{
  "include": [
    {
      "build_name": "manywheel-py3_10-cpu",
      "python_version": "3.10",
      "python_abi": "cp310-cp310",
      "cuda_version": "cpu",
      "cuda_display": "cpu",
      "container": "pytorch/manylinux2_28-builder:cpu"
    },
    {
      "build_name": "manywheel-py3_12-cuda12_4",
      "python_version": "3.12",
      "python_abi": "cp312-cp312",
      "cuda_version": "cu124",
      "cuda_display": "cuda12.4",
      "container": "pytorch/manylinux2_28-builder:cuda12.4"
    }
  ]
}
```

### 矩阵消费

```yaml
build:
  strategy:
    matrix: ${{ fromJson(needs.generate-matrix.outputs.build-matrix) }}
```

每个 JSON 条目生成一个**并行**的 GitHub Actions job。所有 job 同时运行（受 GitHub 并行上限限制）。

### 默认矩阵 vs 完整矩阵

| 配置 | 默认（免费 runner） | 完整（workflow_dispatch） |
|------|-------------------|--------------------------|
| Python | 3.12 | 3.10 3.11 3.12 3.13 |
| CUDA | cpu | cpu cu124 cu126 |
| 条目数 | 1 | 12 |
| 总构建时间 | 2–4h | 2–4h × 并行数 |

---

## 5. Manylinux Docker 构建环境

### 为什么需要 manylinux？

PyTorch 编译出的 `.so` 文件（libtorch.so, _C.so）必须链接到**旧版本**的 glibc（2.28），才能在 CentOS 8+, Ubuntu 20.04+, Debian 11+ 等主流 Linux 上运行。如果链接到较新的 glibc（如 2.35），旧发行版用户将无法 `pip install`。

### 使用的镜像

```yaml
container:
  image: pytorch/manylinux2_28-builder:cpu
```

这是 **PyTorch 官方 CI 使用的同一个镜像**，包含：

- CentOS Stream 8 基础系统（glibc 2.28）
- `/opt/python/cp310-cp310` 到 `cp313-cp313` 的 Python
- CMake 3.28+, Ninja, ccache
- Conda + MKL, MAGMA, LAPACK

### 容器中的 Python 路径

```
/opt/python/
  cp310-cp310/bin/python   → Python 3.10
  cp311-cp311/bin/python   → Python 3.11
  cp312-cp312/bin/python   → Python 3.12
  cp313-cp313/bin/python   → Python 3.13
```

构建脚本根据 `DESIRED_PYTHON` 环境变量解析正确的 Python 路径。

---

## 6. ccache 编译缓存

### 缓存策略

首次构建 PyTorch 需要 2–4 小时。使用 ccache 后，**后续构建仅重编译变更的文件**：

```yaml
- name: Restore ccache
  uses: actions/cache@v4
  with:
    path: ~/.ccache
    key: pytorch-ccache-${{ matrix.python_version }}-${{ matrix.cuda_version }}-${{ hashFiles('.github/workflows/pytorch-nightly.yml') }}
    restore-keys: |
      pytorch-ccache-${{ matrix.python_version }}-${{ matrix.cuda_version }}-
      pytorch-ccache-${{ matrix.python_version }}-
```

### 效果

| 场景 | 构建时间 |
|------|---------|
| 首次构建（冷缓存） | 2–4 小时 |
| PyTorch 源码未变更 | 10–30 分钟 |
| 单个文件变更 | 30–60 分钟 |

ccache 缓存目录 `~/.ccache` 通过 GitHub Actions Cache 在 workflow run 之间持久化。

---

## 7. Smoke Test 验证

构建完成后，test job 验证 wheel 是否可用：

```python
import torch

# 1. 版本检查
assert torch.__version__ is not None

# 2. CUDA 状态 必须匹配构建变体
assert torch.cuda.is_available() == (cuda_version != "cpu")

# 3. 张量运算 — 验证 C++ 数学库可用
x = torch.randn(100, 100)
y = torch.mm(x, x.t())      # 矩阵乘法

# 4. Autograd — 验证自动微分引擎
w = torch.randn(10, 10, requires_grad=True)
(w ** 2).sum().backward()
assert w.grad is not None

# 5. nn.Module — 验证神经网络层
linear = torch.nn.Linear(10, 5)
out = linear(torch.randn(3, 10))
assert out.shape == (3, 5)

# 6. 序列化
torch.save(linear.state_dict(), '/tmp/model.pt')
```

这比 toy demo 的测试更全面，验证了 PyTorch 的核心运行时组件。

---

## 8. 与 PyTorch 上游 CI 的对比

### 工作流结构对比

| 本 Workflow | 上游 PyTorch | 说明 |
|------------|-------------|------|
| `pytorch-nightly.yml` | `generated-linux-binary-manywheel-nightly.yml` | 主工作流 |
| `generate-matrix` job | `generate_binary_build_matrix.py` | 构建矩阵 |
| `build` job（内联） | `_binary-build-linux.yml`（reusable） | 编译阶段 |
| `test` job（内联） | `_binary-test-linux.yml`（reusable） | 测试阶段 |
| `summary` job | `_binary-upload.yml`（reusable workflow） | 上传 |

### 采用的简化

| 上游特性 | 本 Workflow | 原因 |
|---------|------------|------|
| Reusable workflow（`workflow_call`） | 内联 job | 简化文件结构 |
| S3/R2 上传 | GitHub Artifacts | 免费方案 |
| SLSA provenance + 签名 | — | 需要密钥基础设施 |
| GPU runner（g4dn, ROCm, XPU） | CPU only | 免费 runner 无 GPU |
| LibTorch C++ 分发 | — | 仅构建 Python wheel |
| 完整测试套件（20000+ 用例） | Smoke test | 完整测试需 4h+ |

---

## 9. 本地使用与调试

### 本地构建（Docker）

```bash
# 拉取 PyTorch 官方 builder 镜像
docker pull pytorch/manylinux2_28-builder:cpu

# 进入容器编译
docker run --rm -it -v $(pwd):/workspace -w /workspace \
  -e DESIRED_PYTHON=3.12 \
  -e DESIRED_CUDA=cpu \
  -e MAX_JOBS=4 \
  pytorch/manylinux2_28-builder:cpu \
  bash scripts/build_wheel.sh
```

### 手动触发 Workflow

```bash
# 通过 GitHub CLI
gh workflow run pytorch-nightly.yml \
  -f python-versions="3.12" \
  -f cuda-versions="cpu" \
  -f max-jobs="2" \
  -f pytorch-ref="main"
```

### 查看构建进度

```bash
gh run watch $(gh run list --workflow=pytorch-nightly.yml --limit=1 --json databaseId -q '.[0].databaseId')
```

---

## 10. 常见问题

### Q: 为什么构建要 2–4 小时？
A: PyTorch 有 3000+ 个 C++ 文件需要编译。上游 PyTorch CI 使用 72 核 runner 只需 30 分钟。免费 GitHub runner 只有 2 核，编译时间按比例增长。

### Q: 可以加速吗？
A: 有几种方式：
- 使用 GitHub 付费 runner（`ubuntu-latest-4` 或 `ubuntu-latest-16`）
- 使用 `ccache`（已启用，后续构建加快 5–10x）
- 减小 `MAX_JOBS` 以外的优化空间有限

### Q: 能构建 CUDA 版本吗？
A: 需要 GPU runner（如 `linux.g4dn.xlarge`）。免费 runner 没有 NVIDIA GPU。workflow 已预留 CUDA 支持——将 `cuda-versions` 设为 `cu124` 并在 GPU runner 上运行即可。

### Q: 为什么不用 `python -m build`？
A: PyTorch 上游已迁移到 `python -m build --wheel --no-isolation`。我们使用传统的 `python setup.py bdist_wheel` 是因为它在 manylinux 容器中兼容性更好，且 `WERROR=1` 下不会引入新问题。

### Q: wheel 可以分享给别人用吗？
A: 可以！从 workflow run 的 Artifacts 下载 wheel，其他人可以通过 `pip install torch-*.whl` 安装。这是 CPU-only 版本，兼容任何 x86_64 Linux。

### Q: 可以在本地 runner 上跑吗？
A: 可以。安装 GitHub Actions self-hosted runner，修改 `runs-on` 为 `self-hosted` 即可。本地 runner 可以使用更多 CPU 核心加速构建。

---

## 11. Workflow 结构说明

### 触发条件

```yaml
on:
  schedule:
    - cron: '7 17 * * *'        # 每日 UTC 17:07（北京时间 01:07）
  workflow_dispatch:
    inputs:
      python-versions: ...      # 可自定义 Python 版本列表
      cuda-versions: ...        # 可自定义 CUDA 变体列表
      package-type: ...         # 包类型
      max-jobs: ...             # 编译并行度
      pytorch-ref: ...          # PyTorch git 引用（默认 main）
```

### 并发控制

```yaml
concurrency:
  group: pytorch-nightly-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'schedule' }}
```

- 定时运行：新的 run 会取消旧的
- 手动触发：绝不取消

### 构建阶段的关键步骤

| 步骤 | 动作 | 说明 |
|------|------|------|
| Checkout | 拉取 workflow 仓库 | 获取构建脚本 |
| Restore ccache | 恢复编译缓存 | 加速重编译 |
| Clone PyTorch | `git clone --depth=1` | ~1 GB |
| Init submodules | `git submodule update --init` | pb11, cpuinfo, XNNPACK |
| Install deps | `pip install -r requirements.txt` | NumPy, pybind11, etc |
| Build wheel | `python setup.py bdist_wheel` | **真实编译 2–4h** |
| Upload artifact | `actions/upload-artifact@v4` | 保留 7 天 |
| Save ccache | `actions/cache@v4` | 为下次构建缓存 |

### 设计决策

1. **真实编译**：不是 mock，不是 demo —— 实际编译 pytorch/pytorch 源码
2. **相同镜像**：使用 PyTorch CI 相同的 `pytorch/manylinux2_28-builder` 镜像
3. **ccache**：必须启用，否则每次构建都从头开始
4. **shallow clone**：`--depth=1` 大幅减少下载量（4GB → 1GB）
5. **最小子模块**：只初始化编译必需的子模块
6. **360 分钟超时**：足够完成构建，防止无限等待
7. **具体 smoke test**：验证 import, tensor ops, autograd, nn, serialize

---

## 资源链接

- [PyTorch 上游 nightly workflow](https://github.com/pytorch/pytorch/blob/main/.github/workflows/generated-linux-binary-manywheel-nightly.yml)
- [PyTorch CI 构建脚本](https://github.com/pytorch/pytorch/blob/main/.ci/pytorch/build.sh)
- [PyTorch Builder 仓库](https://github.com/pytorch/builder)
- [Manylinux 规范 (PEP 600)](https://peps.python.org/pep-0600/)
- [ccache 官方文档](https://ccache.dev/)
- [GitHub Actions container 指令](https://docs.github.com/en/actions/using-jobs/running-jobs-in-a-container)
