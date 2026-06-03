import os
from setuptools import setup, Extension, find_packages

CUDA_VERSION = os.environ.get("DESIRED_CUDA", "cpu")
PYTHON_VERSION = os.environ.get("DESIRED_PYTHON", "3.12")

# Tiny C extension to demonstrate real manylinux wheel building
# In the real PyTorch pipeline, this would be 100+ C/C++/CUDA source files
ops_extension = Extension(
    "torch_demo._ops",
    sources=["torch_demo/_ops.c"],
    extra_compile_args=["-O2", "-fPIC"],
)

setup(
    name="torch_demo",
    version=f"2.8.0.dev20250603+{CUDA_VERSION}",
    description="Demo package mimicking PyTorch community nightly build pipeline",
    author="Start_Workflow",
    python_requires=f">={PYTHON_VERSION}",
    packages=find_packages(),
    ext_modules=[ops_extension],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
