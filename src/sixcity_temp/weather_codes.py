"""WMO 天气代码到中文描述的映射。"""

from __future__ import annotations

from typing import Final

UNKNOWN_WEATHER: Final[str] = "未知"

WEATHER_CODE_DESCRIPTIONS: Final[dict[int, str]] = {
    0: "晴",
    1: "基本晴朗",
    2: "部分多云",
    3: "阴天",
    45: "雾",
    48: "沉积的霜雾",
    51: "毛毛雨: 轻度",
    53: "毛毛雨: 中度",
    55: "毛毛雨: 强度",
    56: "冰冻毛毛雨: 轻度",
    57: "冰冻毛毛雨: 强度",
    61: "雨: 轻度",
    63: "雨: 中度",
    65: "雨: 强度",
    66: "冻雨: 轻度",
    67: "冻雨: 强度",
    71: "降雪: 轻度",
    73: "降雪: 中度",
    75: "降雪: 强度",
    77: "雪粒",
    80: "阵雨: 轻度",
    81: "阵雨: 中度",
    82: "阵雨: 猛烈",
    85: "阵雪: 轻度",
    86: "阵雪: 强度",
    95: "雷暴: 轻度或中度",
    96: "雷暴伴有轻度冰雹",
    99: "雷暴伴有强度冰雹",
}


def describe_weather_code(code: object) -> str:
    """把 WMO 天气代码翻译成中文描述。

    Args:
        code: 天气代码，缺失或无法识别时返回「未知」。

    Returns:
        中文天气描述。
    """
    if code is None:
        return UNKNOWN_WEATHER
    try:
        return WEATHER_CODE_DESCRIPTIONS.get(int(code), UNKNOWN_WEATHER)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return UNKNOWN_WEATHER
