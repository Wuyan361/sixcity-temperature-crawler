"""城市配置加载测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sixcity_temp.config import DEFAULT_CITIES, load_cities
from sixcity_temp.errors import ConfigError


def test_load_cities_reads_dict_format(tmp_path: Path) -> None:
    """支持 {"cities": [...]} 格式。"""
    path = tmp_path / "cities.json"
    path.write_text(
        json.dumps(
            {"cities": [{"name": "广州", "latitude": 23.1291, "longitude": 113.2644}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cities = load_cities(path)

    assert len(cities) == 1
    assert cities[0].name == "广州"
    assert cities[0].latitude == pytest.approx(23.1291)


def test_load_cities_reads_bare_list(tmp_path: Path) -> None:
    """支持直接给出城市数组。"""
    path = tmp_path / "cities.json"
    path.write_text(
        json.dumps(
            [{"name": "深圳", "latitude": 22.5431, "longitude": 114.0579}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cities = load_cities(path)

    assert [city.name for city in cities] == ["深圳"]


def test_load_cities_raises_when_file_missing(tmp_path: Path) -> None:
    """文件不存在时抛出配置错误。"""
    with pytest.raises(ConfigError, match="不存在"):
        load_cities(tmp_path / "missing.json")


def test_load_cities_raises_when_json_invalid(tmp_path: Path) -> None:
    """JSON 非法时抛出配置错误。"""
    path = tmp_path / "cities.json"
    path.write_text("{ 不是 JSON", encoding="utf-8")

    with pytest.raises(ConfigError, match="不是合法 JSON"):
        load_cities(path)


def test_load_cities_raises_when_cities_missing(tmp_path: Path) -> None:
    """缺少 cities 列表时抛出配置错误。"""
    path = tmp_path / "cities.json"
    path.write_text(json.dumps({"others": []}), encoding="utf-8")

    with pytest.raises(ConfigError, match="cities"):
        load_cities(path)


def test_load_cities_raises_when_name_invalid(tmp_path: Path) -> None:
    """缺少 name 字段时抛出配置错误。"""
    path = tmp_path / "cities.json"
    path.write_text(
        json.dumps({"cities": [{"latitude": 23.1, "longitude": 113.2}]}), encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="name"):
        load_cities(path)


def test_load_cities_raises_when_coordinate_not_number(tmp_path: Path) -> None:
    """经纬度不是数字时抛出配置错误。"""
    path = tmp_path / "cities.json"
    path.write_text(
        json.dumps({"cities": [{"name": "广州", "latitude": "北纬", "longitude": 113.2}]}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="latitude"):
        load_cities(path)


def test_load_cities_raises_when_coordinate_out_of_range(tmp_path: Path) -> None:
    """纬度越界时抛出配置错误。"""
    path = tmp_path / "cities.json"
    path.write_text(
        json.dumps({"cities": [{"name": "广州", "latitude": 200, "longitude": 113.2}]}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="纬度"):
        load_cities(path)


def test_default_cities_cover_six_cities() -> None:
    """内置配置固定包含六个城市。"""
    assert [city.name for city in DEFAULT_CITIES] == [
        "海南",
        "韶关",
        "梅州",
        "茂名",
        "广州",
        "深圳",
    ]
