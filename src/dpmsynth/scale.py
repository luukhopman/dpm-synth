"""Scale a generated report's open tables to very large row counts.

Solving rules over millions of open-table rows is unnecessary for load
testing: rules over open tables are mostly row-wise, so copying solved key
rows under fresh keys keeps them satisfied. :func:`write_scaled_package`
streams such a report straight into an xBRL-CSV package without building a
fact object per row.

Rules that aggregate open tables into closed totals (``sum`` over all
counterparties equals a total cell) are not re-solved and will typically
fail on a scaled report; the ``generate`` result for the base report shows
which rules hold before scaling.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import IO, Any

from dpmxbrl import write_xbrl_csv

from .generator import (
    LEI_PREFIX,
    SyntheticData,
    _key_dates,
    _typed_key,
    _unit,
    _with_check_digits,
    build_report,
)
from .template import OpenKey, TemplateTable

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_PREFIX = re.compile(r"[^A-Z0-9]")
# Typed keys number their rows with ten digits.
_MAX_ROWS = 10**10 - 1


def _scaled_rows(
    table: TemplateTable, count: int, data: SyntheticData
) -> Iterator[tuple[tuple[tuple[str, Any], ...], list[str]]]:
    """Yield up to ``count`` scaled rows: the solved row each repeats, and keys.

    Row ``i`` repeats solved row ``i`` modulo the solved rows, with that
    row's enumerated key values, so a rule that filters on an enumerated key
    sees the values solved for it. Typed keys (no item list) get unique
    values: integer keys count from 1, date keys count back from the
    reference date, and other keys get checksum-valid, visibly fictional
    LEI-shaped identifiers (``SYNTH``, three characters of the key code, a
    row number and check digits). A table whose keys are all enumerated has
    only its solved rows, and one whose typed keys are all dates has at most
    one row per date.

    Yields:
        tuple: The solved row's keys, and the key values to write in column
        order.
    """
    solved = data.key_rows[table.code]
    typed = [key for key in table.open_keys if not key.items]
    reference = data._reference()
    if not typed:
        count = min(count, len(solved))
    elif all(key.data_type == "d" for key in typed):
        count = min(count, _key_dates(reference))
    prefixes = {
        key.code: LEI_PREFIX + (_PREFIX.sub("", key.code.upper()) + "XXX")[:3]
        for key in typed
    }
    for number in range(count):
        source = solved[number % len(solved)]
        values = dict(source)
        yield (
            source,
            [
                data._text(values[key.code])
                if key.items
                else _typed_text(key, number, reference, prefixes, data)
                for key in table.open_keys
            ],
        )


def _typed_text(
    key: OpenKey,
    number: int,
    reference: date,
    prefixes: Mapping[str, str],
    data: SyntheticData,
) -> str:
    value = _typed_key(key, number, reference)
    if value is not None:
        return data._text(value)
    return _with_check_digits(f"{prefixes[key.code]}{number:010d}")


def write_scaled_package(
    data: SyntheticData,
    target: str | os.PathLike[str],
    *,
    rows: int | Mapping[str, int],
) -> dict[str, int]:
    """Write an xBRL-CSV package with every open table scaled to ``rows`` key rows.

    Closed tables are written as generated. Each open table gets ``rows``
    key rows, whose values repeat the generated rows in turn. Typed keys get
    new values; enumerated keys keep the values of the generated row
    that is repeated, so rules that filter on them still hold, and a table
    with only enumerated keys keeps its generated rows. The package is laid
    out, named and described exactly as ``dpmxbrl.write_xbrl_csv`` writes the
    unscaled report, but tables are streamed to the ZIP file, so memory
    stays flat.

    Args:
        data: Generated values, ``GenerationResult.data``.
        target: ZIP file to write; its name without ``.zip`` names the
            package's root folder.
        rows: Key rows per open table, or a mapping of table code to rows;
            tables missing from the mapping keep their generated rows.

    Returns:
        dict[str, int]: Fact rows written per table code.

    Raises:
        ValueError: If a row count is not a whole number of 1 or more.
        dpmxbrl.ReportError: If dpm-xbrl cannot write the package header.
        OSError: If the file cannot be written.

    Examples:
        >>> from dpmsynth import generate, load_template
        >>> result = generate(load_template("sample.json"), seed=7)
        >>> written = write_scaled_package(result.data, "big.zip", rows=1000)
        >>> written["S_03.00"], written["S_02.00.a"]
        (1000, 4)
    """
    counts = {
        table.code: _rows(table.code, rows, data) for table in data.template.tables
    }
    # The header files are dpm-xbrl's own: a report without facts gives the
    # report package, report.json, parameters and filing indicators.
    report = build_report(data)
    write_xbrl_csv(replace(report, facts=()), Path(target))
    written: dict[str, int] = {}
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        root = archive.namelist()[0].split("/", 1)[0]
        for table in sorted(data.template.tables, key=lambda item: item.code.lower()):
            info = zipfile.ZipInfo(
                f"{root}/reports/{table.code.lower()}.csv", _ZIP_TIMESTAMP
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with archive.open(info, "w", force_zip64=True) as raw:
                written[table.code] = _write_table(raw, table, data, counts[table.code])
    return written


def _rows(code: str, rows: int | Mapping[str, int], data: SyntheticData) -> int:
    count = (
        rows
        if not isinstance(rows, Mapping)
        else rows.get(code, len(data.key_rows[code]))
    )
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= _MAX_ROWS
    ):
        raise ValueError(
            f"rows for {code} must be a whole number from 1 to {_MAX_ROWS:_}: {count!r}"
        )
    return count


def _write_table(
    raw: IO[bytes], table: TemplateTable, data: SyntheticData, count: int
) -> int:
    stream = io.TextIOWrapper(raw, encoding="utf-8", newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    units = any(cell.unit for cell in table.cells)
    writer.writerow(
        [
            "datapoint",
            "factValue",
            *(key.column for key in table.open_keys),
            *(["unit"] if units else []),
        ]
    )
    written = 0
    closed: list[tuple[tuple[tuple[str, Any], ...], list[str]]] = [((), [])]
    rows = _scaled_rows(table, count, data) if table.open_keys else closed
    for source, key_text in rows:
        unit = [_unit(data, source)] if units else []
        for cell in table.cells:
            value = data.values.get((cell.datapoint, source))
            if value is not None:
                writer.writerow(
                    [
                        cell.datapoint,
                        data._text(value),
                        *key_text,
                        *(unit if cell.unit else [""] * len(unit)),
                    ]
                )
                written += 1
    stream.flush()
    stream.detach()
    return written


__all__ = ["write_scaled_package"]
