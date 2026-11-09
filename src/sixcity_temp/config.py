"""城市定义、默认参数与自定义城市配置加载。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from .errors import ConfigError

DEFAULT_HISTORY_START: Final[date] = date(2025, 1, 1)
DEFAULT_TIMEOUT: Final[int] = 30
DEFAULT_RETRIES: Final[int] = 3
DEFAULT_TEMPERATURE_FILENAME: Final[str] = "六地气温(历史+预报).xlsx"
DEFAULT_APPARENT_FILENAME: Final[str] = "六地体感温度(历史+预报).xlsx"


@dataclass(frozen=True)
class City:
    """需要抓取的一个城市。

    Attributes:
        name: 城市名称，同时用作 Excel 工作表名。
        latitude: 北纬，正值表示北半球。
        longitude: 东经，正值表示东半球。
    """

    name: str
    latitude: float
    longitude: float


DEFAULT_CITIES: Final[tuple[City, ...]] = (
    City("海南", 20.0469, 110.3417),
    City("韶关", 24.8104, 113.5975),
    City("梅州", 24.2890, 116.1220),
    City("茂名", 21.6633, 110.9255),
    City("广州", 23.1291, 113.2644),
    City("深圳", 22.5431, 114.0579),
)


def load_cities(path: Path) -> list[City]:
    """从 JSON 文件读取城市列表。

    支持两种格式：``{"cities": [...]}`` 或直接是城市数组。
    单个城市需要包含 ``name``、``latitude``、``longitude`` 三个字段。

    Args:
        path: JSON 配置文件路径。

    Returns:
        城市列表。

    Raises:
        ConfigError: 文件不存在、JSON 非法或字段不合法。
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"城市配置文件不存在：{path}") from error
    except OSError as error:
        raise ConfigError(f"城市配置文件无法读取：{path}（{error}）") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"城市配置文件不是合法 JSON：{path}（{error}）") from error

    entries = raw.get("cities") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"城市配置文件缺少非空的 cities 列表：{path}")

    return [_parse_city(entry, path, index) for index, entry in enumerate(entries)]


def _parse_city(entry: object, path: Path, index: int) -> City:
    """把 JSON 中的一项解析为 :class:`City`。"""
    if not isinstance(entry, dict):
        raise ConfigError(f"{path} 第 {index + 1} 项不是对象：{entry!r}")

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{path} 第 {index + 1} 项缺少合法的 name 字段")

    latitude = _parse_coordinate(entry.get("latitude"), path, name, "latitude")
    longitude = _parse_coordinate(entry.get("longitude"), path, name, "longitude")
    if not -90 <= latitude <= 90:
        raise ConfigError(f"{path} 中城市「{name}」的纬度 {latitude} 超出 -90~90 范围")
    if not -180 <= longitude <= 180:
        raise ConfigError(f"{path} 中城市「{name}」的经度 {longitude} 超出 -180~180 范围")

    return City(name=name.strip(), latitude=latitude, longitude=longitude)


def _parse_coordinate(value: object, path: Path, name: str, field: str) -> float:
    """解析单个经纬度字段。"""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{path} 中城市「{name}」的 {field} 不是数字：{value!r}") from error
