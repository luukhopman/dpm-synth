---
description: The standards the reports of dpm-synth follow (EBA Filing Rules v5.9 rules 1.6, 2.18, 3.1 and 3.6; xBRL-CSV 1.0 and Report Packages 1.0 through dpm-xbrl; DPM-XL 0.11 through dpm-xl), with links to the primary sources, what is not followed, and how it is tested.
icon: lucide/badge-check
---

# Standards and conformance

This page lists the published standards that the reports dpm-synth writes
follow, the version of each, how far it goes, and how that is tested. Other
pages link here rather than repeat the versions. dpm-synth implements none
of the formats itself: [dpm-xbrl] writes the package and [dpm-xl] parses and
evaluates the rules, and their standards pages give the details.

| Standard | Version | Publisher | dpm-synth |
| --- | --- | --- | --- |
| [EBA Filing Rules][eba-filing-rules] | 5.9, 26 June 2026 | EBA | Writes reports that follow rules 1.6, 2.18, 3.1 and 3.6, where the template gives what they need. |
| [xBRL-CSV][xbrl-csv-spec] | 1.0, Recommendation of 13 October 2021, errata to 19 April 2023 | XBRL International | Writes reports in the EBA's layout, through dpm-xbrl. |
| [Report Packages][report-packages] | 1.0, Recommendation of 22 September 2023, errata to 11 March 2025 | XBRL International | Writes each report as a `.zip` package, through dpm-xbrl. |
| [DPM-XL][dpm-xl-spec] | 0.11, 18 September 2026 | EBA and EIOPA | Reads and evaluates the template's rules, through dpm-xl. |

dpm-synth is an independent project. It has not been certified by any
standards body, and the EBA does not endorse it. Its reports are synthetic
test data, not submissions.

## EBA Filing Rules

The [EBA Filing Rules][eba-filing-rules], version 5.9 (EBA/XBRL/2026/06,
26 June 2026), say how a report file must be written. Most are met by the
way dpm-xbrl writes a package; these four depend on what dpm-synth puts in
the report.

Rule 1.6, filing indicators
:   Every table's filing indicator is reported as `true`. A template's
    `filing_indicators` lists every template of the module, and those
    without a table in the template are reported as `false`, so the report
    has an indicator for each template of the module (1.6 (d)). See
    [`filing_indicators`](template-format.md#the-module).

Rule 2.18, decimals
:   Each number is rounded to the decimals of its data type, which the
    report declares as its `decimals…` parameters, so the value is correct
    to that many places. Ties go to the even digit, the IEEE 754
    `roundTiesToEven` that the rule asks for when numbers are rounded. A
    template's `decimals` below the rule's minimums (`p` 4, `i` 0, `m` -6)
    is rejected; see [`decimals`](template-format.md#the-module) and
    [rounding](../concepts/repair-loop.md#6-rounding-and-the-final-evaluation).

Rule 3.1, currency
:   Monetary facts are in one reporting currency, the template's
    `currency` or `--currency` (default EUR), written as `baseCurrency`
    only when a monetary fact is reported. A cell with `"unit": true` is
    reported in its currency of denomination (3.1 (b)): the currency of its
    row's `CUS` or `CUA` key (3.1 (c)), else the reporting currency. See
    [`unit`](template-format.md#cells).

Rule 3.6, reporting subject
:   The entity is `<LEI>.CON` or `<LEI>.IND` in the reporting-subject
    scheme, in upper case, or the bare LEI in the LEI scheme before the
    reference date 2022-12-31 and for a module whose code has `_con` or
    `_ind`. See [`--entity`](cli.md#dpm-synth-generate).

Not followed
:   The file name: the package is named as you name the output. dpm-xbrl
    reports a name that does not follow the EBA naming pattern
    (`invalidFileName`, a warning), as in
    [the example below](#how-conformance-is-tested). Reporting subjects
    other than `.CON` and `.IND`, such as `.CRDLIQSUBGRP`, are not
    generated.

dpm-xbrl's [standards page](https://luukhopman.github.io/dpm-xbrl/reference/standards/#eba-filing-rules)
lists every filing rule it checks.

## xBRL-CSV

dpm-synth builds a `dpmxbrl.Report` and writes it with dpm-xbrl's
`write_xbrl_csv`: `reports/report.json` extends the template's
`entry_point`, `parameters.csv` holds the entity, reference date, base
currency and decimals, `FilingIndicators.csv` the filing indicators, and
each table is one CSV file with the EBA's `datapoint` and `factValue`
columns, a column per open key and, for cells in their currency of
denomination, a `unit` column. Scaled packages
([`write_scaled_package`][dpmsynth.write_scaled_package]) stream more rows
into the same layout. See dpm-xbrl's
[standards page](https://luukhopman.github.io/dpm-xbrl/reference/standards/#xbrl-csv).

## Report Packages

Each report is a `.zip` report package with `META-INF/reportPackage.json`
and a root folder named after the file, as dpm-xbrl writes it. See
dpm-xbrl's [standards page](https://luukhopman.github.io/dpm-xbrl/reference/standards/#report-packages).

## DPM-XL

[`load_template`][dpmsynth.load_template] parses every rule and
precondition with dpm-xl and rejects one that does not parse. The rules are
evaluated by dpm-xl, and each ends with one of dpm-xl's
[statuses](json-output.md#rule-statuses), or `skipped` for an inactive
rule. A construct that a single report cannot answer, such as `time_shift`,
is `unsupported`. The language version, and where dpm-xl reads it
differently from the specification, are on dpm-xl's
[standards page](https://luukhopman.github.io/dpm-xl/reference/standards/#dpm-xl).

## How conformance is tested

- **Write, read, evaluate.** [`tests/test_end_to_end.py`](https://github.com/luukhopman/dpm-synth/blob/main/tests/test_end_to_end.py)
  generates every sample template in `docs/samples` with three seeds,
  writes the package, reads it back with dpm-xbrl and evaluates the rules
  with dpm-xl on what was read. It asserts that dpm-xbrl records no filing
  finding of severity `error`, that the facts read are the facts
  generated, and that every rule ends with the same status as in the
  generator.
- **Each filing rule.** Unit tests cover the filing indicators, rounding
  and the decimals minimums, the base currency and the `unit` column, and
  the reporting subject before and after 2022-12-31.
- **Real modules.** On EBA DPM 4.3 COREP_OF, all 1,051 EBA rules that
  apply pass with seed 7, as measured in
  [limits of the loop](../concepts/limits.md#results-on-eba-modules).
  That measurement is run by hand: it needs a template exported from the
  DPM release, which is not in the repository, so the test suite does not
  repeat it.
- **Documentation examples.** Every Python and command-line example on
  these pages runs in the test suite and must print what the page shows.

Named as the EBA naming pattern asks, a generated package reads back with
no filing finding at all:

```python
from dpmxbrl import read_report, write_xbrl_csv

from dpmsynth import generate, load_template

result = generate(load_template("sample.json"), seed=7)
for name in (
    "report.zip",
    "SYNTHETICDPMXL000002.CON_NL_SAMPLE010000_SAMPLE_2026-12-31_20261030120000000.zip",
):
    write_xbrl_csv(result.report, name)
    report = read_report(name)  # (1)!
    print([finding.code for finding in report.filing], report.filing_indicators)
```

1. dpm-xbrl checks the filing rules that the file alone can show; with the
   module's taxonomy package it checks more.

```text
['invalidFileName'] {'S_01.00': True, 'S_02.00': True, 'S_03.00': True, 'S_04.00': False}
[] {'S_01.00': True, 'S_02.00': True, 'S_03.00': True, 'S_04.00': False}
```
