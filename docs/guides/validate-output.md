---
description: Check a generated package independently - read it with dpm-xbrl, check it against its template file with dpm-xl check-report or dpmxl.xbrl.ReportProvider, and explain the rules that still fail.
---

# Validate the output with dpm-xbrl and dpm-xl

dpm-synth evaluates the rules on its own values while it generates. To
check the package as a consumer of the report would, read the written ZIP
with [dpm-xbrl] and evaluate the template file's rules on what was read
with [dpm-xl]. The test suite does this for every sample template file.

## Read the package

```python
from dpmxbrl import read_report, write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("sample.json")
result = generate(template, seed=7)
write_xbrl_csv(result.report, "sample.zip")

report = read_report("sample.zip")
print(report.format, report.entity_id, len(report.facts))
for finding in report.filing:
    print(finding.severity, finding.code)
```

```text
xbrl-csv SYNTHETICDPMXL000002.CON 20
warning invalidFileName
```

dpm-xbrl records every [EBA filing rule][dpm-xbrl-filing] the file breaks.
The only one is the file name, which for a real submission encodes the
entity, module and creation time.

## Check the package in one command

`dpm-xl check-report` reads the package with dpm-xbrl, reports the broken
filing rules, places the facts in the template file's tables and
evaluates its rules. It needs dpm-xl's `xbrl` extra:

```bash
pip install "dpm-xl[xbrl]"
dpm-xl check-report sample.json sample.zip
```

```text
report: sample.zip (xbrl-csv); module SAMPLE, release 1.0
warning: reports/report.json: 1 extended metadata document could not be resolved offline (https://example.com/taxonomy/sample/1.0/mod/sample.json); tables without resolved metadata use the EBA datapoint/factValue convention
filing rules broken: 0 errors, 1 warning
  - [warning] file-naming The file name does not follow ReportSubject_Country_FrameworkCodeModuleVersion_Module_ReferenceDate_CreationTimestamp, the structure for reports sent to the EBA.
prior-period: unsupported
  message: time_shift needs the report 1 year(s) earlier (reference date 2025-12-31), which the provider does not have
  records: 0 passed, 0 failed, 0 null
9 rules: 8 passed, 1 unsupported (8 not listed; --all lists every rule)
```

The rules end with the statuses `dpm-synth generate` printed. The warning
says the example taxonomy is not available offline, so the tables are read
by their datapoint codes, which is all the check needs. Rule
`prior-period` compares with last year's report; pass one with
`--previous` to evaluate it. See
[`dpm-xl check-report`](https://luukhopman.github.io/dpm-xl/reference/cli/#dpm-xl-check-report)
for the options and exit statuses.

## Check it in Python

`dpmxl.xbrl.ReportProvider` places the facts of a report read with
dpm-xbrl in the template file's tables, so any rule can be evaluated on
them:

<!-- docs: skip -->
```python
from collections import Counter

from dpmxbrl import read_report
from dpmxl import evaluate_rule
from dpmxl.module import load_module
from dpmxl.xbrl import ReportProvider

module = load_module("sample.json")
provider = ReportProvider(module, read_report("sample.zip"))
statuses = {
    rule.code: evaluate_rule(
        rule.expression, provider, precondition=rule.precondition
    ).status
    for rule in module.rules
}
print(Counter(statuses.values()))
print(provider.unplaced)
```

```text
Counter({'passed': 8, 'unsupported': 1})
()
```

`unplaced` lists the facts that are in no table of the template file; here
there are none. dpm-xl's
[end-to-end guide](https://luukhopman.github.io/dpm-xl/guides/end-to-end/)
takes the same path on a large module, with the columnar evaluator.

## Explain what still fails

On a real module some rules can stay failing (see
[limits of the loop](../concepts/limits.md#rules-that-still-fail)).
`dpm-xl check-report` explains each failing rule. In Python, evaluate the
rule on the generated values and explain the failure with dpm-xl. Here a
rule asks for a three-letter code in a text cell, a pattern the loop does
not repair:

```python
import json
from pathlib import Path

from dpmxl import evaluate_rule, explain

document = json.loads(Path("minimal.json").read_text(encoding="utf-8"))
document["tables"][0]["cells"].append(
    {"id": "T_01.00/r0040", "row": "0040", "column": "0010", "datapoint": "dp1004"}
)
document["rules"].append(
    {"code": "v3", "expression": 'match({tT_01.00, r0040, c0010}, "^[A-Z]{3}$")'}
)
template = load_template(document)
result = generate(template, seed=7)
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
v3 "Synthetic text 1187" does not have the required format
```

The summary of `dpm-synth generate` names up to 20 failing rules; `--json`
lists them all.
