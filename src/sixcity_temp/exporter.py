"""Excel 导出与样式美化。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from .errors import ExportError

LOGGER = logging.getLogger(__name__)

DOCUMENT_CREATOR: str = "sixcity-temperature-crawler"
"""写入 Excel 文档属性的作者标识。

刻意不写入运行者的用户名或机器名，避免产出的表格携带可追溯到个人的信息。
"""

HEADER_FONT: Font = Font(bold=True)
THIN_BORDER: Border = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER_ALIGNMENT: Alignment = Alignment(horizontal="center", vertical="center")
TODAY_FILL: PatternFill = PatternFill(start_color="FFDDC1", end_color="FFDDC1", fill_type="solid")


def export_temperature_workbook(
    path: Path,
    tables: Mapping[str, pd.DataFrame],
    today: date,
    *,
    style: bool = True,
) -> Path:
    """写出气温 Excel：每个城市一个工作表。

    Args:
        path: 输出文件路径。
        tables: 城市名到宽表的映射。
        today: 需要高亮的当天日期。
        style: 是否美化样式。

    Returns:
        实际写出的文件路径。

    Raises:
        ExportError: 文件被占用或无法写出。
    """
    return _export(
        path,
        tables,
        today,
        style=style,
        freeze_panes="F2",
        explicit_widths={"A": 15, "B": 10, "C": 12, "D": 12, "E": 12},
        narrow_from=6,
    )


def export_apparent_workbook(
    path: Path,
    tables: Mapping[str, pd.DataFrame],
    today: date,
    *,
    style: bool = True,
) -> Path:
    """写出体感温度 Excel：每个城市一个工作表。

    Args:
        path: 输出文件路径。
        tables: 城市名到宽表的映射。
        today: 需要高亮的当天日期。
        style: 是否美化样式。

    Returns:
        实际写出的文件路径。

    Raises:
        ExportError: 文件被占用或无法写出。
    """
    return _export(
        path,
        tables,
        today,
        style=style,
        freeze_panes="E2",
        explicit_widths={"A": 15, "B": 12, "C": 12, "D": 12},
        narrow_from=5,
    )


def _export(
    path: Path,
    tables: Mapping[str, pd.DataFrame],
    today: date,
    *,
    style: bool,
    freeze_panes: str,
    explicit_widths: Mapping[str, int],
    narrow_from: int,
) -> Path:
    """所有工作簿写出的公共实现。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            _set_neutral_properties(writer.book, path)
            for city_name, table in tables.items():
                table.to_excel(writer, sheet_name=city_name)
            if style:
                workbook = writer.book
                for city_name, table in tables.items():
                    _style_worksheet(
                        workbook[city_name],
                        table,
                        today,
                        freeze_panes=freeze_panes,
                        explicit_widths=explicit_widths,
                        narrow_from=narrow_from,
                    )
    except PermissionError as error:
        raise ExportError(
            f"无法写入「{path.name}」：文件可能正在 WPS / Excel 中打开，请关闭后重试。"
        ) from error
    LOGGER.info("已写出 %s", path)
    return path


def _set_neutral_properties(workbook: Workbook, path: Path) -> None:
    """设置与运行者无关的文档属性。

    表格对外分享时，文档属性里的作者字段是最容易被忽略的身份泄漏点；
    这里固定写项目标识，不写运行者的用户名或机器名。
    """
    properties = workbook.properties
    properties.creator = DOCUMENT_CREATOR
    properties.lastModifiedBy = DOCUMENT_CREATOR
    properties.title = path.stem
    properties.description = "由六地气温爬虫生成，数据来源 Open-Meteo"
    properties.keywords = "weather,open-meteo,temperature"
    properties.language = "zh-CN"


def _style_worksheet(
    worksheet: Worksheet,
    table: pd.DataFrame,
    today: date,
    *,
    freeze_panes: str,
    explicit_widths: Mapping[str, int],
    narrow_from: int,
) -> None:
    """设置冻结窗格、列宽、边框、居中与当天行高亮。"""
    worksheet.freeze_panes = freeze_panes
    worksheet.row_dimensions[1].height = 20
    for column_letter, width in explicit_widths.items():
        worksheet.column_dimensions[column_letter].width = width
    for index in range(narrow_from, worksheet.max_column + 1):
        worksheet.column_dimensions[get_column_letter(index)].width = 8

    today_row = _today_row_index(table, today)
    for row_index, row in enumerate(worksheet.iter_rows(), start=1):
        if row_index > 1:
            worksheet.row_dimensions[row_index].height = 18
        is_today = today_row is not None and row_index == today_row
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGNMENT
            if row_index == 1:
                cell.font = HEADER_FONT
            if is_today:
                cell.fill = TODAY_FILL

    if today_row is not None:
        cell_ref = f"A{today_row}"
        for selection in worksheet.sheet_view.selection:
            selection.activeCell = cell_ref
            selection.sqref = cell_ref


def _today_row_index(table: pd.DataFrame, today: date) -> int | None:
    """今天所在行的 Excel 行号（含表头偏移）；今天不在表中时返回 ``None``。"""
    try:
        location = table.index.get_loc(today)
    except KeyError:
        return None
    if not isinstance(location, int):
        return None
    return location + 2
