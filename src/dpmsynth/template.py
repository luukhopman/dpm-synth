"""Module templates: the tables, cells and rules a synthetic report must satisfy.

A template is a JSON document in the ``dpm-synth-template/1`` format, so any
DPM source can produce one. The format is specified at
https://luukhopman.github.io/dpm-synth/reference/template-format/; in short:

.. code-block:: json

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
text. ``items`` lists the allowed item qnames of enumerated cells and keys.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

TEMPLATE_FORMAT = "dpm-synth-template/1"
"""The ``format`` value of the templates this version reads."""

# Table codes name the package's CSV files, as dpm-xbrl writes them.
_TABLE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_RESERVED_TABLES = {"parameters", "filingindicators"}
_RESERVED_COLUMNS = {"datapoint", "factvalue"}
_MAX_DECIMALS = 20


class TemplateError(ValueError):
    """Raised when a template cannot be read or is not a valid template.

    The message names the offending field by its path in the document, such
    as ``tables[2].cells[0].datapoint``.

    Examples:
        >>> load_template({"format": "dpm-synth-template/1", "module": "M"})
        Traceback (most recent call last):
        ...
        dpmsynth.template.TemplateError: release: required
    """


@dataclass(frozen=True, slots=True)
class OpenKey:
    """An open-axis key column of a table.

    Attributes:
        code: The key's property code, as rules name it, such as ``qEBB``.
        column: The column of the key in the table's CSV file.
        items: Allowed item qnames for an enumerated key; ``None`` for a
            typed key, which gets generated identifiers.
    """

    code: str
    column: str
    items: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TemplateCell:
    """One reportable cell and the datapoint that carries its value.

    Attributes:
        id: An identifier of the cell, unique within the template.
        datapoint: The datapoint code written in the ``datapoint`` column.
        data_type: The DPM data type code, such as ``m`` or ``e``; ``None``
            or an unknown code is text.
        row: The row code, such as ``0010``; ``None`` for a table without
            rows, ``*`` for every row of an open table.
        column: The column code.
        sheet: The sheet code, ``*`` for every sheet, or ``None``.
        items: Allowed item qnames of an enumerated cell.
    """

    id: str
    datapoint: str
    data_type: str | None
    row: str | None = None
    column: str | None = None
    sheet: str | None = None
    items: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TemplateTable:
    """A table, its filing indicator, open keys and cells.

    Attributes:
        code: The table code, such as ``C_07.00.a``; it names the CSV file.
        filing_indicator: The filing indicator the table is reported under.
        cells: The reportable cells.
        open_keys: The open-axis key columns; empty for a closed table.
    """

    code: str
    filing_indicator: str
    cells: tuple[TemplateCell, ...]
    open_keys: tuple[OpenKey, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateRule:
    """A validation rule with its precondition.

    Attributes:
        code: The rule code, such as ``v0001_m``.
        expression: The DPM-XL expression.
        precondition: An optional DPM-XL precondition, such as
            ``{v_C_01.00}``.
        source: Who defined the rule, such as ``eba``.
    """

    code: str
    expression: str
    precondition: str | None = None
    source: str = "eba"


@dataclass(frozen=True, slots=True)
class ModuleTemplate:
    """Everything needed to generate one module's report.

    Build one with [`load_template`][dpmsynth.load_template].

    Attributes:
        release: The DPM release, such as ``4.3``.
        module: The module code, such as ``COREP_OF``.
        entry_point: The module's entry point, written to ``report.json``.
        tables: The module's tables.
        rules: The rules the report should satisfy.
        reference_date: The report's reference date; 2026-12-31 when
            ``None``.
        decimals: Reporting decimals by data type code; ``m`` 0, ``p`` 4,
            ``i`` 0 and ``r`` 2 unless given.
    """

    release: str
    module: str
    entry_point: str | None
    tables: tuple[TemplateTable, ...]
    rules: tuple[TemplateRule, ...]
    reference_date: date | None = None
    decimals: Mapping[str, int] = field(default_factory=dict)

    def table(self, code: str) -> TemplateTable | None:
        """Return a table by code, ignoring case.

        Returns:
            TemplateTable | None: The table, or ``None``.

        Examples:
            >>> template = load_template("minimal.json")
            >>> template.table("t_01.00").code
            'T_01.00'
        """
        folded = code.casefold()
        return next(
            (table for table in self.tables if table.code.casefold() == folded), None
        )


def load_template(
    source: str | os.PathLike[str] | Mapping[str, Any],
) -> ModuleTemplate:
    """Load and validate a template from a JSON file or a parsed document.

    Fields this version does not know are ignored, so newer exports still
    load.

    Args:
        source: A path to a JSON file, or the document as a mapping.

    Returns:
        ModuleTemplate: The validated template.

    Raises:
        TemplateError: If the file cannot be read, is not JSON, or the
            document is not a valid ``dpm-synth-template/1`` template.

    Examples:
        >>> template = load_template("minimal.json")
        >>> template.module, len(template.tables), len(template.rules)
        ('DEMO', 1, 2)
    """
    if isinstance(source, Mapping):
        document: object = source
    else:
        path = Path(source)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise TemplateError(f"{path}: cannot read: {_reason(error)}") from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise TemplateError(f"{path}: not JSON: {error}") from error
        except RecursionError as error:
            raise TemplateError(f"{path}: JSON nested too deeply") from error
    return _Loader().template(document)


def _reason(error: Exception) -> str:
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)


class _Loader:
    """Validates a parsed document field by field."""

    def template(self, document: object) -> ModuleTemplate:
        root = self.mapping(document, "template")
        found = root.get("format")
        if found != TEMPLATE_FORMAT:
            raise TemplateError(
                f"format: expected {TEMPLATE_FORMAT!r}, got {found!r}"
                if found is not None
                else f"format: required, {TEMPLATE_FORMAT!r}"
            )
        release = self.text(root, "release", "")
        module = self.text(root, "module", "")
        entry_point = self.optional_text(root, "entry_point", "")
        reference_date = self.date_value(root, "reference_date")
        decimals = self.decimals(root)
        tables = tuple(
            self.table(item, f"tables[{index}]")
            for index, item in enumerate(self.array(root, "tables", "", required=True))
        )
        if not tables:
            raise TemplateError("tables: at least one table is required")
        seen: dict[str, int] = {}
        for index, table in enumerate(tables):
            folded = table.code.casefold()
            if folded in seen:
                raise TemplateError(
                    f"tables[{index}].code: {table.code!r} repeats "
                    f"tables[{seen[folded]}].code"
                )
            seen[folded] = index
        cell_ids: dict[str, str] = {}
        for index, table in enumerate(tables):
            for number, cell in enumerate(table.cells):
                where = f"tables[{index}].cells[{number}].id"
                if cell.id in cell_ids:
                    raise TemplateError(
                        f"{where}: {cell.id!r} repeats {cell_ids[cell.id]}"
                    )
                cell_ids[cell.id] = where
        rules = tuple(
            self.rule(item, f"rules[{index}]")
            for index, item in enumerate(self.array(root, "rules", ""))
        )
        return ModuleTemplate(
            release=release,
            module=module,
            entry_point=entry_point,
            tables=tables,
            rules=rules,
            reference_date=reference_date,
            decimals=decimals,
        )

    def table(self, value: object, path: str) -> TemplateTable:
        table = self.mapping(value, path)
        code = self.text(table, "code", path)
        if not _TABLE_CODE.fullmatch(code) or code.casefold() in _RESERVED_TABLES:
            raise TemplateError(
                f"{path}.code: {code!r} cannot name a table file; use letters, "
                "digits, '_', '.' and '-'"
            )
        keys = tuple(
            self.open_key(item, f"{path}.open_keys[{index}]")
            for index, item in enumerate(self.array(table, "open_keys", path))
        )
        columns: set[str] = set()
        for index, key in enumerate(keys):
            where = f"{path}.open_keys[{index}]"
            if key.column.casefold() in _RESERVED_COLUMNS:
                raise TemplateError(
                    f"{where}.column: {key.column!r} is a fact column of the table"
                )
            if key.column in columns:
                raise TemplateError(f"{where}.column: {key.column!r} repeats")
            columns.add(key.column)
        cells = tuple(
            self.cell(item, f"{path}.cells[{index}]")
            for index, item in enumerate(
                self.array(table, "cells", path, required=True)
            )
        )
        if not cells:
            raise TemplateError(f"{path}.cells: at least one cell is required")
        return TemplateTable(
            code=code,
            filing_indicator=self.optional_text(table, "filing_indicator", path)
            or code,
            cells=cells,
            open_keys=keys,
        )

    def open_key(self, value: object, path: str) -> OpenKey:
        key = self.mapping(value, path)
        code = self.text(key, "code", path)
        return OpenKey(
            code=code,
            column=self.optional_text(key, "column", path) or code,
            items=self.items(key, path),
        )

    def cell(self, value: object, path: str) -> TemplateCell:
        cell = self.mapping(value, path)
        return TemplateCell(
            id=self.text(cell, "id", path),
            datapoint=self.text(cell, "datapoint", path),
            data_type=self.optional_text(cell, "data_type", path),
            row=self.optional_text(cell, "row", path),
            column=self.optional_text(cell, "column", path),
            sheet=self.optional_text(cell, "sheet", path),
            items=self.items(cell, path),
        )

    def rule(self, value: object, path: str) -> TemplateRule:
        rule = self.mapping(value, path)
        return TemplateRule(
            code=self.text(rule, "code", path),
            expression=self.text(rule, "expression", path),
            precondition=self.optional_text(rule, "precondition", path),
            source=self.optional_text(rule, "source", path) or "eba",
        )

    # Fields ------------------------------------------------------------------

    @staticmethod
    def mapping(value: object, path: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise TemplateError(f"{path}: expected an object, got {_kind(value)}")
        return value

    @staticmethod
    def array(
        parent: Mapping[str, Any], name: str, path: str, *, required: bool = False
    ) -> list[Any]:
        where = f"{path}.{name}" if path else name
        value = parent.get(name)
        if value is None:
            if required:
                raise TemplateError(f"{where}: required")
            return []
        if not isinstance(value, list):
            raise TemplateError(f"{where}: expected an array, got {_kind(value)}")
        return value

    @staticmethod
    def text(parent: Mapping[str, Any], name: str, path: str) -> str:
        where = f"{path}.{name}" if path else name
        value = parent.get(name)
        if value is None:
            raise TemplateError(f"{where}: required")
        if not isinstance(value, str) or not value.strip():
            raise TemplateError(
                f"{where}: expected a non-empty string, got {_kind(value)}"
            )
        return value

    @staticmethod
    def optional_text(parent: Mapping[str, Any], name: str, path: str) -> str | None:
        where = f"{path}.{name}" if path else name
        value = parent.get(name)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise TemplateError(
                f"{where}: expected a string or null, got {_kind(value)}"
            )
        return value

    @staticmethod
    def items(parent: Mapping[str, Any], path: str) -> tuple[str, ...] | None:
        value = parent.get("items")
        if value is None:
            return None
        if not isinstance(value, list):
            raise TemplateError(
                f"{path}.items: expected an array of item qnames or null, "
                f"got {_kind(value)}"
            )
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise TemplateError(
                    f"{path}.items[{index}]: expected an item qname such as "
                    f"'eba_AS:x1', got {_kind(item)}"
                )
        return tuple(value) or None

    @staticmethod
    def date_value(parent: Mapping[str, Any], name: str) -> date | None:
        value = parent.get(name)
        if value is None:
            return None
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise TemplateError(f"{name}: expected a date as YYYY-MM-DD, got {value!r}")

    @staticmethod
    def decimals(parent: Mapping[str, Any]) -> dict[str, int]:
        value = parent.get("decimals")
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TemplateError(f"decimals: expected an object, got {_kind(value)}")
        result = {}
        for kind, number in value.items():
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or abs(number) > _MAX_DECIMALS
            ):
                raise TemplateError(
                    f"decimals.{kind}: expected a whole number from "
                    f"-{_MAX_DECIMALS} to {_MAX_DECIMALS}, got {number!r}"
                )
            result[kind] = number
        return result


def _kind(value: object) -> str:
    match value:
        case None:
            return "null"
        case bool():
            return "a boolean"
        case int() | float():
            return f"the number {value!r}"
        case str():
            return f"the string {value!r}" if value.strip() else "an empty string"
        case list():
            return "an array"
        case Mapping():
            return "an object"
    return type(value).__name__


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
