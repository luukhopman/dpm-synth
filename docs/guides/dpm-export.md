---
description: Generate a synthetic report for a real EBA module from a template that a DPM tool exports, choose the rules to keep, and read the results.
---

# Generate from a DPM export

A real module has thousands of cells and rules, so its template is exported
from a DPM database rather than written by hand. a DPM tool, a separate
tool that prepares EBA DPM releases, writes `dpm-synth-template/1`
templates with its `report-template` command. Any other tool that writes the
[template format](../reference/template-format.md) works the same way.

## Export the template

With a prepared DPM release in a DPM tool:

<!-- docs: skip -->
```console
$ dpm-export 4.3 COREP_OF -o corep_of.json
Wrote 81 tables and 1510 rules to corep_of.json
```

The template holds every non-abstract table of the module with its cells
(datapoint, coordinates, data type and, for enumerated cells, the allowed
items of their domain), the open keys of each open table, the module's
validation rules with their preconditions, and default decimals per data
type. The export may leave `entry_point` and `reference_date` empty;
set them in the JSON, or pass `--reference-date`, if your consumer needs
them.

## Choose the rules

Each rule carries a `source`. An export may include rules from more than
one source; if you want only the EBA's own rules, keep those before
generating:

<!-- docs: skip -->
```python
from dataclasses import replace

from dpmsynth import generate, load_template

template = load_template("corep_of.json")
template = replace(
    template, rules=tuple(r for r in template.rules if r.source == "eba")
)
result = generate(template, seed=7)
```

`ModuleTemplate` is a frozen dataclass, so `dataclasses.replace` gives a
copy with other rules, or other tables.

## Generate

<!-- docs: skip -->
```console
$ dpm-synth generate corep_of.json -o corep_of.zip --seed 7
```

On EBA DPM 4.3 COREP_OF, with its 1,205 EBA rules, generation takes about
15 seconds and 15 rounds, and 988 of the 1,051 rules that apply pass. The
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
result = generate(template, seed=7, max_rounds=1)
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
open 39,000 should not exceed -600,000: difference 639,000, at least 638,999 given the reported precision
open-total 332,000 should equal 1,135,000: difference 803,000
rows 1,135,000 should equal -180,000 (717,000 + 75,000 − 972,000): difference 1,315,000, at least 1,314,998 given the reported precision
```

Here the loop was stopped after one round, so rules that more rounds would
settle still fail. On a real module, a rule that still fails after the
loop stops is usually coupled to another rule that defines the same cell
differently; see [limits of the loop](../concepts/limits.md).
