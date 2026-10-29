---
description: Write a dpm-synth template by hand - a closed table, an open table with enumerated and typed keys, data types, items, rules and preconditions - and check it.
---

# Write a template by hand

Templates for real EBA modules come from a DPM tool (see
[build a template from a DPM release](from-a-dpm-release.md)). Writing one by
hand is useful for your own tables, for a few tables of a module, or for a
test fixture. This guide builds a template in Python and writes it as JSON;
the [template format](../reference/template-format.md) lists every field.

## The module

Start with the format, the release and module codes, and optionally the
entry point and the reference date that the package should carry:

```python
template = {
    "format": "dpm-synth-template/1",
    "release": "1.0",
    "module": "LOANS",
    "entry_point": "https://example.com/taxonomy/loans/1.0/mod/loans.json",
    "reference_date": "2026-06-30",
    "decimals": {"m": -3},  # monetary amounts in thousands
    "tables": [],
    "rules": [],
}
```

## A closed table

A closed table has a fixed set of cells. Give each cell an `id`, its row and
column codes (without the `r` and `c`), the `datapoint` that carries its
value in the package, and its data type: `m` monetary, `p` percentage, `i`
integer, `r` decimal, `e` enumerated, `b` boolean, `d` date, anything else
text.

```python
def cell(table, row, column, datapoint, data_type, **more):
    return {
        "id": f"{table}/r{row}/c{column}",
        "row": row,
        "column": column,
        "datapoint": datapoint,
        "data_type": data_type,
        **more,
    }


template["tables"].append(
    {
        "code": "L_01.00",
        "cells": [
            cell("L_01.00", "0010", "0010", "dp101", "m"),  # total loans
            cell("L_01.00", "0020", "0010", "dp102", "m"),  # of which secured
            cell("L_01.00", "0030", "0010", "dp103", "m"),  # of which unsecured
            cell("L_01.00", "0040", "0010", "dp104", "p"),  # share secured
            cell(
                "L_01.00",
                "0050",
                "0010",
                "dp105",
                "e",
                items=["eba_CT:x1", "eba_CT:x2"],  # allowed items, first is the start
            ),
        ],
    }
)
```

## An open table

An open table has one row per key value. Each `open_keys` entry becomes a
column of the table's file. A key with `items` is enumerated and takes its
items in order; a key without is typed, and gets generated LEI-shaped
identifiers. Cells of an open table usually have row `*`, for every row:

```python
template["tables"].append(
    {
        "code": "L_02.00",
        "open_keys": [
            {"code": "LEI", "column": "c0010"},  # typed: generated identifiers
            {"code": "qCT", "column": "c0020", "items": ["eba_CT:x1", "eba_CT:x2"]},
        ],
        "cells": [
            cell("L_02.00", "*", "0030", "dp201", "m", sheet="*"),  # amount
            cell("L_02.00", "*", "0040", "dp202", "s", sheet="*"),  # name
        ],
    }
)
```

## Rules

Rules are DPM-XL expressions, as [dpm-xl] parses them. A rule may have a
precondition, usually the table's filing indicator; every table of the
template counts as reported.

```python
template["rules"] = [
    {
        "code": "l1",
        "expression": "with {tL_01.00, c0010, default: 0, interval: true}: "
        "{r0010} = {r0020} + {r0030}",
        "precondition": "{v_L_01.00}",
    },
    {"code": "l2", "expression": "with {tL_01.00, c0010}: {(r0020, r0030)} >= 0"},
    {
        "code": "l3",
        "expression": "with {default: 0, interval: true}: "
        "{tL_01.00, r0040, c0010} * {tL_01.00, r0010, c0010} "
        "= {tL_01.00, r0020, c0010}",
    },
    {"code": "l4", "expression": "{tL_01.00, r0050, c0010} in {[eba_CT:x2]}"},
    {
        "code": "l5",
        "expression": "with {default: 0, interval: true}: "
        "sum({tL_02.00, c0030}) <= {tL_01.00, r0010, c0010}",
    },
    {"code": "l6", "expression": "{tL_02.00, c0030} >= 0"},
    {
        "code": "l7",
        "expression": 'match({tL_02.00, c0030}[get LEI], "^[A-Z0-9]{18}[0-9]{2}$")',
    },
]
```

## Check and generate

Write the JSON and load it; [`load_template`][dpmsynth.load_template]
validates every field and names the first wrong one:

```python
import json
from pathlib import Path

from dpmsynth import generate, load_template

Path("loans.json").write_text(json.dumps(template, indent=2), encoding="utf-8")
loaded = load_template("loans.json")
result = generate(loaded, seed=1)
print(result.passed, "passed; failed:", result.failed)
for fact in result.report.facts:
    print(fact.template, fact.datapoint, fact.value, dict(fact.keys))
```

```text
7 passed; failed: []
l_01.00 dp101 1451000 {}
l_01.00 dp102 583000 {}
l_01.00 dp103 868000 {}
l_01.00 dp104 0.4018 {}
l_01.00 dp105 eba_CT:x2 {}
l_02.00 dp201 993000 {'c0010': 'SYNTHEQH524YNG5BY106', 'c0020': 'eba_CT:x1'}
l_02.00 dp202 SYNTHB7O259OWOO3SB53 {'c0010': 'SYNTHEQH524YNG5BY106', 'c0020': 'eba_CT:x1'}
l_02.00 dp201 433000 {'c0010': 'SYNTHA2ROGUBBB8AYN47', 'c0020': 'eba_CT:x2'}
l_02.00 dp202 SYNTH09GLSHV616MTS07 {'c0010': 'SYNTHA2ROGUBBB8AYN47', 'c0020': 'eba_CT:x2'}
```

Monetary amounts are multiples of 1,000, as `"decimals": {"m": -3}` asks,
the share in row 0040 times the total gives the secured loans within the
precision the package reports, and the item rule picked `eba_CT:x2`. Text
cells and typed keys get visibly fictional LEI-shaped values starting with
`SYNTH`; only `match` rules with the LEI or
`dd/mm/yyyy` pattern ask for anything else.

The same file works from the command line:

```console
$ dpm-synth generate loans.json -o loans.zip --seed 1
rules: 7, passed: 7, failed: 0, not evaluated: 0, not applicable: 0
rounds: 2 (failing rules per round: 4, 0)
wrote loans.zip (9 facts)
```

## Mistakes the loader catches

```python
from dpmsynth import TemplateError

broken = json.loads(json.dumps(template))
broken["tables"][1]["open_keys"][0]["column"] = "datapoint"
try:
    load_template(broken)
except TemplateError as error:
    print(error)
```

```text
tables[1].open_keys[0].column: 'datapoint' is a fact column of the table
```

The loader also parses every rule: a rule that does not parse, or that
selects a table the template does not have, is an error of the template.
