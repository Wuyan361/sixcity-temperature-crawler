"""项目自定义异常。"""

from __future__ import annotations


class SixCityTempError(Exception):
    """本项目所有自定义异常的基类。"""


class ConfigError(SixCityTempError):
    """配置文件或命令行参数不合法。"""


class DataFetchError(SixCityTempError):
    """网络请求失败，或接口返回了无法解析的数据。"""


class DataFormatError(SixCityTempError):
    """接口返回结构与预期不符（缺少 hourly / daily 等字段）。"""


class ExportError(SixCityTempError):
    """Excel 写出失败，例如文件被 WPS / Excel 占用。"""
