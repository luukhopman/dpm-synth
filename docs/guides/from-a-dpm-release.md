---
description: Get a dpm-synth template file for a real EBA module - get the DPM database, export the module with dpm-xl export-module, generate a report and check it - and notes for writing an exporter for another DPM source.
icon: lucide/database
---

# Get a template from a DPM release

For a real EBA module, the template file is the
[module file](https://luukhopman.github.io/dpm-xl/reference/module-file/)
that `dpm-xl export-module` writes from the EBA's DPM database: one JSON
file with the module's tables, cells and rules for one release. dpm-synth
reads it as it is.

## 1. Get the database

You need the EBA's DPM 2.0 database as a SQLite file, about 350 MB. The
EBA publishes each release as a Microsoft Access file; dpm-xl's guide
shows how to
[convert it, or download one already converted](https://luukhopman.github.io/dpm-xl/guides/from-a-dpm-release/#2-get-the-database-as-sqlite).
One database holds every release up to its own, so the 4.4 database,
`dpm-4.4.sqlite` below, also exports release 4.3.

## 2. Export the module

```bash
pip install dpm-xl
dpm-xl export-module dpm-4.4.sqlite COREP_OF --release 4.3 -o corep_of.json
```

```text
note: COREP_OF: left out 32 rules whose scope spans several modules: v0655_m, v0656_m, …, v6259_m
note: COREP_OF: rule v7551_m: corrected 'trueendif' to 'true endif' (no space before endif)
wrote corep_of.json: module COREP_OF, release 4.3: 81 tables, 21339 cells, 1418 rules
```

The notes say what the export corrected or left out of the EBA's data.
`dpm-xl list-modules dpm-4.4.sqlite --release 4.3` lists the module codes
of a release.

## 3. Generate a report

```bash
dpm-synth generate corep_of.json -o report.zip --seed 7
```

```text
rules: 1418, passed: 1150, failed: 1, not applicable: 54, skipped: 213
rounds: 14 (failing rules per round: 69, 33, 22, 11, 11, 11, 11, 11, 11, 11, 1, 2, 2, 2)
still failing: v4810_m (warning)
wrote report.zip (25483 facts)
```

The 213 skipped rules are those the EBA deactivated. Expect a few rules to
stay failing on a real module: [limits of the loop](../concepts/limits.md)
explains why. Here `v4810_m` is a warning, so the exit status is 0; a
failing `error` rule makes it 1, and the package is written either way.
Another seed can leave other rules failing.

## 4. Check the report

```bash
pip install "dpm-xl[xbrl]"
dpm-xl check-report corep_of.json report.zip
```

`dpm-xl check-report` reads the package with dpm-xbrl and evaluates the
module's rules on what it read. It gives the same statuses as step 3 and
explains each failing rule; see
[validate the output](validate-output.md).

## Notes for exporter authors

Only for a DPM source that `dpm-xl export-module` does not read: write the
fields of the [template format](../reference/template-format.md) yourself.
dpm-xl's [module file](https://luukhopman.github.io/dpm-xl/reference/module-file/)
reference says where each field comes from in the DPM. Write the module's
`entry_point`, without which the package names no taxonomy. Leave out abstract
tables, cells without a variable and rules of other modules, and write
item qnames as they appear in a report, such as `eba_qEC:qx16`; dpm-synth
writes them back unchanged.

### A small exporter

An exporter is a query per field. Here the
release's rows are plain Python lists, standing in for the query results of
your DPM database:

```python
import json
import re
from pathlib import Path

# Query results of a release, one tuple per row.
tables = [("X_01.00", False), ("X_02.00.a", False), ("X_99.00", True)]  # code, abstract
cells = [  # table, row, column, sheet, variable, data type
    ("X_01.00", "0010", "0010", None, "500", "m"),
    ("X_01.00", "0020", "0010", None, "501", "m"),
    ("X_01.00", "0030", "0010", None, "502", "e"),
    ("X_02.00.a", "*", "0010", None, "510", "m"),
]
open_axes = [("X_02.00.a", "qCP", None)]  # table, property, domain (None: typed)
domains = {"CT": ["x1", "x2"]}  # domain code -> item codes
enumerated = {"502": "CT"}  # variable -> domain of an enumerated variable
rules = [  # code, expression, precondition
    ("v1", "with {tX_01.00, c0010, default: 0}: {r0010} >= {r0020}", "{v_X_01.00}"),
    (
        "v2",
        "with {default: 0}: sum({tX_02.00.a, c0010}) = {tX_01.00, r0020, c0010}",
        None,
    ),
    ("v3", "{tX_01.00, r0030, c0010} in {[eba_CT:x2]}", None),
]


def items(domain):
    return [f"eba_{domain}:{code}" for code in domains[domain]] if domain else None


def filing_indicator(code):
    # Drop single-letter parts: C_08.05.1.a -> C_08.05.1.
    return re.sub(r"\.[A-Za-z](?=\.|$)", "", code)


template = {
    "format": "dpm-synth-template/1",
    "release": "1.0",
    "module": "X",
    "entry_point": "https://example.com/taxonomy/x/1.0/mod/x.json",
    "reference_date": "2026-12-31",
    "tables": [
        {
            "code": code,
            "filing_indicator": filing_indicator(code),
            "open_keys": [
                {"code": prop, "column": prop, "items": items(domain)}
                for table, prop, domain in open_axes
                if table == code
            ],
            "cells": [
                {
                    "id": f"{code}/r{row}/c{column}",
                    "row": row,
                    "column": column,
                    "sheet": sheet,
                    "datapoint": f"dp{variable}",
                    "data_type": data_type,
                    "items": items(enumerated.get(variable)),
                }
                for table, row, column, sheet, variable, data_type in cells
                if table == code
            ],
        }
        for code, abstract in tables
        if not abstract
    ],
    "rules": [
        {"source": "eba", "code": code, "expression": expression, "precondition": pre}
        for code, expression, pre in rules
    ],
}
Path("x.json").write_text(json.dumps(template, indent=1), encoding="utf-8")
```

Load the result to check it; [`load_template`][dpmsynth.load_template]
names the first field that is wrong:

```python
from dpmsynth import generate, load_template

module = load_template("x.json")
print([table.code for table in module.tables], len(module.rules))
result = generate(module, seed=1)
print(result.summary["passed"], result.failed)
```

```text
['X_01.00', 'X_02.00.a'] 3
3 []
```

Then generate from it:

```console
$ dpm-synth generate x.json -o x.zip --seed 1
rules: 3, passed: 3, failed: 0
rounds: 2 (failing rules per round: 1, 0)
wrote x.zip (5 facts)
```
