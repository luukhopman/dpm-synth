---
description: What dpm-synth is, a 30-second example in Python and on the command line, installation, the standards its reports follow and where to go next.
---

# dpm-synth

dpm-synth generates synthetic EBA xBRL-CSV report packages that satisfy a
module's DPM-XL validation rules. Give it a template that lists a module's
tables, cells and rules; it fills every cell with a plausible value, repairs
the values until the rules pass, and writes a report package that reads and
validates like a real submission.

dpm-synth is an independent project, not affiliated with or endorsed by the
European Banking Authority.

<div class="toolkit-badges" markdown>

[xBRL-CSV 1.0](reference/standards.md#xbrl-csv)
[Report Packages 1.0](reference/standards.md#report-packages)
[EBA Filing Rules 5.9](reference/standards.md#eba-filing-rules)
[DPM-XL 0.11](reference/standards.md#dpm-xl)
[Python 3.11+](project/stability.md#python-versions)

</div>

It is for teams that build loaders, data warehouses or validators for EBA
reports and need internally consistent test submissions without real
supervisory data. It builds on [dpm-xl], which evaluates the rules, and
[dpm-xbrl], which writes the package. The entity is a fictional LEI and
every value is generated.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Standards and conformance](reference/standards.md){ .md-button }

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
       [template format](reference/template-format.md). A path or the
       parsed JSON.
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

The template [`minimal.json`](samples/minimal.json) has one table of three
monetary cells and two rules: row 0010 is the sum of rows 0020 and 0030,
and both components are not negative. Every example in these pages runs
against the templates in
[`docs/samples`](https://github.com/luukhopman/dpm-synth/tree/main/docs/samples),
and the test suite checks that each prints what is shown.

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

## Find your way

<div class="grid cards" markdown>

-   :lucide-graduation-cap:{ .lg .middle } **Getting started**

    ---

    Install dpm-synth, generate a first report, read it back and check
    its rules, step by step.

    [:lucide-arrow-right: Tutorial](getting-started.md)

-   :lucide-list-checks:{ .lg .middle } **How-to guides**

    ---

    Recipes for one task each: write a template, shape a realistic report,
    load-test, reproduce a report, validate the output.

    [:lucide-arrow-right: Guides](guides/index.md)

-   :lucide-lightbulb:{ .lg .middle } **Concepts**

    ---

    How the joint solve and the evaluate-and-repair loop work, and where
    they stop.

    [:lucide-arrow-right: Concepts](concepts/index.md)

-   :lucide-library:{ .lg .middle } **Reference**

    ---

    The template format, the command line, exit statuses, JSON output, the
    Python API and the standards.

    [:lucide-arrow-right: Reference](reference/index.md)

</div>

## Features

- **Any module.** The template format describes tables, open keys, cells,
  data types, allowed items and rules, so one tool covers COREP, FINREP and
  every other DPM framework; see the [template format](reference/template-format.md).
- **Rules satisfied, not just shapes.** Linear rules are solved jointly;
  products of two cells, `isnull`, `in`, `match` and the rest are repaired;
  on EBA DPM 4.3 COREP_OF, all 1,051 rules that apply pass with seed 7. See
  [the evaluate-and-repair loop](concepts/repair-loop.md) and
  [its limits](concepts/limits.md).
- **Realistic shape.** Amounts for a small, medium or large institution,
  sparse reports, a reporting currency and currencies of denomination, and
  rules graded as warnings or switched off; see
  [shape a realistic report](guides/realistic-reports.md).
- **Filing rules followed.** Filing indicators, decimals, currencies and the
  reporting subject follow the EBA filing rules, and dpm-xbrl reads the
  packages back without a broken filing rule other than the file name; see
  [standards and conformance](reference/standards.md).
- **Reproducible.** The same template, seed, options and versions give the
  same bytes; see [reproduce a report](guides/reproducible-seeds.md).
- **Large.** Scaled packages stream open tables with millions of rows; see
  [load-test with scaled packages](guides/load-testing.md).
- **For AI agents too.** The essentials on [one page](agents.md), and every
  page as Markdown in [`llms.txt`](llms.txt) and
  [`llms-full.txt`](llms-full.txt).

## Part of the dpm toolkit

dpm-synth generates the reports that [dpm-xbrl] reads and [dpm-xl]
evaluates; the [toolkit page](toolkit.md) shows how they fit together.

--8<-- "docs/.snippets/toolkit-cards.md"
