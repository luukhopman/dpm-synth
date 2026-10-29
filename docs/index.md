---
description: What dpm-synth is, who it is for, a 30-second example, installation and where to go next.
---

# dpm-synth

dpm-synth generates synthetic EBA xBRL-CSV report packages that satisfy a
module's DPM-XL validation rules. Give it a template that lists a module's
tables, cells and rules; it fills every cell with a plausible value, repairs
the values until the rules pass, and writes a report package that reads and
validates like a real submission.

dpm-synth is an independent project, not affiliated with or endorsed by the
European Banking Authority.

It builds on two sibling packages: [dpm-xl] evaluates the rules and
[dpm-xbrl] writes the package. It needs Python 3.11 or newer. The reports it
writes are synthetic: the entity is a fictional LEI and every value is
generated.

## Who it is for

- Teams that build loaders, data warehouses or validators for EBA reports
  and need realistic, internally consistent test submissions for any
  module, without using real supervisory data.
- Performance tests that need report packages with millions of facts.
- Rule authors who want to see a module's rules satisfied, or find the
  rules that cannot be satisfied together.

## In 30 seconds

```python
from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("minimal.json")  # a module's tables, cells and rules
result = generate(template, seed=7)
summary = result.summary  # rules counted by status
print(summary["passed"], "of", summary["rules"], "rules pass; failing:", result.failed)
write_xbrl_csv(result.report, "report.zip")
for fact in result.report.facts:
    print(fact.template, fact.datapoint, fact.value)
```

```text
2 of 2 rules pass; failing: []
t_01.00 dp1001 1126000
t_01.00 dp1002 971000
t_01.00 dp1003 155000
```

The template [`minimal.json`](samples/minimal.json) has one table of three
monetary cells and two rules: row 0010 is the sum of rows 0020 and 0030,
and both components are not negative. The same from the command line:

```console
$ dpm-synth generate minimal.json -o report.zip --seed 7
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report.zip (3 facts)
```

Every example in these pages runs against the templates in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples),
and the test suite checks that each prints what is shown.

## Install

```text
pip install dpm-synth
```

This installs dpm-xl and dpm-xbrl too, and the `dpm-synth` command.

## Key features

- **Any module.** The template format describes tables, open keys, cells,
  data types, allowed items and rules, so one tool covers COREP, FINREP and
  every other DPM framework; see the [template format](reference/template-format.md).
- **Rules satisfied, not just shapes.** Linear rules are solved jointly;
  products of two cells, `isnull`, `in`, `match` and the rest are repaired;
  on EBA DPM 4.3 COREP_OF, 1,050 of the 1,051 rules that apply pass. See
  [the evaluate-and-repair loop](concepts/repair-loop.md) and
  [its limits](concepts/limits.md).
- **Valid packages.** Packages are written by dpm-xbrl and read back without
  a single broken EBA filing rule that the file can show, other than the
  synthetic file name.
- **Reproducible.** The same template, seed, options and versions give the
  same bytes; see [reproduce a report](guides/reproducible-seeds.md).
- **Large.** Scaled packages stream open tables with millions of rows in
  seconds; see [load-test with scaled packages](guides/load-testing.md).

## Toolkit

--8<-- "docs/.snippets/toolkit.md"

## Where next

- New here: the [getting started](getting-started.md) tutorial.
- A task to do: the [how-to guides](guides/index.md).
- How it works: the [concepts](concepts/index.md).
- Exact behaviour: the [reference](reference/index.md), including the
  [template format](reference/template-format.md), the
  [API](reference/api.md) and the [command line](reference/cli.md).
- Working with an AI agent: [dpm-synth for AI agents](agents.md),
  [`llms.txt`](llms.txt) and [`llms-full.txt`](llms-full.txt).
- The sibling packages: [dpm-xl] for DPM-XL rules and [dpm-xbrl] for
  reading and writing reports.
