"""Scale a generated report's open tables to very large row counts.

Solving rules over millions of open-table rows is unnecessary for load
testing: rules over open tables are mostly row-wise, so copying solved key
rows under fresh keys keeps them satisfied. :func:`write_scaled_package`
streams such a report straight into an xBRL-CSV package without building a
fact object per row.

Rules that aggregate open tables into closed totals (``sum`` over all
counterparties equals a total cell) are not re-solved and will typically
fail on a scaled report; :func:`generate` results for the base report show
which rules hold before scaling.
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import zipfile
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path

from .generator import SyntheticData, _lexical
from .template import ModuleTemplate, TemplateTable

_EPOCH = (1980, 1, 1, 0, 0, 0)


def _key_values(
    table: TemplateTable, count: int
) -> Iterator[tuple[tuple[str, str], ...]]:
    """Yield ``count`` distinct key rows for a table.

    Enumerated keys cycle through their allowed items; typed keys (no item
    list) get unique identifiers, so the rows stay distinct. A table whose
    keys are all enumerated yields at most the product of its item lists.

    Yields:
        tuple[tuple[str, str], ...]: ``(key code, lexical value)`` pairs.
    """
    typed = [key for key in table.open_keys if not key.items]
    if not typed:
        lists = [list(key.items or ()) for key in table.open_keys]
        for combination in itertools.islice(itertools.product(*lists), count):
            yield tuple(
                (key.code, value)
                for key, value in zip(table.open_keys, combination, strict=True)
            )
        return
    for number in range(count):
        row = []
        for key in table.open_keys:
            if key.items:
                row.append((key.code, key.items[number % len(key.items)]))
            else:
                prefix = (key.code.upper() + "000000")[:6]
                row.append((key.code, f"{prefix}{number:012d}{number % 97:02d}"))
        yield tuple(row)


def write_scaled_package(
    template: ModuleTemplate,
    data: SyntheticData,
    target: str | Path,
    *,
    rows: int | Mapping[str, int],
    entity: str = "SYNTHETICDPMXL000002",
    reporting_level: str = "CON",
    reference_date: date | None = None,
) -> dict[str, int]:
    """Write an xBRL-CSV package with open tables scaled to ``rows`` key rows.

    Args:
        template: Module template.
        data: Values from :func:`dpmsynth.generate` (``GenerationResult.data``).
        target: ZIP file to write.
        rows: Key rows per open table, or a mapping of table code to rows.
        entity: LEI of the reporting entity.
        reporting_level: ``CON`` or ``IND``.
        reference_date: Report reference date; defaults to the template's.

    Returns:
        dict[str, int]: Fact rows written per table.
    """
    reference = reference_date or template.reference_date or date(2026, 12, 31)
    root = f"{entity}.{reporting_level}_{reference.isoformat()}"
    written: dict[str, int] = {}
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
    ) as archive:

        def add(name: str, text: str) -> None:
            info = zipfile.ZipInfo(f"{root}/{name}", _EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text)

        add(
            "META-INF/reportPackage.json",
            json.dumps(
                {
                    "documentInfo": {
                        "documentType": "https://xbrl.org/report-package/2023/xbrl-csv"
                    }
                }
            ),
        )
        add(
            "reports/report.json",
            json.dumps(
                {
                    "documentInfo": {
                        "documentType": "https://xbrl.org/2021/xbrl-csv",
                        "extends": [template.entry_point]
                        if template.entry_point
                        else [],
                    }
                },
                indent=2,
            ),
        )
        decimals = {"m": 0, "p": 4, "i": 0, "r": 2, **template.decimals}
        parameters = io.StringIO()
        writer = csv.writer(parameters, lineterminator="\n")
        writer.writerow(["name", "value"])
        writer.writerow(["entityID", f"lei:{entity}.{reporting_level}"])
        writer.writerow(["refPeriod", reference.isoformat()])
        writer.writerow(["baseCurrency", "iso4217:EUR"])
        names = {
            "m": "decimalsMonetary",
            "p": "decimalsPercentage",
            "i": "decimalsInteger",
            "r": "decimalsDecimal",
        }
        for kind, name in names.items():
            writer.writerow([name, decimals[kind]])
        add("reports/parameters.csv", parameters.getvalue())
        indicators = io.StringIO()
        writer = csv.writer(indicators, lineterminator="\n")
        writer.writerow(["templateID", "reported"])
        for code in dict.fromkeys(table.filing_indicator for table in template.tables):
            writer.writerow([code, "true"])
        add("reports/FilingIndicators.csv", indicators.getvalue())

        for table in template.tables:
            name = f"reports/{table.code.lower()}.csv"
            info = zipfile.ZipInfo(f"{root}/{name}", _EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            count = 0
            with archive.open(info, "w", force_zip64=True) as raw:
                stream = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(
                    ["datapoint", "factValue", *[key.column for key in table.open_keys]]
                )
                base_rows = data.key_rows[table.code]
                if not table.open_keys:
                    for cell in table.cells:
                        value = data.values.get((cell.datapoint, ()))
                        if value is not None:
                            writer.writerow([cell.datapoint, _lexical(value)])
                            count += 1
                else:
                    target_rows = (
                        rows
                        if isinstance(rows, int)
                        else rows.get(table.code, len(base_rows))
                    )
                    for number, keys in enumerate(_key_values(table, target_rows)):
                        source = base_rows[number % len(base_rows)] if base_rows else ()
                        key_text = [value for _code, value in keys]
                        for cell in table.cells:
                            value = data.values.get((cell.datapoint, source))
                            if value is not None:
                                writer.writerow(
                                    [cell.datapoint, _lexical(value), *key_text]
                                )
                                count += 1
                stream.flush()
                stream.detach()
            written[table.code] = count
    return written


__all__ = ["write_scaled_package"]
