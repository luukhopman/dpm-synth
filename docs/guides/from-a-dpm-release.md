---
description: Build a dpm-synth template for a real module from a DPM release - what an exporter must fill in, a small exporter, choosing rules, generating and reading the results.
---

# Build a template from a DPM release

A real module has thousands of cells and rules, so its template is exported
from a DPM release rather than written by hand. The
[template format](../reference/template-format.md) is the interface:
dpm-synth does not read DPM databases itself, and any tool that can read a
release, such as a script over the EBA's DPM database, can write templates.
This guide shows what such an exporter must fill in, with a small exporter
you can adapt.

## What an exporter fills in

For one module of one release, the exporter writes:

| Template field | From the DPM release |
| --- | --- |
| `release`, `module` | The release code, such as `4.3`, and the module code, such as `COREP_OF`. |
| `entry_point` | The module's xBRL-CSV entry point (its `.json` URL in the taxonomy), if the consumer of the package needs it. |
| `tables[].code` | Every non-abstract table version of the module, such as `C_07.00.a`. |
| `tables[].filing_indicator` | The table's template code, as the module's taxonomy gives it. It is usually the table code without its single-letter parts, such as `C_07.00` for `C_07.00.a` and `C_08.05.1` for `C_08.05.1.a`, but not always. |
| `filing_indicators` | The filing indicators of every template of the module, so that templates without tables in the template are reported as `false`. |
| `tables[].open_keys` | The table's open-axis properties: their codes, the CSV column of each, and for an enumerated property the item qnames of its domain or subdomain. |
| `tables[].cells` | Every reportable cell: its row, column and sheet codes, the datapoint (variable) code that carries its value, the variable's data type code, for enumerated variables the allowed item qnames, and `unit` for a datapoint reported in its currency of denomination. |
| `rules` | The module's validation rules: code, DPM-XL expression and precondition, with a `source` such as `eba`. |
| `decimals` | The reporting decimals per data type, if the defaults (`m` 0, `p` 4, `i` 0, `r` 2) do not suit. |

Leave out abstract tables, cells without a variable and rules of other
modules. Item qnames are written as they appear in a report, such as
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

On EBA DPM 4.3 COREP_OF, with its 1,205 EBA rules, generation takes about
20 rounds (about 20 seconds on a laptop), and 1,050 of the 1,051 rules
that apply pass. The
other 154 rules do not apply to the generated report: they select no
generated cell, such as rows filtered on key values that the generated
rows do not have.
[Limits of the loop](../concepts/limits.md) has the figures for other
modules and explains what remains.

## Read the results

The summary names up to 20 failing rules; `--json` lists them all. To see
why a rule fails, evaluate it on the generated values and explain the
failure with dpm-xl:

```python
from dpmxl import evaluate_rule, explain

from dpmsynth import generate, load_template

template = load_template("sample.json")
result = generate(template, seed=7, max_rounds=0)
rules = {rule.code: rule for rule in template.rules}
for code in result.failed:
    rule = rules[code]
    outcome = evaluate_rule(
        rule.expression, result.data, precondition=rule.precondition
    )
    failure = outcome.failures[0]
    print(code, explain(outcome.evaluation, rule.expression, failure.key).summary)
```

```text
rows 936,000 should equal 2,314,000 (165,000 + 149,000 + 2,000,000): difference 1,378,000, at least 1,377,998 given the reported precision
columns 936,000 should equal 9,253,000 (283,000 + 8,970,000): difference 8,317,000, at least 8,316,998.5 given the reported precision
ratio 90,750 should equal 149,000: difference 58,250, at least 58,240.9 given the reported precision
item [AS:x1] is not one of [AS:x2]
open 69,558,000 should not exceed 150,000: difference 69,408,000, at least 69,407,999 given the reported precision
open-total 5,120,000 should equal 936,000: difference 4,184,000
lei "Synthetic text 5147" does not have the required format
```

Here `max_rounds=0` keeps the starting values, so rules that the solver
and the loop would settle still fail. On a real module, a rule that still
fails is usually nonlinear and coupled to rules that define the same cells,
such as a total of `max(...)` terms; see
[limits of the loop](../concepts/limits.md).
