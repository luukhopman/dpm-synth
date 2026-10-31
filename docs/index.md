---
description: Generate synthetic EBA xBRL-CSV test reports that pass Data Point Model (DPM 2.0) validation rules, in Python - install, a 30-second example and where to go next.
---

# dpm-synth: synthetic EBA test reports in Python

dpm-synth generates synthetic EBA supervisory reports: xBRL-CSV report
packages, such as COREP or FINREP reports, whose values are made up but
pass the module's DPM-XL validation rules. You give it a template file with
a module's tables, cells and rules, such as the module file
`dpm-xl export-module` writes from a release of the EBA Data Point Model
(DPM 2.0); it fills every cell with a plausible value, repairs the values
until the rules pass, and writes a report package that reads and validates
like a real submission.

dpm-synth is an independent project, not affiliated with or endorsed by the
European Banking Authority.

It is for teams that build loaders, data warehouses or validators for EBA
reports and need internally consistent test reports without real
supervisory data. The entity is a fictional LEI and every value is
generated. It builds on [dpm-xl], which evaluates the rules, and
[dpm-xbrl], which writes the package.

[Get started](getting-started.md){ .md-button .md-button--primary }

## Install

=== "pip"

    ```text
    pip install dpm-synth
    ```

=== "uv"

    ```text
    uv add dpm-synth
    ```

This installs dpm-xl and dpm-xbrl too. The import name is `dpmsynth`; the
command is `dpm-synth`.

## In 30 seconds

=== "Python"

    ```python
    from dpmxbrl import write_xbrl_csv

    from dpmsynth import generate, load_template

    template = load_template("minimal.json")  # (1)!
    result = generate(template, seed=7)  # (2)!
    summary = result.summary
    print(summary["passed"], "of", summary["rules"], "rules pass:", result.failed)
    write_xbrl_csv(result.report, "report.zip")  # (3)!
    for fact in result.report.facts:
        print(fact.template, fact.datapoint, fact.value)
    ```

    1. A module's tables, cells and rules, in the
       [template format](reference/template-format.md): a path to the
       template file, or the parsed JSON.
    2. Fills every cell and repairs the values until the rules pass. The
       same seed gives the same report.
    3. `result.report` is a `dpmxbrl.Report`; dpm-xbrl writes it as an
       xBRL-CSV report package.

    ```text
    2 of 2 rules pass: []
    t_01.00 dp1001 9253000
    t_01.00 dp1002 283000
    t_01.00 dp1003 8970000
    ```

=== "Command line"

    ```console
    $ dpm-synth generate minimal.json -o report.zip --seed 7  # (1)!
    rules: 2, passed: 2, failed: 0
    rounds: 1 (failing rules per round: 0)
    wrote report.zip (3 facts)
    ```

    1. Add `--size large`, `--fill 0.5` or `--currency SEK` to shape the
       report; see [shape a realistic report](guides/realistic-reports.md).

The template file [`minimal.json`](samples/minimal.json) has one table of
three monetary cells and two rules: row 0010 is the sum of rows 0020 and 0030,
and both components are not negative. Every example in these pages runs
against the templates in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples),
and the test suite checks that each prints what is shown.

## From an EBA DPM release

For a real module, export its module file from the EBA's DPM database with
dpm-xl, and generate from that file:

```bash
pip install dpm-xl
dpm-xl export-module dpm-4.4.sqlite COREP_OF --release 4.3 -o module.json
dpm-synth generate module.json -o report.zip --seed 7
```

`dpm-4.4.sqlite` is the EBA's DPM 2.0 database as a SQLite file;
[get a template from a DPM release](guides/from-a-dpm-release.md) says
where to get it and what to expect.

## Find your way

<div class="grid cards" markdown>

-   :lucide-graduation-cap:{ .lg .middle } **Getting started**

    ---

    Install dpm-synth, generate a first report, look inside it, read it
    back and check its rules, step by step.

    [:lucide-arrow-right: Tutorial](getting-started.md)

-   :lucide-list-checks:{ .lg .middle } **How-to guides**

    ---

    Recipes for one task each: get a template from a DPM release, write
    one, shape a realistic report, load-test, reproduce a report, validate
    the output.

    [:lucide-arrow-right: Guides](guides/index.md)

-   :lucide-lightbulb:{ .lg .middle } **Concepts**

    ---

    How dpm-synth makes the values pass the rules, and where that stops.

    [:lucide-arrow-right: Concepts](concepts/index.md)

-   :lucide-library:{ .lg .middle } **Reference**

    ---

    The template format, the command line, exit statuses, JSON output, the
    Python API and the standards.

    [:lucide-arrow-right: Reference](reference/index.md)

</div>

## Features

- **Any module.** The [template format](reference/template-format.md)
  describes tables, open keys, cells, every DPM data type, allowed items
  and rules, so one tool covers COREP, FINREP and every other DPM
  framework, from the module file of a DPM release or a file you write.
- **Rules satisfied, not just shapes.** Linear rules are solved together,
  and the rest are repaired one value at a time; the result names the
  rules that still fail. See [limits of the loop](concepts/limits.md).
- **Realistic shape.** Amounts for an institution size, sparse reports,
  currencies, rule severities and inactive rules; see
  [shape a realistic report](guides/realistic-reports.md).
- **Valid packages, reproducibly.** Filing indicators, decimals,
  currencies and the reporting subject follow the EBA filing rules
  ([standards](reference/standards.md)), and a seed reproduces a report
  byte for byte ([reproduce a report](guides/reproducible-seeds.md)).
- **Large.** Scaled packages stream open tables with millions of rows; see
  [load-test with scaled packages](guides/load-testing.md).

The essentials for AI agents are on [one page](agents.md), and every page
is in [`llms.txt`](llms.txt) and [`llms-full.txt`](llms-full.txt).

## Part of the dpm toolkit

dpm-synth generates the reports that [dpm-xbrl] reads and [dpm-xl]
evaluates; the [toolkit page](toolkit.md) shows how they fit together.

--8<-- "docs/.snippets/toolkit-cards.md"
