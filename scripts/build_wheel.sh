#!/bin/bash
# =============================================================================
# Build PyTorch Wheel from Source (REAL COMPILATION)
# =============================================================================
# This script is designed to run inside a pytorch/manylinux2_28-builder
# container. It clones the PyTorch repository, compiles the full C++/CUDA
# library from source, and produces a manylinux-compatible wheel.
#
# This mirrors what PyTorch's own CI does in:
#   .ci/pytorch/build.sh
#   .ci/pytorch/binary_populate_env.sh
#   manywheel/build.sh (pytorch/builder repo)
#
# Environment variables (set by the workflow):
#   DESIRED_PYTHON       - Target Python version (e.g., "3.12")
#   DESIRED_CUDA         - CUDA variant (e.g., "cpu", "cu124")
#   MAX_JOBS             - Parallel compile jobs (default: 2)
#   PYTORCH_BUILD_VERSION - Version string override (auto-generated if unset)
# =============================================================================

set -euo pipefail

# ---- Resolve Python in manylinux container ----
PYTHON_VERSION="${DESIRED_PYTHON:-3.12}"
CUDA_VERSION="${DESIRED_CUDA:-cpu}"
PY_SHORT="cp${PYTHON_VERSION//./}"
PYTHON_BIN="/opt/python/${PY_SHORT}-${PY_SHORT}/bin/python"

echo "============================================"
echo " PyTorch Community Nightly Build"
echo "============================================"
echo " Python:        ${PYTHON_VERSION}  (${PY_SHORT})"
echo " CUDA variant:  ${CUDA_VERSION}"
echo " Max jobs:      ${MAX_JOBS:-2}"
echo " Build env:     ${BUILD_ENVIRONMENT:-linux-binary-manywheel}"
echo " Python path:   ${PYTHON_BIN}"
echo "============================================"

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python ${PYTHON_VERSION} not found in container"
    echo "Available:"
    ls /opt/python/ 2>/dev/null || echo "  (none)"
    exit 1
fi

${PYTHON_BIN} --version

# ---- Clone PyTorch source ----
PYTORCH_DIR="${GITHUB_WORKSPACE:-/tmp}/pytorch-src"
if [ ! -f "${PYTORCH_DIR}/CMakeLists.txt" ]; then
    echo ""
    echo "--- Cloning PyTorch (depth=1, branch=main) ---"
    git clone --depth=1 --branch=main --single-branch \
        https://github.com/pytorch/pytorch.git "${PYTORCH_DIR}"
    echo "Clone complete ($(du -sh "${PYTORCH_DIR}" | cut -f1))"
else
    echo ""
    echo "--- Using existing PyTorch source ---"
    cd "${PYTORCH_DIR}"
    echo "Commit: $(git rev-parse --short HEAD)"
fi

cd "${PYTORCH_DIR}"
PYTORCH_COMMIT=$(git rev-parse --short HEAD)
echo "PyTorch commit: ${PYTORCH_COMMIT}"
echo "PyTorch dir size: $(du -sh . 2>/dev/null | cut -f1)"

# ---- Initialize minimal submodules ----
echo ""
echo "--- Initializing submodules ---"
# PyTorch needs these submodules even for CPU builds
git submodule update --init --depth=1 --jobs=2 \
    third_party/pybind11 \
    third_party/cpuinfo \
    third_party/FP16 \
    third_party/FXdiv \
    third_party/pthreadpool \
    third_party/psimd \
    third_party/XNNPACK \
    third_party/NEON_2_SSE \
    2>/dev/null || echo "  (some submodules may not exist; continuing)"

# ---- Set build version ----
if [ -z "${PYTORCH_BUILD_VERSION:-}" ]; then
    if [ -f version.txt ]; then
        BASE_VER=$(head -1 version.txt | sed 's/a.*//')
    else
        BASE_VER="2.8.0"
    fi
    PYTORCH_BUILD_VERSION="${BASE_VER}.dev$(date +%Y%m%d)"
fi
export PYTORCH_BUILD_VERSION
export PYTORCH_BUILD_NUMBER=1

echo ""
echo "Build version: ${PYTORCH_BUILD_VERSION}+${CUDA_VERSION}"

# ---- Install build dependencies ----
echo ""
echo "--- Installing build dependencies ---"
${PYTHON_BIN} -m pip install --quiet --upgrade pip
${PYTHON_BIN} -m pip install --quiet -r requirements.txt 2>&1 | tail -5
${PYTHON_BIN} -m pip install --quiet build wheel setuptools

# ---- Configure ccache (if available) ----
if command -v ccache &>/dev/null; then
    export CCACHE_DIR="${CCACHE_DIR:-${HOME}/.ccache}"
    ccache -M 2G 2>/dev/null || true
    ccache -z 2>/dev/null || true
    export CMAKE_C_COMPILER_LAUNCHER=ccache
    export CMAKE_CXX_COMPILER_LAUNCHER=ccache
    echo "ccache: $(ccache -V 2>/dev/null | head -1), max: $(ccache -M 2>/dev/null || echo '2G')"
fi

# ---- Build environment variables ----
# These match the settings PyTorch's CI uses for CPU-only builds.
# We disable everything non-essential to keep build time reasonable
# on standard GitHub runners (2 cores, 7 GB RAM).
export USE_CUDA=0
export USE_CUDNN=0
export USE_FBGEMM=1
export USE_DISTRIBUTED=0
export USE_NCCL=0
export BUILD_TEST=0
export BUILD_CAFFE2_OPS=0
export MAX_JOBS="${MAX_JOBS:-2}"
export CMAKE_BUILD_TYPE=Release
export ATEN_THREADING=NATIVE
export USE_GOLD_LINKER=ON

echo ""
echo "Build configuration:"
echo "  USE_CUDA=${USE_CUDA}"
echo "  BUILD_TEST=${BUILD_TEST}"
echo "  MAX_JOBS=${MAX_JOBS}"
echo "  CMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}"

# ---- BUILD ----
echo ""
echo "============================================"
echo " STARTING PYTORCH COMPILATION"
echo " This compiles ~3000 C++ source files."
echo " Estimated: 2–4 hours on standard runner."
echo "============================================"
echo ""

cd "${PYTORCH_DIR}"
BUILD_START=$(date +%s)

# Clean any previous build artifacts
${PYTHON_BIN} setup.py clean 2>/dev/null || true

# Build the wheel
# We use setup.py bdist_wheel (traditional method) rather than
# python -m build because it gives more control over the build process.
${PYTHON_BIN} setup.py bdist_wheel

BUILD_END=$(date +%s)
BUILD_ELAPSED=$((BUILD_END - BUILD_START))
BUILD_MIN=$((BUILD_ELAPSED / 60))

echo ""
echo "============================================"
echo " BUILD COMPLETE"
echo " Duration: ${BUILD_MIN} minutes"
echo "============================================"

# ---- Show results ----
echo ""
echo "--- Built wheels ---"
ls -lh "${PYTORCH_DIR}/dist/" 2>/dev/null || echo "  (no wheels found)"

# Show ccache stats
if command -v ccache &>/dev/null; then
    echo ""
    echo "--- ccache statistics ---"
    ccache -s 2>/dev/null || true
fi

echo ""
echo "Wheel location: ${PYTORCH_DIR}/dist/"
