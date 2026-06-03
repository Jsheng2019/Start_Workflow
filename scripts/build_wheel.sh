#!/bin/bash
# =============================================================================
# Build PyTorch community nightly wheel
# =============================================================================
# This script mimics PyTorch's .ci/manywheel/build.sh pattern:
#   1. Source the binary environment file
#   2. Build the wheel using the correct Python version
#   3. Output wheel to dist/
#
# Environment variables (set by the workflow, matching PyTorch convention):
#   DESIRED_PYTHON    - Target Python version (e.g., "3.12")
#   DESIRED_CUDA      - Target CUDA variant (e.g., "cpu", "cu124")
#   PACKAGE_TYPE      - Package type (e.g., "manywheel")
#   BUILD_ENVIRONMENT - Build environment label
# =============================================================================

set -euo pipefail

# ---- Manylinux Python path resolution ----
# In manylinux images, Pythons live at /opt/python/cpXY-cpXY/bin/python
PYTHON_VERSION="${DESIRED_PYTHON:-3.12}"
CUDA_VERSION="${DESIRED_CUDA:-cpu}"
PACKAGE_TYPE="${PACKAGE_TYPE:-manywheel}"
BUILD_ENV="${BUILD_ENVIRONMENT:-linux-binary-manywheel}"

PYTHON_SHORT="cp${PYTHON_VERSION//./}"
PYTHON_BIN="/opt/python/${PYTHON_SHORT}-${PYTHON_SHORT}/bin/python"

echo "============================================"
echo " PyTorch Community Nightly Build (Demo)"
echo "============================================"
echo " Python:       ${PYTHON_VERSION}  (${PYTHON_SHORT})"
echo " CUDA:         ${CUDA_VERSION}"
echo " Package:      ${PACKAGE_TYPE}"
echo " Build env:    ${BUILD_ENV}"
echo " Python bin:   ${PYTHON_BIN}"
echo "============================================"

# Verify Python exists
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python ${PYTHON_VERSION} not found at ${PYTHON_BIN}"
    echo "Available Pythons:"
    ls /opt/python/ 2>/dev/null || echo "  (none found)"
    exit 1
fi

${PYTHON_BIN} --version

# ---- Build the wheel ----
# In the real PyTorch pipeline, this step:
#   1. Compiles 100+ C/C++/CUDA source files
#   2. Links against cuDNN, NCCL, BLAS, etc.
#   3. Produces a ~200MB manylinux wheel
#
# For this demo, we build a tiny C extension wheel that demonstrates
# the same pipeline structure in seconds.

echo ""
echo "--- Installing build dependencies ---"
${PYTHON_BIN} -m pip install --quiet build setuptools wheel

echo ""
echo "--- Building ${PACKAGE_TYPE} wheel for Python ${PYTHON_VERSION} (${CUDA_VERSION}) ---"
cd "${GITHUB_WORKSPACE:-.}/demo-pytorch"

export DESIRED_PYTHON="${PYTHON_VERSION}"
export DESIRED_CUDA="${CUDA_VERSION}"

${PYTHON_BIN} -m build --wheel --outdir dist/

echo ""
echo "--- Build complete ---"
ls -lh dist/

# Write the binary env file (PyTorch convention)
# In production, this is sourced by downstream test/upload scripts
BINARY_ENV_FILE="${BINARY_ENV_FILE:-/tmp/env}"
cat > "${BINARY_ENV_FILE}" << EOF
PYTHON_VERSION=${PYTHON_VERSION}
CUDA_VERSION=${CUDA_VERSION}
PACKAGE_TYPE=${PACKAGE_TYPE}
BUILD_ENVIRONMENT=${BUILD_ENV}
WHEEL_DIR=${GITHUB_WORKSPACE:-.}/demo-pytorch/dist
EOF

echo "Binary env written to ${BINARY_ENV_FILE}"
