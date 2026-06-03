"""torch_demo - Demo package for PyTorch community nightly build pipeline."""

import os

from torch_demo._ops import add, version

BUILD_CUDA = os.environ.get("DESIRED_CUDA", "cpu")
BUILD_PYTHON = os.environ.get("DESIRED_PYTHON", "3.12")

__version__ = "2.8.0.dev20250603"
__cuda_variant__ = BUILD_CUDA
__python_version__ = BUILD_PYTHON


def cuda_is_available() -> bool:
    return BUILD_CUDA != "cpu"


def get_build_info() -> dict:
    return {
        "version": __version__,
        "cuda_variant": BUILD_CUDA,
        "python_version": BUILD_PYTHON,
        "cuda_available": cuda_is_available(),
    }
