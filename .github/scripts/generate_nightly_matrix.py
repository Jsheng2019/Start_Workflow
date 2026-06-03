#!/usr/bin/env python3
"""
Generate build matrix for PyTorch community nightly builds.

Mimics PyTorch's generate_binary_build_matrix.py:
  https://github.com/pytorch/pytorch/blob/main/tools/scripts/generate_binary_build_matrix.py

Each matrix entry = one (Python version, CUDA variant) tuple.
Uses pytorch/manylinux2_28-builder images — the SAME images PyTorch's CI uses.

Usage:
  python generate_nightly_matrix.py --python-versions "3.12" --cuda-versions "cpu"
"""

import argparse
import json

# Container images that match PyTorch's own CI
# These are the EXACT same images used by pytorch/pytorch nightly builds.
# ref: .ci/pytorch/binary_populate_env.sh
CUDA_TO_CONTAINER = {
    "cpu": "pytorch/manylinux2_28-builder:cpu",
    "cu124": "pytorch/manylinux2_28-builder:cuda12.4",
    "cu126": "pytorch/manylinux2_28-builder:cuda12.6",
}

PYTHON_ABI = {
    "3.10": "cp310-cp310",
    "3.11": "cp311-cp311",
    "3.12": "cp312-cp312",
    "3.13": "cp313-cp313",
}


def generate_matrix(
    python_versions: list[str],
    cuda_versions: list[str],
    package_type: str = "manywheel",
) -> dict:
    include_entries = []

    for py_ver in python_versions:
        py_abi = PYTHON_ABI.get(py_ver, f"cp{py_ver.replace('.', '')}-cp{py_ver.replace('.', '')}")

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

            include_entries.append({
                "build_name": build_name,
                "python_version": py_ver,
                "python_abi": py_abi,
                "cuda_version": cuda_ver,
                "cuda_display": cuda_display,
                "package_type": package_type,
                "container": CUDA_TO_CONTAINER.get(cuda_ver, CUDA_TO_CONTAINER["cpu"]),
            })

    return {"include": include_entries}


def main():
    parser = argparse.ArgumentParser(description="Generate PyTorch nightly build matrix")
    parser.add_argument("--python-versions", default="3.12",
                        help="Space-separated Python versions (default: '3.12')")
    parser.add_argument("--cuda-versions", default="cpu",
                        help="Space-separated CUDA variants (default: 'cpu')")
    parser.add_argument("--package-type", default="manywheel")
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    matrix = generate_matrix(
        args.python_versions.split(),
        args.cuda_versions.split(),
        args.package_type,
    )

    output = json.dumps(matrix, indent=2)
    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(output)
        print(f"Matrix ({len(matrix['include'])} entries) → {args.output_file}")
    else:
        print(output)


if __name__ == "__main__":
    main()
