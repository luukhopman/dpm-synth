---
description: Get a dpm-synth template for a real EBA module from a DPM release - no public exporter exists yet, so what an exporter must write, where each field comes from, and a small exporter to adapt.
icon: lucide/database
---

# Get a template from a DPM release

A real module has thousands of cells and rules, so its template is exported
from the EBA's DPM release rather than written by hand.

!!! warning "No public exporter yet"

    dpm-synth does not read DPM releases, and no published tool exports
    templates from one yet. You write the exporter: a script over the
    release's DPM database that writes one module in the
    [template format](../reference/template-format.md). This guide lists
    what it must write and gives a small exporter to start from.

The same fields make a [module file](https://luukhopman.github.io/dpm-xl/reference/module-file/)
for dpm-xl, so one export serves both packages; see the
[toolkit page](../toolkit.md).

## What an exporter writes

For one module of one release:

| Template field | From the DPM release |
| --- | --- |
| `release`, `module` | The release code, such as `4.3`, and the module code, such as `COREP_OF`. |
| `entry_point` | The module's xBRL-CSV entry point, the `.json` URL in its taxonomy package. Take it from the package: the folder and version in the URL do not always follow the module code and release. |
| `tables[].code` | Every non-abstract table version of the module, such as `C_07.00.a`. |
| `tables[].filing_indicator` | The table's template code, as the module's taxonomy gives it. It is usually the table code without its single-letter parts, such as `C_07.00` for `C_07.00.a` and `C_08.05.1` for `C_08.05.1.a`, but not always. |
| `filing_indicators` | The filing indicators of every template of the module, so that templates without tables in the template are reported as `false`. |
| `tables[].open_keys` | The table's open-axis properties: their codes, the CSV column of each, the item qnames of an enumerated property's domain or subdomain, and the data type of a typed one. |
| `tables[].cells` | Every reportable cell: its row, column and sheet codes, the datapoint (variable) code that carries its value, the variable's data type code, the allowed item qnames of an enumerated variable, and `unit` for a datapoint reported in its currency of denomination. |
| `rules` | The module's validation rules: code, DPM-XL expression and precondition, `severity`, and `active: false` for a deactivated rule. |
| `decimals` | The reporting decimals per data type, if the defaults (`m` 0, `p` 4, `i` 0, `r` 2) do not suit. |

Leave out abstract tables, cells without a variable and rules of other
modules. Write item qnames as they appear in a report, such as
`eba_qEC:qx16`; dpm-synth writes them back unchanged.

## A small exporter

An exporter is a query per field. Here the release's rows are plain Python
lists, standing in for the query results of your DPM database:

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
    ("X_02.00.a", "*", "0010", "*", "510", "m"),
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

## Choose the rules

Each rule carries a `source`. If the release, or your own rule set, has
rules from more than one source, keep the ones you want before generating.
`ModuleTemplate` is a frozen dataclass, so `dataclasses.replace` gives a
copy with other rules, or other tables:

```python
from dataclasses import replace

own = replace(module, rules=tuple(r for r in module.rules if r.source == "eba"))
print(len(own.rules))
```

```text
3
```

## Generate

```console
$ dpm-synth generate x.json -o x.zip --seed 1
rules: 3, passed: 3, failed: 0
rounds: 2 (failing rules per round: 1, 0)
wrote x.zip (5 facts)
```

On a real module, expect some rules to stay failing or not to apply.
[Limits of the loop](../concepts/limits.md) has the figures for EBA DPM 4.3
modules, explains what remains, and shows how to explain a failing rule
with dpm-xl.
