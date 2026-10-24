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
import itertools
import os
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import IO

from dpmxbrl import write_xbrl_csv

from .generator import SyntheticData, _with_check_digits, build_report
from .template import TemplateTable

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_PREFIX = re.compile(r"[^A-Z0-9]")


def _key_values(
    table: TemplateTable, count: int
) -> Iterator[tuple[tuple[str, str], ...]]:
    """Yield up to ``count`` distinct key rows for a table.

    Enumerated keys cycle through their allowed items; typed keys (no item
    list) get unique, checksum-valid LEI-shaped identifiers, so the rows stay
    distinct. A table whose keys are all enumerated yields at most the
    product of its item lists.

    Yields:
        tuple[tuple[str, str], ...]: ``(key code, lexical value)`` pairs.
    """
    typed = [key for key in table.open_keys if not key.items]
    if not typed:
        lists = [list(key.items or ()) for key in table.open_keys]
        for combination in itertools.islice(itertools.product(*lists), count):
            yield tuple(
                (key.code, value.strip())
                for key, value in zip(table.open_keys, combination, strict=True)
            )
        return
    prefixes = {
        key.code: (_PREFIX.sub("", key.code.upper()) + "XXXXXX")[:6] for key in typed
    }
    for number in range(count):
        row = []
        for key in table.open_keys:
            if key.items:
                row.append((key.code, key.items[number % len(key.items)].strip()))
            else:
                identifier = _with_check_digits(f"{prefixes[key.code]}{number:012d}")
                row.append((key.code, identifier))
        yield tuple(row)


def write_scaled_package(
    data: SyntheticData,
    target: str | os.PathLike[str],
    *,
    rows: int | Mapping[str, int],
) -> dict[str, int]:
    """Write an xBRL-CSV package with every open table scaled to ``rows`` key rows.

    Closed tables are written as generated. Each open table gets ``rows``
    fresh key rows, whose values repeat the generated rows in turn. Typed
    keys get new identifiers; enumerated keys cycle through their items, so
    a table with only enumerated keys gets at most as many rows as their
    combinations. The package is laid out, named and described exactly as
    ``dpmxbrl.write_xbrl_csv`` writes the unscaled report, but tables are
    streamed to the ZIP file, so memory stays flat.

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
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(
            f"rows for {code} must be a whole number of 1 or more: {count!r}"
        )
    return count


def _write_table(
    raw: IO[bytes], table: TemplateTable, data: SyntheticData, count: int
) -> int:
    stream = io.TextIOWrapper(raw, encoding="utf-8", newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(
        ["datapoint", "factValue", *(key.column for key in table.open_keys)]
    )
    written = 0
    base_rows = data.key_rows[table.code]
    if not table.open_keys:
        for cell in table.cells:
            value = data.values.get((cell.datapoint, ()))
            if value is not None:
                writer.writerow([cell.datapoint, data._text(value)])
                written += 1
    else:
        for number, keys in enumerate(_key_values(table, count)):
            source = base_rows[number % len(base_rows)] if base_rows else ()
            key_text = [value for _code, value in keys]
            for cell in table.cells:
                value = data.values.get((cell.datapoint, source))
                if value is not None:
                    writer.writerow([cell.datapoint, data._text(value), *key_text])
                    written += 1
    stream.flush()
    stream.detach()
    return written


__all__ = ["write_scaled_package"]
