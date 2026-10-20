"""Module templates: the tables, cells and rules a synthetic report must satisfy.

A template is plain JSON so that any DPM source can produce one; a DPM tool
writes it with ``dpm-export``. Shape::

    {
      "format": "dpm-synth-template/1",
      "release": "4.3",
      "module": "COREP_OF",
      "entry_point": "http://…/corep/4.3/mod/corep_of.json",
      "reference_date": "2026-12-31",
      "decimals": {"m": 0, "p": 4, "i": 0, "r": 2},
      "tables": [
        {
          "code": "C_07.00.a",
          "filing_indicator": "C_07.00",
          "open_keys": [{"code": "qEBB", "column": "qEBB",
                         "items": ["eba_qEC:qx16", "eba_qEC:qx23"]}],
          "cells": [{"id": "table-cell:5", "row": "0010", "column": "0010",
                     "sheet": "*", "datapoint": "dp12345", "data_type": "m",
                     "items": null}]
        }
      ],
      "rules": [{"source": "eba", "code": "v0001_m",
                 "expression": "…", "precondition": "{v_C_07.00}"}]
    }

Data types follow DPM codes: ``m`` monetary, ``p`` percentage, ``i`` integer,
``r`` decimal, ``e`` enumerated item, ``b`` boolean, ``d`` date, anything else
text. ``items`` lists allowed item qnames for enumerated cells and keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

TEMPLATE_FORMAT = "dpm-synth-template/1"


class TemplateError(ValueError):
    """Raised when a template document is malformed."""


@dataclass(frozen=True, slots=True)
class OpenKey:
    """An open-axis key column of a table."""

    code: str
    column: str
    items: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TemplateCell:
    """One reportable cell and the datapoint that carries its value."""

    id: str
    datapoint: str
    data_type: str | None
    row: str | None = None
    column: str | None = None
    sheet: str | None = None
    items: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TemplateTable:
    """A table, its filing indicator, open keys and cells."""

    code: str
    filing_indicator: str
    cells: tuple[TemplateCell, ...]
    open_keys: tuple[OpenKey, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateRule:
    """A validation rule or check expression with its precondition."""

    code: str
    expression: str
    precondition: str | None = None
    source: str = "eba"


@dataclass(frozen=True, slots=True)
class ModuleTemplate:
    """Everything needed to generate one module's report."""

    release: str
    module: str
    entry_point: str | None
    tables: tuple[TemplateTable, ...]
    rules: tuple[TemplateRule, ...]
    reference_date: date | None = None
    decimals: dict[str, int] = field(default_factory=dict)

    def table(self, code: str) -> TemplateTable | None:
        """Return a table by code, ignoring case.

        Returns:
            TemplateTable | None: The table, or ``None``.
        """
        folded = code.casefold()
        return next(
            (table for table in self.tables if table.code.casefold() == folded), None
        )


def load_template(source: str | Path | dict[str, Any]) -> ModuleTemplate:
    """Load a template from a JSON file or an already parsed document.

    Returns:
        ModuleTemplate: The validated template.

    Raises:
        TemplateError: If required fields are missing or malformed.
    """
    document = (
        source
        if isinstance(source, dict)
        else json.loads(Path(source).read_text(encoding="utf-8"))
    )
    if document.get("format") != TEMPLATE_FORMAT:
        raise TemplateError(f"expected format {TEMPLATE_FORMAT!r}")
    try:
        tables = tuple(
            TemplateTable(
                code=table["code"],
                filing_indicator=table.get("filing_indicator") or table["code"],
                open_keys=tuple(
                    OpenKey(
                        code=key["code"],
                        column=key.get("column") or key["code"],
                        items=tuple(key["items"]) if key.get("items") else None,
                    )
                    for key in table.get("open_keys", ())
                ),
                cells=tuple(
                    TemplateCell(
                        id=cell["id"],
                        datapoint=cell["datapoint"],
                        data_type=cell.get("data_type"),
                        row=cell.get("row"),
                        column=cell.get("column"),
                        sheet=cell.get("sheet"),
                        items=tuple(cell["items"]) if cell.get("items") else None,
                    )
                    for cell in table["cells"]
                ),
            )
            for table in document["tables"]
        )
        rules = tuple(
            TemplateRule(
                code=rule["code"],
                expression=rule["expression"],
                precondition=rule.get("precondition") or None,
                source=rule.get("source", "eba"),
            )
            for rule in document.get("rules", ())
        )
        reference = document.get("reference_date")
        return ModuleTemplate(
            release=document["release"],
            module=document["module"],
            entry_point=document.get("entry_point"),
            tables=tables,
            rules=rules,
            reference_date=date.fromisoformat(reference) if reference else None,
            decimals={
                key: int(value) for key, value in document.get("decimals", {}).items()
            },
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TemplateError(f"invalid template: {error}") from error


__all__ = [
    "TEMPLATE_FORMAT",
    "ModuleTemplate",
    "OpenKey",
    "TemplateCell",
    "TemplateError",
    "TemplateRule",
    "TemplateTable",
    "load_template",
]
