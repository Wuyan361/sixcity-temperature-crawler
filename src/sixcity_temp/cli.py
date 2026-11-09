"""命令行入口。"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

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
from .errors import ConfigError, ExportError
from .exporter import export_apparent_workbook, export_temperature_workbook
from .fetcher import CityDataset, OpenMeteoClient, diagnose_and_retry, fetch_city_with_retry
from .processor import build_apparent_table, build_temperature_table

LOGGER = logging.getLogger(__name__)

EXIT_OK: int = 0
EXIT_PARTIAL: int = 1
EXIT_USAGE: int = 2
EXIT_EXPORT: int = 3


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="sixcity-temp",
        description=(
            "六地气温爬虫：抓取海南、韶关、梅州、茂名、广州、深圳的历史与预报气温，"
            "导出带样式的 Excel。"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Excel 输出目录",
    )
    parser.add_argument(
        "--history-start",
        default=DEFAULT_HISTORY_START.isoformat(),
        help="历史数据起始日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--cities",
        type=Path,
        default=None,
        help="自定义城市 JSON 文件，默认使用内置的六个城市",
    )
    parser.add_argument(
        "--only-city",
        action="append",
        default=None,
        metavar="城市名",
        help="只抓取指定城市，可重复传入",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次请求超时秒数")
    parser.add_argument(
        "--retries", type=int, default=DEFAULT_RETRIES, help="单个城市的最大尝试次数"
    )
    parser.add_argument("--no-style", action="store_true", help="不美化 Excel，只写原始数据")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[int], OpenMeteoClient] | None = None,
) -> int:
    """执行一次抓取并导出。

    Args:
        argv: 命令行参数列表，``None`` 表示直接读取进程参数。
        client_factory: 客户端工厂，便于测试时注入假客户端。

    Returns:
        进程退出码：0 全部成功，1 部分城市失败，2 参数或配置错误，3 导出失败。
    """
    args = build_parser().parse_args(argv)
    _configure_logging(args.log_level)

    try:
        history_start = date.fromisoformat(args.history_start)
    except ValueError:
        LOGGER.error("--history-start 需要 YYYY-MM-DD 格式，当前值：%s", args.history_start)
        return EXIT_USAGE

    try:
        cities = load_cities(args.cities) if args.cities else list(DEFAULT_CITIES)
    except ConfigError as error:
        LOGGER.error("%s", error)
        return EXIT_USAGE

    if args.only_city:
        wanted = set(args.only_city)
        cities = [city for city in cities if city.name in wanted]
        if not cities:
            LOGGER.error(
                "没有匹配到城市：%s（可选：%s）",
                "、".join(args.only_city),
                "、".join(city.name for city in DEFAULT_CITIES),
            )
            return EXIT_USAGE

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    factory = client_factory if client_factory is not None else _default_client_factory
    client = factory(args.timeout)

    datasets, failed = _collect_datasets(client, cities, history_start, args.retries)
    if not datasets:
        LOGGER.error("所有城市都抓取失败，没有生成任何文件。")
        return EXIT_PARTIAL

    today = date.today()
    temperature_tables = {
        name: build_temperature_table(dataset, today) for name, dataset in datasets.items()
    }
    apparent_tables = {
        name: build_apparent_table(dataset, today) for name, dataset in datasets.items()
    }

    try:
        export_temperature_workbook(
            output_dir / DEFAULT_TEMPERATURE_FILENAME,
            temperature_tables,
            today,
            style=not args.no_style,
        )
        export_apparent_workbook(
            output_dir / DEFAULT_APPARENT_FILENAME,
            apparent_tables,
            today,
            style=not args.no_style,
        )
    except ExportError as error:
        LOGGER.error("%s", error)
        return EXIT_EXPORT

    LOGGER.info("全部完成：%d 个城市成功，%d 个城市失败。", len(datasets), len(failed))
    if failed:
        LOGGER.warning("失败城市：%s", "、".join(failed))
        return EXIT_PARTIAL
    return EXIT_OK


def _default_client_factory(timeout: int) -> OpenMeteoClient:
    """默认的客户端工厂。"""
    return OpenMeteoClient(timeout=timeout)


def _collect_datasets(
    client: OpenMeteoClient,
    cities: Sequence[City],
    history_start: date,
    retries: int,
) -> tuple[dict[str, CityDataset], dict[str, Exception]]:
    """逐个抓取城市，失败时做一次针对性补救。"""
    datasets: dict[str, CityDataset] = {}
    failed: dict[str, Exception] = {}

    for city in cities:
        LOGGER.info("开始抓取 %s（%.4f, %.4f）", city.name, city.latitude, city.longitude)
        dataset, error = fetch_city_with_retry(client, city, history_start, max_retries=retries)
        if dataset is None:
            LOGGER.info("%s 重试 %d 次仍失败，尝试针对性补救。", city.name, retries)
            dataset = diagnose_and_retry(client, city, history_start, error) if error else None
        if dataset is None:
            failed[city.name] = error if error is not None else RuntimeError("未知错误")
            LOGGER.error("%s 抓取失败，本城市本次不生成数据。", city.name)
        else:
            datasets[city.name] = dataset
            LOGGER.info("%s 抓取完成。", city.name)

    return datasets, failed


def _configure_logging(level_name: str) -> None:
    """配置根日志。"""
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def main() -> None:
    """命令行程序入口。"""
    _force_utf8_output()
    raise SystemExit(run())


def _force_utf8_output() -> None:
    """把标准输出统一成 UTF-8。

    Windows 上重定向到文件时，Python 会退回系统 ANSI 代码页，
    导致中文日志乱码；这里固定成 UTF-8，保证任何输出去向都可读。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - 取决于运行环境
            continue
