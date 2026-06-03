"""Tests for torch_demo package — validates wheel installation."""

import pytest

try:
    import torch_demo
    from torch_demo._ops import add, version
except ImportError:
    torch_demo = None
    add = None
    version = None


@pytest.mark.skipif(torch_demo is None, reason="torch_demo not installed")
class TestTorchDemo:
    def test_version(self):
        assert version() == "2.8.0.dev20250603"

    def test_add(self):
        assert add(1, 2) == 3
        assert add(-1, 1) == 0
        assert add(0, 0) == 0

    def test_cuda_available(self):
        info = torch_demo.get_build_info()
        assert "version" in info
        assert "cuda_variant" in info
        assert "python_version" in info
        assert "cuda_available" in info

    def test_build_info_consistency(self):
        info = torch_demo.get_build_info()
        assert info["version"] == torch_demo.__version__
        assert info["cuda_available"] == torch_demo.cuda_is_available()
