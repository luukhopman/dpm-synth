"""Templates and a package reader shared by the tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from dpmxbrl import Report
from dpmxl import CellQuery, DataPoint, Item, Number, Value, axis_matches

from dpmsynth import TEMPLATE_FORMAT, ModuleTemplate, OpenKey

SAMPLES = Path(__file__).parent.parent / "docs" / "samples"


def sample(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def cell(row, column, number, data_type="m", sheet=None, items=None):
    return {
        "id": f"cell-{number}",
        "row": row,
        "column": column,
        "sheet": sheet,
        "datapoint": f"dp{number}",
        "data_type": data_type,
        "items": items,
    }


def document(cells, rules, *, open_keys=(), decimals=None, more_tables=()):
    """A template with one table T and the given cells and rules."""
    raw: dict[str, Any] = {
        "format": TEMPLATE_FORMAT,
        "release": "1.0",
        "module": "TEST",
        "reference_date": "2026-12-31",
        "tables": [
            {"code": "T", "open_keys": list(open_keys), "cells": list(cells)},
            *more_tables,
        ],
        "rules": [
            {"code": f"r{index}", "expression": expression}
            if isinstance(expression, str)
            else expression
            for index, expression in enumerate(rules, 1)
        ],
    }
    if decimals is not None:
        raw["decimals"] = decimals
    return raw


_DECIMALS = {
    "m": "decimalsMonetary",
    "p": "decimalsPercentage",
    "i": "decimalsInteger",
    "r": "decimalsDecimal",
}


class PackageProvider:
    """A dpm-xl provider over a report read back with dpm-xbrl.

    It knows nothing of dpm-synth's own values: every value comes from the
    written package, placed by the template's datapoints.
    """

    def __init__(self, template: ModuleTemplate, report: Report) -> None:
        self.template = template
        self.report = report
        self.rows: dict[str, dict[tuple, dict[str, Value]]] = {}
        for fact in report.facts:
            table = template.table(fact.template or "")
            assert table is not None, fact.template
            cell = next(c for c in table.cells if c.datapoint == fact.datapoint)
            columns = {key.column: key for key in table.open_keys}
            keys = tuple(
                (columns[column].code, _key(columns[column], text))
                for column, text in fact.keys.items()
            )
            self.rows.setdefault(table.code, {}).setdefault(keys, {})[
                fact.datapoint or ""
            ] = self.value(cell.data_type, fact.value)

    def value(self, data_type: str | None, text: str | None) -> Value:
        if text is None:
            return None
        if data_type in _DECIMALS:
            decimals = self.report.decimals_parameters.get(_DECIMALS[data_type])
            return Number.of(Decimal(text), decimals)
        if data_type in ("e", "es"):
            return Item.parse(text)
        if data_type == "b":
            return text == "true"
        if data_type == "d":
            return date.fromisoformat(text)
        return text

    def select(self, query: CellQuery) -> Sequence[DataPoint]:
        table = self.template.table(query.table)
        if table is None:
            raise LookupError(query.table)
        points = []
        for keys, values in self.rows.get(table.code, {}).items():
            for cell in table.cells:
                if all(
                    _selected(code, selector)
                    for code, selector in (
                        (cell.row, query.rows),
                        (cell.column, query.columns),
                        (cell.sheet, query.sheets),
                    )
                ):
                    points.append(
                        DataPoint(
                            table=table.code,
                            row=cell.row,
                            column=cell.column,
                            sheet=cell.sheet,
                            keys=dict(keys),
                            value=values.get(cell.datapoint),
                            ref=(table.code, cell.datapoint, keys),
                        )
                    )
        return points

    def table_reported(self, table: str) -> bool | None:
        folded = table.casefold()
        return any(
            code.casefold() == folded and reported
            for code, reported in self.report.filing_indicators.items()
        ) or any(
            item.code.casefold() == folded and item.code in self.rows
            for item in self.template.tables
        )

    def parameter(self, name: str) -> Value:
        if name.casefold() == "refperiod":
            return self.report.reference_date
        if name.casefold() == "reportinglevel" and self.report.entity_id:
            return self.report.entity_id.rsplit(".", 1)[-1].casefold()
        return None

    def open_keys(self, table: str) -> tuple[str, ...]:
        found = self.template.table(table)
        return tuple(key.code for key in found.open_keys) if found else ()


def _key(key: OpenKey, text: str) -> Value:
    if key.items:
        return Item.parse(text)
    if key.data_type == "i":
        return Number(Decimal(text))
    if key.data_type == "d":
        return date.fromisoformat(text)
    return text


def _selected(code: str | None, selector: Any) -> bool:
    if selector is None or selector.wildcard:
        return True
    if code in (None, "*"):
        return False
    return axis_matches(code, selector)
