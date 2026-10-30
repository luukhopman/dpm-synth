---
description: The template file format (dpm-module/1 and dpm-synth-template/1), field by field - the module, tables, open keys, cells, data types, items, rules and decimals - and how it is validated.
---

# Template format

A template file describes one module of a DPM release: its tables, the
cells of each table, and the rules a report must satisfy. It is a JSON
document (UTF-8), read by [`load_template`][dpmsynth.load_template]: the
[module file](https://luukhopman.github.io/dpm-xl/reference/module-file/)
(`dpm-module/1`) that `dpm-xl export-module` writes, or the same fields in
the `dpm-synth-template/1` format. See
[get a template from a DPM release](../guides/from-a-dpm-release.md) and
[write a template by hand](../guides/write-a-template.md).

## Example

```json
{
  "format": "dpm-module/1",
  "release": "4.3",
  "module": "COREP_OF",
  "entry_point": "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.2/mod/corep_of.json",
  "reference_date": "2026-12-31",
  "decimals": {"m": 0, "p": 4, "i": 0, "r": 2},
  "tables": [
    {
      "code": "C_07.00.a",
      "filing_indicator": "C_07.00",
      "open_keys": [
        {"code": "qEBB", "column": "qEBB", "items": ["eba_qEC:qx16", "eba_qEC:qx23"]}
      ],
      "cells": [
        {"id": "C_07.00.a/dp12345", "row": "0010", "column": "0010", "sheet": "*",
         "datapoint": "dp12345", "data_type": "m"}
      ]
    }
  ],
  "rules": [
    {"source": "eba", "code": "v0001_m", "expression": "…", "precondition": "{v_C_07.00}"}
  ]
}
```

## The module

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `format` | string | yes | `"dpm-module/1"` for a [dpm-xl module file](https://luukhopman.github.io/dpm-xl/reference/module-file/), or `"dpm-synth-template/1"`; both have the fields on this page. |
| `release` | string | yes | The DPM release, such as `"4.3"`. Informative. |
| `module` | string | yes | The module code, such as `"COREP_OF"`. Named in error messages and the JSON output. |
| `entry_point` | string or null | no | The module's xBRL-CSV entry point, written to `reports/report.json` as `extends`. |
| `reference_date` | string or null | no | The reference date, `YYYY-MM-DD`; it is the `refPeriod` parameter and the rules' `{refPeriod}`, and `d` cells start in the ten years up to it. Before 2022-12-31 the entity is identified by its bare LEI (EBA filing rule 3.6). Default `2026-12-31`; the `--reference-date` option overrides it. |
| `currency` | string or null | no | The reporting currency, an ISO 4217 code such as `"SEK"`; the report's `baseCurrency`, written only when a monetary fact is reported. Default `"EUR"`; the `--currency` option overrides it. |
| `decimals` | object | no | Reporting decimals by data type code, such as `{"m": -3}`; whole numbers from -20 to 20. Unlisted types keep the defaults `m` 0, `p` 4, `i` 0, `r` 2. EBA filing rule 2.18 sets the least accuracy: `p` 4 or more, `i` exactly 0, and `m` -4 or more, or -6 for the FP, ESG, Pillar 3 and REM_DBM modules; `m` below -6 is rejected. |
| `filing_indicators` | array of strings | no | The filing indicators of every reporting template of the module, such as `["C_07.00", "C_08.01"]`, which EBA filing rule 1.6 asks a report to declare. Those that a table of the file uses are reported as `true`, the others as `false`. Unique, and must include every table's `filing_indicator`. |
| `tables` | array | yes | At least one [table](#tables). |
| `rules` | array | no | The [rules](#rules); none means every value is simply generated. |

## Tables

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `code` | string | yes | The table code, such as `"C_07.00.a"`, as rules name it. Lower-cased, it names the table's file, `reports/c_07.00.a.csv`, so it is letters, digits, `_`, `.` and `-`, starting with a letter or digit, and not `parameters` or `FilingIndicators`. Unique within the file, ignoring case. |
| `filing_indicator` | string or null | no | The filing indicator the table is reported under, such as `"C_07.00"`. Default: the code. It is reported as `true`. |
| `open_keys` | array | no | The table's [open keys](#open-keys); none for a closed table. |
| `cells` | array | yes | At least one [cell](#cells). |

## Open keys

An open table has one row per combination of key values, such as one row per
counterparty. Each key becomes a column of the table's file.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `code` | string | yes | The key's property code, as rules name it, such as `"qEBB"` in `[where qEBB = …]`. |
| `column` | string or null | no | The key's column in the table's file. Default: the code. Unique within the table, and not `datapoint` or `factValue`. |
| `items` | array of strings or null | no | The allowed item qnames of an enumerated key, such as `"eba_qEC:qx16"`. Null or empty for a typed key, whose values are generated. |
| `data_type` | string or null | no | The data type of a typed key: `i` or `o` gives integers 1, 2, 3 and so on; `d` or `dt` gives dates counting back from the reference date; any other code, or null, gives LEI-shaped identifiers starting with `SYNTH`. |

The generator gives every open table `open_rows` key rows (default 2).
Enumerated keys take their items in order, row by row, so an enumerated key
with fewer items than rows gives fewer distinct rows.

## Open tables

In an open table, the reporter adds one row of the table's file per key
value. In the table's layout, the axis that repeats per key value is the
*open axis*, and its code is written `*`:

- In most open tables the rows repeat: the cells have `"row": "*"` and
  their own columns, as `S_03.00` in [`sample.json`](../samples/sample.json):
  `{"row": "*", "column": "0020", ...}`.
- In some, the sheets repeat, such as one sheet per counterparty group,
  and the rows stay fixed: the cells have their rows and `"sheet": "*"`, as
  `S_02.00.a`: `{"row": "0010", "column": "0010", "sheet": "*", ...}`.

Copy what `dpm-xl export-module` writes. A rule selects the `*` cells only
when it names no code on that axis, or `*`: `{tS_03.00, c0020}` and
`{tS_02.00.a, r0010, c0010}` select them; `{tS_03.00, r0010, c0020}` does
not.

## Cells

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | An identifier of the cell, unique within the file, in any form, such as `C_07.00.a/dp12345`. Only used in error messages. |
| `datapoint` | string | yes | The datapoint code written in the table's `datapoint` column, such as `"dp12345"`. Two tables may share a datapoint; they then share its value. |
| `data_type` | string or null | no | The [data type](#data-types). |
| `row` | string or null | no | The row code, such as `"0010"`, without the `r`. Null for a table without rows; `"*"` when the rows are the [open axis](#open-tables). |
| `column` | string or null | no | The column code, such as `"0010"`. |
| `sheet` | string or null | no | The sheet code, without the `s`; `"*"` when the sheets are the [open axis](#open-tables). |
| `items` | array of strings or null | no | The allowed item qnames of an enumerated (`e`) cell; required for those. The first is its starting value. Ignored for other data types. |
| `unit` | boolean or null | no | `true` for a monetary cell reported in its currency of denomination, whose datapoint has a `unit` in the module's metadata (EBA filing rule 3.1). Its table's file then has a `unit` column: the currency of the row's `CUS` or `CUA` key, such as `iso4217:USD` for `eba_CU:USD`, and otherwise the reporting currency. Default `false`. |

Rules select cells by table, row, column and sheet, as in
`{tC_07.00.a, r0010, c0010}`; the generator answers such a selection with
the file's cells, for every key row of an open table.

## Data types

`data_type` is a DPM data type code. It decides the starting value, which
repairs apply, how the value is rounded and how it is written.

| Code | Type | Starting value | Written as |
| --- | --- | --- | --- |
| `m` | monetary | a multiple of 1,000, spread over three orders of magnitude for the institution size: 100,000 to 100,000,000 by default (`size`, `--size`) | a decimal with `decimals.m` places |
| `p` | percentage | 0.01 to 0.99 | a decimal with `decimals.p` places |
| `i` | integer | 1 to 50 | a decimal with `decimals.i` places |
| `r` | decimal | 1.00 to 9.99 | a decimal with `decimals.r` places |
| `o` | ordinal | 1 to 10 | a whole number |
| `e` | enumerated | the first of `items` | the item qname as the file writes it |
| `b` | boolean | `true` or `false` | `true` or `false` |
| `t` | true | `true`; no repair changes it | `true` |
| `d` | date | a day in the ten years up to the reference date | `YYYY-MM-DD` |
| `dt` | date and time | a day in the ten years up to the reference date | `YYYY-MM-DD`, a valid date and time value |
| `u` | URI | `https://example.com/dpm-synth/` and a number | the URI |
| `s`, `es`, anything else, or null | text | `Synthetic text` and a number; a `match` repair writes an LEI-shaped identifier starting with `SYNTH` where a rule asks for one | the text |

An `es` value may be empty in the DPM, but EBA filing rule 2.19 forbids
reporting the empty string (in xBRL-CSV, `#empty`), so dpm-synth never
writes one.

Starting values depend on the seed only. With `fill` below 1 (`--fill`),
a share of the cells starts empty instead and is left out of the report
unless a rule needs a value. Only numeric cells (`m`, `p`, `i`, `r`) take
part in arithmetic repairs.
Negative decimals round to tens, hundreds or thousands: with `"m": -3` a
monetary value is written as a multiple of 1,000.

## Rules

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `code` | string | yes | The rule code, such as `"v0001_m"`. Unique within the file: results list rules by code. |
| `expression` | string | yes | The DPM-XL expression, as [dpm-xl] parses it. |
| `precondition` | string or null | no | A DPM-XL precondition, such as `"{v_C_07.00}"`; the rule applies only when it holds. |
| `source` | string or null | no | Who defines the rule, such as `"eba"`. Default `"eba"`. Informative: filter the rules before generating if you want only some sources. |
| `severity` | string or null | no | `"error"` for a blocking rule or `"warning"`. Default `"error"`. Both are repaired alike; the severity is shown in the output and decides, with `--fail-on`, the [exit status](exit-statuses.md). |
| `active` | boolean or null | no | `false` for a rule that does not apply, such as one the EBA deactivated: it is neither repaired nor evaluated, and is reported as `skipped`. It is not parsed, so it may select a table the file does not have. Default `true`. |

Every table of the file counts as reported, so a precondition such as
`{v_C_07.00}` holds when the file has a table of reporting template
`C_07.00`, and is false otherwise. `{vReportingLevel}` is `con` or `ind`
and `{refPeriod}` is the reference date.

A rule or precondition that does not parse, or that selects a table the
file does not have, is an error of the template file, with one exception:
a reporting template listed in `filing_indicators` with no tables in the
file is reported as absent, so a rule on it is `not_applicable`.

## Validation

[`load_template`][dpmsynth.load_template] checks every field above and
raises [`TemplateError`][dpmsynth.TemplateError] for the first problem,
naming the field by its path. Text that cannot be written as UTF-8, such as
a lone surrogate escape `\ud800` in the JSON, is rejected too, since the
package is UTF-8:

```python
import json
from pathlib import Path

from dpmsynth import TemplateError, load_template

document = json.loads(Path("minimal.json").read_text(encoding="utf-8"))
document["tables"][0]["cells"][1]["datapoint"] = 1002
try:
    load_template(document)
except TemplateError as error:
    print(error)
```

```text
tables[0].cells[1].datapoint: expected a non-empty string, got the number 1002
```

A file that cannot be read or is not JSON raises `TemplateError` too, and
the command line reports any of them with exit status 3.

## Compatibility

Fields a version does not know are ignored, so a template file with extra
fields loads, and exports may carry more information than dpm-synth uses.
A module file that `dpm-xl export-module` writes loads as it is. A change
that a reader of `dpm-synth-template/1` cannot ignore gets a new format
version, `dpm-synth-template/2`; see
[stability and versioning](../project/stability.md).
