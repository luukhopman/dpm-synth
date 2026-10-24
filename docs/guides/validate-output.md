---
description: Check a generated package independently - read it with dpm-xbrl, check the EBA filing rules, bind its facts to a dpm-xl provider through the template, and evaluate the module's rules.
---

# Validate the output with dpm-xbrl and dpm-xl

dpm-synth evaluates the rules on its own values while it generates. To be
sure the package says the same, check it as a downstream consumer would:
read the written ZIP file with [dpm-xbrl], and evaluate the template's rules
on what was read with [dpm-xl]. The test suite does exactly this for every
sample template.

## Generate and read back

```python
from dpmxbrl import read_report, write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("sample.json")
result = generate(template, seed=7)
write_xbrl_csv(result.report, "sample.zip")

report = read_report("sample.zip")
print(report.format, report.entity_id, len(report.facts))
for finding in report.filing:
    print(finding.severity, finding.rule, finding.code)
```

```text
xbrl-csv SYNTHETICDPMXL000002.CON 20
warning File naming invalidFileName
```

dpm-xbrl records every [EBA filing rule][dpm-xbrl-filing] the file breaks.
The only one is the file name, which for a real submission encodes the
entity, module and creation time.

## A provider over the package

dpm-xl evaluates rules against a data provider: an object that answers a
selection such as `{tS_01.00, r0010, c0010}` with data points. The facts of
an EBA xBRL-CSV package carry a datapoint, not row and column codes, so the
template's cells place them. This provider knows nothing of dpm-synth's own
values; everything comes from the package
(see [writing a provider][dpm-xl-provider] for the protocol):

```python
from datetime import date
from decimal import Decimal

from dpmxl import DataPoint, Item, Number, axis_matches

DECIMALS = {
    "m": "decimalsMonetary",
    "p": "decimalsPercentage",
    "i": "decimalsInteger",
    "r": "decimalsDecimal",
}


def selected(code, selector):
    if selector is None or selector.wildcard:
        return True
    return code not in (None, "*") and axis_matches(code, selector)


class PackageProvider:
    """Facts of a report read with dpm-xbrl, placed by a template's cells."""

    def __init__(self, template, report):
        self.template, self.report = template, report
        self.rows = {}  # table code -> key row -> datapoint -> value
        for fact in report.facts:
            table = template.table(fact.template)
            cell = next(c for c in table.cells if c.datapoint == fact.datapoint)
            columns = {key.column: key for key in table.open_keys}
            keys = tuple(
                (columns[name].code, Item.parse(text) if columns[name].items else text)
                for name, text in fact.keys.items()
            )
            row = self.rows.setdefault(table.code, {}).setdefault(keys, {})
            row[fact.datapoint] = self.value(cell.data_type, fact.value)

    def value(self, data_type, text):
        if text is None:
            return None
        if data_type in DECIMALS:  # reported decimals become the tolerance
            decimals = self.report.decimals_parameters.get(DECIMALS[data_type])
            return Number.of(Decimal(text), decimals)
        if data_type == "e":
            return Item.parse(text)
        if data_type == "b":
            return text == "true"
        if data_type == "d":
            return date.fromisoformat(text)
        return text

    def select(self, query):
        table = self.template.table(query.table)
        if table is None:
            raise LookupError(f"table {query.table} is not in the template")
        return [
            DataPoint(
                table=table.code,
                row=cell.row,
                column=cell.column,
                sheet=cell.sheet,
                keys=dict(keys),
                value=values.get(cell.datapoint),
                ref=(table.code, cell.datapoint, keys),
            )
            for keys, values in self.rows.get(table.code, {}).items()
            for cell in table.cells
            if selected(cell.row, query.rows)
            and selected(cell.column, query.columns)
            and selected(cell.sheet, query.sheets)
        ]

    def table_reported(self, table):
        folded = table.casefold()
        return any(
            reported and code.casefold() == folded
            for code, reported in self.report.filing_indicators.items()
        ) or any(
            t.code.casefold() == folded and t.code in self.rows
            for t in self.template.tables
        )

    def parameter(self, name):
        if name.casefold() == "refperiod":
            return self.report.reference_date
        if name.casefold() == "reportinglevel":
            return self.report.entity_id.rsplit(".", 1)[-1].casefold()
        return None

    def open_keys(self, table):
        found = self.template.table(table)
        return tuple(key.code for key in found.open_keys) if found else ()
```

## Evaluate the rules

```python
from collections import Counter

from dpmxl import evaluate_rule

provider = PackageProvider(template, report)
statuses = {
    rule.code: evaluate_rule(
        rule.expression, provider, precondition=rule.precondition
    ).status
    for rule in template.rules
}
print(Counter(statuses.values()))
failed = [code for code, status in statuses.items() if status == "failed"]
print(failed == result.failed)
```

```text
Counter({'passed': 8, 'unsupported': 1})
True
```

The package passes the same eight rules. The ninth, a `time_shift`, is
`unsupported` here, as it is "not evaluated" in the generator: a single
report has no previous period. To evaluate it, give the provider an
`earlier_report(period, count)` method that returns a provider over last
year's package.

For a large module, use dpm-xl's columnar evaluator and its
[end-to-end guide](https://luukhopman.github.io/dpm-xl/guides/end-to-end/),
which reads a package with dpm-xbrl in the same way.
