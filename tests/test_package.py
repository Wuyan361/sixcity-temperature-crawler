"""包元数据一致性测试。"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import sixcity_temp

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.mark.skipif(not PYPROJECT.exists(), reason="仅在源码仓库中存在 pyproject.toml")
def test_package_version_matches_pyproject() -> None:
    """包内版本号与 pyproject.toml 声明一致，避免发布时版本漂移。"""
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == sixcity_temp.__version__


@pytest.mark.skipif(not PYPROJECT.exists(), reason="仅在源码仓库中存在 pyproject.toml")
def test_license_is_declared_and_file_present() -> None:
    """声明的许可证与仓库中的 LICENSE 文件配套。"""
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert metadata["project"]["license"] == "MPL-2.0"
    assert metadata["project"]["license-files"] == ["LICENSE"]
    assert (PYPROJECT.parent / "LICENSE").is_file()
