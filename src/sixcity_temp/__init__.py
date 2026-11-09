"""六地气温爬虫：抓取六城历史与预报气温，导出带样式的 Excel。"""

from __future__ import annotations

from .config import (
    DEFAULT_APPARENT_FILENAME,
    DEFAULT_CITIES,
    DEFAULT_HISTORY_START,
    DEFAULT_RETRIES,
    DEFAULT_TEMPERATURE_FILENAME,
    DEFAULT_TIMEOUT,
    City,
    load_cities,
)
from .errors import ConfigError, DataFetchError, DataFormatError, ExportError, SixCityTempError
from .exporter import export_apparent_workbook, export_temperature_workbook
from .fetcher import (
    CityDataset,
    OpenMeteoClient,
    diagnose_and_retry,
    fetch_city_with_retry,
)
from .processor import build_apparent_table, build_temperature_table
from .weather_codes import describe_weather_code

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_APPARENT_FILENAME",
    "DEFAULT_CITIES",
    "DEFAULT_HISTORY_START",
    "DEFAULT_RETRIES",
    "DEFAULT_TEMPERATURE_FILENAME",
    "DEFAULT_TIMEOUT",
    "City",
    "CityDataset",
    "ConfigError",
    "DataFetchError",
    "DataFormatError",
    "ExportError",
    "OpenMeteoClient",
    "SixCityTempError",
    "__version__",
    "build_apparent_table",
    "build_temperature_table",
    "describe_weather_code",
    "diagnose_and_retry",
    "export_apparent_workbook",
    "export_temperature_workbook",
    "fetch_city_with_retry",
    "load_cities",
]
