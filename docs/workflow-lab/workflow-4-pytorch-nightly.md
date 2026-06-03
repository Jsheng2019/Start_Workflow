# Workflow 4: PyTorch Community Nightly Build — 完整指南

> **受众：** 想要理解和部署 PyTorch 社区 nightly 构建流水线的开发者。
>
> **对应文件：**
> - `.github/workflows/pytorch-nightly.yml` — 工作流定义
> - `.github/scripts/generate_nightly_matrix.py` — 构建矩阵生成器
> - `scripts/build_wheel.sh` — Wheel 构建脚本
> - `demo-pytorch/` — 演示用的 Python 包（含 C 扩展）
>
> **涉及概念：** 构建矩阵、Docker 多架构构建、manylinux wheel、C 扩展编译、CI/CD 流水线设计

---

## 目录

1. [什么是 PyTorch Community Nightly Build](#1-什么是-pytorch-community-nightly-build)
2. [Pipeline 架构概览](#2-pipeline-架构概览)
3. [构建矩阵生成](#3-构建矩阵生成)
4. [Manylinux 容器构建](#4-manylinux-容器构建)
5. [三阶段流水线详解](#5-三阶段流水线详解)
6. [工作流触发与调度](#6-工作流触发与调度)
7. [配置文件详解](#7-配置文件详解)
8. [本地验证](#8-本地验证)
9. [与真实 PyTorch 流水线的对比](#9-与真实-pytorch-流水线的对比)
10. [高级用法](#10-高级用法)
11. [常见问题](#11-常见问题)
12. [Workflow 结构说明](#12-workflow-结构说明)

---

## 1. 什么是 PyTorch Community Nightly Build

PyTorch 社区 nightly build 是 **每天凌晨自动执行**的构建流水线，将最新的 `main` 分支代码编译为多平台、多 Python 版本、多 CUDA 变体的 wheel 包，供社区开发者在正式 release 之前使用最新特性。

### 它解决什么问题？

- **快速验证最新代码**：开发者无需从源码编译，`pip install` 即可获得昨夜最新 PyTorch
- **多维度覆盖**：同时产出 CPU / CUDA / ROCm / XPU 变体，覆盖 Python 3.10–3.15
- **门禁质量**：每个构建都必须通过测试才能上传，组件质量有保障
- **供应链安全**：通过 SLSA provenance + SBOM 提供可追溯的构建证明

### Nightly vs Stable Release

| 维度 | Nightly | Stable Release |
|------|---------|---------------|
| 触发频率 | 每日自动 | 手动/按计划 |
| 版本号 | `2.8.0.dev20250603+cu124` | `2.7.0` |
| 稳定性 | 最新代码，可能不稳定 | 经过完整测试 |
| 上传位置 | `download.pytorch.org/whl/nightly` | `download.pytorch.org/whl` |
| 适用场景 | 尝鲜/开发/提前适配 | 生产环境 |

---

## 2. Pipeline 架构概览

### Job 依赖图

```
┌──────────────────────────┐
│   generate-matrix         │  动态生成构建矩阵 (Python)
│   (Python script → JSON)  │
└────────────┬─────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│                    build (Matrix)                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │ py3_10-cpu       │  │ py3_10-cu124     │  │  ...     │ │
│  │ manylinux        │  │ manylinux        │  │          │ │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┘ │
│           │                     │                          │
│           ▼                     ▼                          │
│     [wheel artifact]     [wheel artifact]                  │
└───────────┬─────────────────────┬──────────────────────────┘
            │                     │
            ▼                     ▼
┌────────────────────────────────────────────────────────────┐
│                     test (Matrix)                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │ pip install      │  │ pip install      │  │  ...     │ │
│  │ pytest           │  │ pytest           │  │          │ │
│  └──────────────────┘  └──────────────────┘  └──────────┘ │
└───────────┬─────────────────────┬──────────────────────────┘
            │                     │
            ▼                     ▼
┌────────────────────────────────────────────────────────────┐
│                   summary                                   │
│   (汇总所有变体结果，生成报告)                                │
└────────────────────────────────────────────────────────────┘
```

### 核心设计决策

1. **动态矩阵生成**：矩阵由 Python 脚本生成，避免在 YAML 中硬编码大量配置
2. **Container 原生指令**：使用 GitHub Actions 的 `container:` 指令，所有步骤直接在 manylinux 容器中执行
3. **独立测试**：每个变体独立下载 artifact、安装、测试，互不干扰
4. **`fail-fast: false`**：一个变体失败不影响其他变体继续执行

---

## 3. 构建矩阵生成

### 什么是构建矩阵？

构建矩阵是 **所有需要构建的变体组合**。PyTorch 的 nightly build 需要为每个 (Python 版本 × CUDA 变体) 组合产出一个独立的 wheel 包。

本工作流使用 `.github/scripts/generate_nightly_matrix.py` 动态生成这个矩阵：

```bash
python generate_nightly_matrix.py \
  --python-versions "3.10 3.11 3.12 3.13" \
  --cuda-versions "cpu cu124"
```

输出示例（JSON）：

```json
{
  "include": [
    {
      "build_name": "manywheel-py3_10-cpu",
      "python_version": "3.10",
      "python_abi": "cp310-cp310",
      "cuda_version": "cpu",
      "cuda_display": "cpu",
      "container": "quay.io/pypa/manylinux_2_28_x86_64:2025-03-24-e43cb71"
    },
    {
      "build_name": "manywheel-py3_10-cu124",
      "python_version": "3.10",
      "python_abi": "cp310-cp310",
      "cuda_version": "cu124",
      "cuda_display": "cuda12.4",
      "container": "quay.io/pypa/manylinux_2_28_x86_64:2025-03-24-e43cb71"
    }
  ]
}
```

### 真实 PyTorch 的矩阵规模

| 维度 | 选项数 | 具体值 |
|------|--------|--------|
| Python 版本 | 8 | 3.10, 3.11, 3.12, 3.13, 3.14, 3.14t, 3.15, 3.15t |
| CUDA 变体 | 4 | cpu, cu126, cu130, cu132 |
| ROCm 变体 | 2 | rocm7.1, rocm7.2 |
| XPU | 1 | xpu |
| **总计** | **56+** | 全部组合 |

### GitHub Actions 中的使用

```yaml
strategy:
  matrix: ${{ fromJson(needs.generate-matrix.outputs.build-matrix) }}
```

`fromJson()` 将 JSON 字符串解析为 GitHub Actions 的矩阵对象，每个 `include` 条目产生一个并行 job。

---

## 4. Manylinux 容器构建

### 为什么需要 manylinux？

Python wheel 包可以包含编译好的 C 扩展（`.so` 文件）。为了让 wheel 在尽可能多的 Linux 发行版上运行，需要链接**旧版本**的 glibc：

| 标签 | glibc 版本 | 兼容发行版 |
|------|-----------|-----------|
| `manylinux1` | glibc 2.5 | CentOS 5+ |
| `manylinux2014` | glibc 2.17 | CentOS 7+ |
| `manylinux_2_28` | glibc 2.28 | CentOS 8+, Ubuntu 20.04+ |

本工作流使用 `quay.io/pypa/manylinux_2_28_x86_64`，这是 PyPA 官方维护的 manylinux 构建镜像。

### 容器中的 Python 路径

Manylinux 镜像使用 `/opt/python/` 目录存放多个 Python 版本：

```
/opt/python/
  cp310-cp310/bin/python   → Python 3.10
  cp311-cp311/bin/python   → Python 3.11
  cp312-cp312/bin/python   → Python 3.12
  cp313-cp313/bin/python   → Python 3.13
```

构建脚本 `scripts/build_wheel.sh` 负责根据 `DESIRED_PYTHON` 环境变量解析正确的 Python 路径。

### 真实 PyTorch vs 本 Demo

| 方面 | 真实 PyTorch | 本 Demo |
|------|-------------|---------|
| Docker 镜像 | `pytorch/manylinux2_28-builder:cuda12.6` (私有) | `quay.io/pypa/manylinux_2_28_x86_64` (公开) |
| 编译内容 | 100+ C/C++/CUDA 源文件 | 1 个 C 文件 (30 行) |
| 编译时间 | 30–240 分钟 | 30–60 秒 |
| 产出大小 | ~200MB per wheel | ~20KB per wheel |
| Runner 规格 | `linux.12xlarge.memory.ephemeral` | `ubuntu-latest` (免费) |

---

## 5. 三阶段流水线详解

### Stage 1: Build（构建）

构建阶段在 manylinux 容器中编译 C 扩展并打包为 wheel。

**关键环境变量**（遵循 PyTorch 命名约定）：

| 变量 | 示例值 | 说明 |
|------|--------|------|
| `DESIRED_PYTHON` | `3.12` | 目标 Python 版本 |
| `DESIRED_CUDA` | `cu124` | 目标 CUDA 变体 |
| `PACKAGE_TYPE` | `manywheel` | 包类型 |
| `BUILD_ENVIRONMENT` | `linux-binary-manywheel` | 构建环境标识 |
| `GPU_ARCH_TYPE` | `cuda` | GPU 架构类型 |
| `GPU_ARCH_VERSION` | `cuda12.4` | GPU 架构版本 |

**构建流程**：

```bash
# 1. 解析 Python 路径
PYTHON_BIN="/opt/python/cp312-cp312/bin/python"

# 2. 安装构建工具
${PYTHON_BIN} -m pip install build setuptools wheel

# 3. 编译 C 扩展 + 打包 wheel
${PYTHON_BIN} -m build --wheel --outdir dist/
```

**产出物**：`torch_demo-2.8.0.dev20250603+cu124-cp312-cp312-linux_x86_64.whl`

### Stage 2: Test（测试）

测试阶段将构建好的 wheel 安装到干净的 Python 环境中并运行测试。

**为什么测试不在容器中运行？**
- 容器环境与用户实际环境有差异
- 需要测试 wheel 的可安装性和兼容性
- 测试框架 (pytest) 和依赖的安装需要网络访问

```bash
# 1. 下载对应变体的 wheel
actions/download-artifact@v4  →  dist/torch_demo-*.whl

# 2. 安装
pip install --find-links=dist/ torch_demo

# 3. 运行测试
python -m pytest demo-pytorch/tests/ -v
```

### Stage 3: Summary（汇总报告）

汇总所有变体的构建和测试结果，生成 Markdown 报告写入 `GITHUB_STEP_SUMMARY`。

---

## 6. 工作流触发与调度

### 定时触发（Nightly Schedule）

```yaml
on:
  schedule:
    - cron: '7 5 * * *'   # 每天 UTC 05:07（北京时间 13:07）
```

偏移到第 7 分钟（而非整点）是为了避开 GitHub Actions 调度器的整点高峰。

### 手动触发（Workflow Dispatch）

```yaml
on:
  workflow_dispatch:
    inputs:
      python-versions:   # 可自定义 Python 版本
        default: '3.10 3.11 3.12 3.13'
      cuda-versions:     # 可自定义 CUDA 变体
        default: 'cpu cu124'
      package-type:      # 可切换包类型
        default: manywheel
      keep-artifacts:    # 是否延长保留期到 90 天
        default: false
```

### 并发控制

```yaml
concurrency:
  group: pytorch-nightly-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'schedule' }}
```

- **定时触发**：同一分支的新运行会取消旧的运行（节省资源）
- **手动触发**：不会取消，确保用户明确触发的构建能完整执行

---

## 7. 配置文件详解

### 项目文件结构

```
.
├── .github/
│   ├── scripts/
│   │   └── generate_nightly_matrix.py    # 构建矩阵生成器
│   └── workflows/
│       └── pytorch-nightly.yml           # 工作流定义
├── scripts/
│   └── build_wheel.sh                    # Wheel 构建脚本
├── demo-pytorch/                         # 演示 Python 包
│   ├── setup.py                          # 包配置（含 C 扩展定义）
│   ├── torch_demo/
│   │   ├── __init__.py                   # 包入口
│   │   └── _ops.c                        # C 扩展源码
│   └── tests/
│       └── test_ops.py                   # 单元测试
└── docs/workflow-lab/
    └── workflow-4-pytorch-nightly.md     # 本文档
```

### `setup.py` — 包定义

```python
ops_extension = Extension(
    "torch_demo._ops",
    sources=["torch_demo/_ops.c"],
    extra_compile_args=["-O2", "-fPIC"],
)

setup(
    name="torch_demo",
    version=f"2.8.0.dev20250603+{CUDA_VERSION}",
    ext_modules=[ops_extension],
)
```

版本号格式遵循 PEP 440：`{base_version}.dev{date}+{local_suffix}`

### `_ops.c` — C 扩展

仅 30 行的 C 扩展，演示 `PyArg_ParseTuple`、`PyLong_FromLong`、`PyModuleDef` 等 Python C API 的基本用法。编译后的 `.so` 文件会被打包进 wheel。

---

## 8. 本地验证

### 本地构建单个 wheel

```bash
# 使用 manylinux 容器本地构建
docker run --rm -v $(pwd):/workspace -w /workspace \
  quay.io/pypa/manylinux_2_28_x86_64:latest \
  /opt/python/cp312-cp312/bin/bash -c "
    cd demo-pytorch && \
    /opt/python/cp312-cp312/bin/pip install build && \
    /opt/python/cp312-cp312/bin/python -m build --wheel
  "

# 安装并测试
pip install demo-pytorch/dist/*.whl
python -c "from torch_demo._ops import add; print(add(1, 2))"
```

### 本地运行矩阵生成器

```bash
python3 .github/scripts/generate_nightly_matrix.py \
  --python-versions "3.10 3.12" \
  --cuda-versions "cpu" \
  --output-file matrix.json
```

---

## 9. 与真实 PyTorch 流水线的对比

### 工作流文件对比

| 文件 | 真实 PyTorch | 本 Demo |
|------|-------------|---------|
| 主工作流 | `generated-linux-binary-manywheel-nightly.yml` | `pytorch-nightly.yml` |
| 构建模板 | `_binary-build-linux.yml` (reusable workflow) | 内联在 build job |
| 测试模板 | `_binary-test-linux.yml` (reusable workflow) | 内联在 test job |
| 上传模板 | `_binary-upload.yml` (reusable workflow) | summary job (不上传) |
| 矩阵生成 | `tools/scripts/generate_binary_build_matrix.py` | `.github/scripts/generate_nightly_matrix.py` |
| 构建脚本 | `.ci/manywheel/build.sh` | `scripts/build_wheel.sh` |

### 上游 vs Demo 差异

| 特性 | 真实 PyTorch | 本 Demo | 原因 |
|------|-------------|---------|------|
| **GPU runner** | `linux.g4dn.4xlarge.nvidia.gpu` | `ubuntu-latest` (无 GPU) | GitHub 免费 runner 无 GPU |
| **CUDA 编译** | 实际编译 CUDA kernels | 仅在版本号中标记 CUDA | 需要 NVIDIA 驱动 |
| **ROCm/XPU** | 完整支持 AMD/Intel GPU | 不支持 | 需要专用硬件 runner |
| **S3/R2 上传** | 上传到 AWS S3 + Cloudflare R2 | 不上传 (仅 artifact) | 需要云服务凭证 |
| **LibTorch 提取** | 从 wheel 中提取 C++ 库 | 不提取 | Demo 包无 C++ API |
| **Builder 镜像** | `pytorch/manylinux2_28-builder:cu*` | `quay.io/pypa/manylinux_2_28_x86_64` | 公开可用 |
| **Reusable workflow** | 使用 `workflow_call` 复用 | 内联 job | 简化结构 |
| **SLSA provenance** | SLSA Build L2+ | 不生成 | 需要签名基础设施 |

---

## 10. 高级用法

### 10.1 自定义 CUDA 变体

```bash
# 通过 workflow_dispatch 手动触发，输入自定义 CUDA 版本
python-versions: "3.12 3.13"
cuda-versions: "cpu cu124 cu126 cu128"
```

### 10.2 添加新的 Python 版本

1. 更新 `PYTHON_ABI` 字典（如果 Python 版本带新 ABI tag）
2. 确保 manylinux 镜像包含该 Python 版本
3. 更新 workflow_dispatch inputs 的 default 值

### 10.3 集成真实上传

将 `summary` job 替换为实际的上传逻辑：

```yaml
upload:
  needs: [build, test]
  strategy:
    matrix: ${{ fromJson(needs.generate-matrix.outputs.build-matrix) }}
  steps:
    - name: Download wheel
      uses: actions/download-artifact@v4
      with:
        name: ${{ matrix.build_name }}
    - name: Upload to S3
      run: |
        aws s3 cp *.whl s3://pytorch-whl/nightly/${{ matrix.cuda_display }}/
```

### 10.4 添加 SLSA 溯源

```yaml
- uses: slsa-framework/slsa-github-generator/.github/workflows/
    builder_go_slsa3.yml@v2.1.0
  with:
    artifact: ${{ matrix.build_name }}
```

### 10.5 添加 Reusable Workflow 模式

将 build job 提取为独立的 reusable workflow（像 PyTorch 的 `_binary-build-linux.yml`）：

```yaml
# .github/workflows/_pytorch-build.yml
on:
  workflow_call:
    inputs:
      python_version: { required: true, type: string }
      cuda_version:   { required: true, type: string }
      container:      { required: true, type: string }
```

---

## 11. 常见问题

### Q: 为什么构建要在 Docker 容器中运行？
A: 两个原因：(1) 使用 manylinux 镜像确保编译出的 C 扩展链接旧版 glibc，兼容更多 Linux 发行版；(2) 不同 CUDA 变体需要不同版本的 CUDA 工具链，容器提供了隔离环境。

### Q: 为什么测试不在容器中运行？
A: 测试需要模拟真实用户环境。如果 wheel 在容器内能安装但在用户机器上不行，就失去了测试的意义。测试在 bare runner 上运行，更接近用户的实际使用场景。

### Q: 矩阵构建会不会太慢？
A: 所有矩阵条目**并行执行**。使用 `fail-fast: false` 可以让每个变体独立运行，不会互相阻塞。在 GitHub Actions 的免费 plan 下，最多 20 个并行 job。

### Q: 如何添加真实的 CUDA 编译？
A: 需要使用 GPU runner（如 `linux.g4dn.xlarge`），并且使用包含 CUDA 工具链的 Docker 镜像（如 `nvidia/cuda:12.4.0-devel-ubuntu22.04`）。GitHub Actions 的免费 runner 没有 GPU。

### Q: `actions/checkout` 能在 manylinux 容器中运行吗？
A: 可以。`actions/checkout` 是 JavaScript action，它运行在 runner 上并操作 workspace。当使用 `container:` 指令时，workspace 会被自动挂载到容器中。checkout 产生的文件在容器内可见。

### Q: artifact 和 cache 有什么区别？
A: artifact 用于同一 workflow run 内的 job 间传递数据（build → test），retention 7-90 天。cache 用于跨 run 复用数据（依赖缓存），retention 最长 7 天未访问后过期。

### Q: 为什么 `generate-matrix` 是单独的 job？
A: 矩阵在 workflow 启动时就需要确定（GitHub Actions 在 job 启动前解析 `strategy.matrix`）。必须用一个前置 job 生成矩阵，后续 job 才能通过 `fromJson()` 使用。

---

## 12. Workflow 结构说明

### 触发条件

```yaml
on:
  schedule:
    - cron: '7 5 * * *'            # 每日定时
  workflow_dispatch:                # 手动触发
    inputs:
      python-versions: ...          # 可选：自定义 Python 版本
      cuda-versions: ...            # 可选：自定义 CUDA 变体
      package-type: ...             # 可选：包类型
      keep-artifacts: ...           # 可选：延长 artifact 保留期
```

### 环境变量

```yaml
env:
  BUILD_ENVIRONMENT: linux-binary-manywheel
  PACKAGE_TYPE: ${{ inputs.package-type || 'manywheel' }}
  BINARY_ENV_FILE: /tmp/env
  PYTORCH_FINAL_PACKAGE_DIR: /artifacts
```

### Job 概览

| Job | Runs On | Container | 超时 | 说明 |
|-----|---------|-----------|------|------|
| `generate-matrix` | ubuntu-latest | 否 | 2 min | 动态生成构建矩阵 JSON |
| `build` | ubuntu-latest | manylinux | 30 min | 每个矩阵条目构建一个 wheel |
| `test` | ubuntu-latest | 否 | 10 min | 每个矩阵条目安装并测试 wheel |
| `summary` | ubuntu-latest | 否 | 2 min | 汇总所有结果生成报告 |

### 构建阶段关键步骤

```yaml
- name: Populate binary environment
  run: |
    echo "DESIRED_PYTHON=${DESIRED_PYTHON}" >> "${BINARY_ENV_FILE}"
    echo "DESIRED_CUDA=${DESIRED_CUDA}" >> "${BINARY_ENV_FILE}"

- name: Build wheel
  run: bash scripts/build_wheel.sh    # 调用构建脚本

- name: Upload wheel artifact
  uses: actions/upload-artifact@v4
  with:
    name: ${{ matrix.build_name }}     # 唯一命名：manywheel-py3_10-cpu
    path: demo-pytorch/dist/*.whl
```

### 设计要点

1. **动态矩阵**：避免在 YAML 中硬编码上百行矩阵配置
2. **容器原生指令**：利用 `container:` 指令而非 `docker run`，代码更简洁
3. **环境变量契约**：`DESIRED_PYTHON` + `DESIRED_CUDA` 遵循 PyTorch 命名约定
4. **产物独立命名**：每个变体使用 `matrix.build_name` 作为 artifact 名称
5. **条件 artifact 保留期**：`keep-artifacts` 控制 7 天 vs 90 天
6. **并发控制**：定时运行可取消，手动运行不可取消
7. **C 扩展演示**：真实编译 C 代码，展示 manylinux 的核心价值

---

## 资源链接

- [PyTorch 上游 nightly workflow](https://github.com/pytorch/pytorch/blob/main/.github/workflows/generated-linux-binary-manywheel-nightly.yml)
- [PyTorch Builder 仓库](https://github.com/pytorch/builder)
- [Manylinux 官方文档](https://github.com/pypa/manylinux)
- [PEP 600 — manylinux_2_28 规范](https://peps.python.org/pep-0600/)
- [GitHub Actions matrix strategies](https://docs.github.com/en/actions/using-jobs/using-a-build-matrix-for-your-jobs)
- [GitHub Actions container directive](https://docs.github.com/en/actions/using-jobs/running-jobs-in-a-container)
