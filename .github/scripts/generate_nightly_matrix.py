#!/usr/bin/env python3
"""
Generate build matrix for PyTorch-style community nightly builds.

This script mimics PyTorch's generate_binary_build_matrix.py:
  https://github.com/pytorch/pytorch/blob/main/tools/scripts/generate_binary_build_matrix.py

It produces a JSON matrix consumed by GitHub Actions' strategy.matrix,
with one entry per (Python version, CUDA variant) pair.

Usage:
  python generate_nightly_matrix.py --python-versions "3.10 3.11 3.12 3.13" --cuda-versions "cpu cu124"

Output:
  JSON with an "include" array, each entry representing one build configuration.
"""

import argparse
import json
import sys

# Mapping from CUDA version code to manylinux container image tag
# In production, these would be full manylinux CUDA images.
CUDA_TO_CONTAINER = {
    "cpu": "quay.io/pypa/manylinux_2_28_x86_64:latest",
    "cu124": "quay.io/pypa/manylinux_2_28_x86_64:latest",
    "cu126": "quay.io/pypa/manylinux_2_28_x86_64:latest",
}

# Python ABI tag mapping (cpXY-cpXY) used by manylinux images
PYTHON_ABI = {
    "3.10": "cp310-cp310",
    "3.11": "cp311-cp311",
    "3.12": "cp312-cp312",
    "3.13": "cp313-cp313",
    "3.14": "cp314-cp314",
}


def generate_matrix(
    python_versions: list[str],
    cuda_versions: list[str],
    package_type: str = "manywheel",
) -> dict:
    """Generate the build matrix for GitHub Actions strategy."""

    include_entries = []

    for py_ver in python_versions:
        py_short = py_ver.replace(".", "")
        py_abi = PYTHON_ABI.get(py_ver, f"cp{py_short}-cp{py_short}")

        for cuda_ver in cuda_versions:
            if cuda_ver == "cpu":
                suffix = "cpu"
                cuda_display = "cpu"
            else:
                cuda_num = cuda_ver.replace("cu", "")
                major = cuda_num[:-1] if len(cuda_num) > 2 else cuda_num[:1]
                minor = cuda_num[-1]
                suffix = f"cuda{major}_{minor}"
                cuda_display = f"cuda{major}.{minor}"

            build_name = f"{package_type}-py{py_ver.replace('.', '_')}-{suffix}"

            include_entries.append(
                {
                    "build_name": build_name,
                    "python_version": py_ver,
                    "python_abi": py_abi,
                    "cuda_version": cuda_ver,
                    "cuda_display": cuda_display,
                    "package_type": package_type,
                    "container": CUDA_TO_CONTAINER[cuda_ver],
                    "artifact_name": f"wheel-{build_name}",
                }
            )

    return {"include": include_entries}


def main():
    parser = argparse.ArgumentParser(
        description="Generate PyTorch-style nightly build matrix"
    )
    parser.add_argument(
        "--python-versions",
        default="3.10 3.11 3.12 3.13",
        help="Space-separated Python versions (default: '3.10 3.11 3.12 3.13')",
    )
    parser.add_argument(
        "--cuda-versions",
        default="cpu cu124",
        help="Space-separated CUDA variants (default: 'cpu cu124')",
    )
    parser.add_argument(
        "--package-type",
        default="manywheel",
        help="Package type (default: 'manywheel')",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Write matrix JSON to file instead of stdout",
    )
    args = parser.parse_args()

    py_versions = args.python_versions.split()
    cuda_versions = args.cuda_versions.split()

    matrix = generate_matrix(py_versions, cuda_versions, args.package_type)

    output = json.dumps(matrix, indent=2)

    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(output)
        print(f"Matrix written to {args.output_file}")
    else:
        print(output)


if __name__ == "__main__":
    main()
