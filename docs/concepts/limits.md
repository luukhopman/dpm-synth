---
description: What the joint solve and the repair loop achieve on real EBA modules, which rules stay failing, which cannot be evaluated or do not apply, and why.
---

# Limits of the loop

The [joint solve and the evaluate-and-repair loop](repair-loop.md) settle
almost every rule of real modules, but not all: the joint solve covers
linear rules only, and the loop changes one cell at a time. A report that
passes every rule is therefore not guaranteed; the result always says which
rules still fail.

## Results on EBA modules

--8<-- "docs/.snippets/corep-of.md"

In detail: the module file is release 4.3, exported from the
EBA's 4.4 database with
`dpm-xl export-module dpm-4.4.sqlite COREP_OF --release 4.3`, measured on
2026-10-31 with the dpm-synth, dpm-xl and dpm-xbrl versions these pages
document; seed 7, default options. The time is wall clock on a laptop
(AMD Ryzen 7 4700U) and only indicates the scale:

| COREP_OF, release 4.3 | |
| --- | --- |
| Tables and cells | 81 tables, 21,339 cells |
| Rules | 1,418: 182 skipped, 1,178 apply, 58 not applicable |
| Rules that apply | 1,177 pass, 1 fails |
| Rounds | 14 |
| Facts written | 25,432 |
| Time | 30 s |

- Skipped rules are those the EBA deactivated (`"active": false`); the
  other 1,236 rules are evaluated.
- The rules that apply are those that are evaluated and whose precondition
  holds. None is `error` or `unsupported`.
- The rule that fails is the warning `v4810_m`, so the exit status is 0.
  Seeds 0 to 4 leave `v4810_m`, the error `v6290_m`, or both failing.

Other modules of release 4.3, exported and measured the same way, with
seeds 0 to 4 and default options:

| Module | Rules that apply | Failing |
| --- | --- | --- |
| AE | 218 | 0 |
| COREP_ALM | 134 | 0 |
| COREP_LCR_DA | 328 | 0 to 2 warnings and errors |
| COREP_LE | 25 | 0 |
| DORA | 66 | 0 |
| FINREP9 | about 2,250 | 45 to 65, mostly warnings |

FINREP9 fails on linear rules the joint solve cannot settle within its
passes once the repairs of non-linear rules have moved their cells.

`dpm-xl check-report` on the written package gives the same statuses, so
the rules that pass and fail on the generated values are exactly those
that pass and fail when the package is read back, as in
[validate the output](../guides/validate-output.md).

## Rules that still fail

- **Totals of `max(...)`.** A total row of an open table holds
  `c0410 = c0420 + ... + max(c0470, c0480)`, and so does every row, and the
  total row is the sum of the rows. That holds only if the same column is
  the larger one in every row; the loop does not choose it.
- **Other non-linear rules coupled to linear ones.** Products of two cells,
  `max` and `min` are repaired one cell at a time, after the joint solve
  (an `if` joins the solve with the branch its condition picks); a repair can break a linear rule that the second solve then
  restores at the cost of the first.
- **Contradictions.** Equalities that contradict each other, or bounds that
  leave no room, have no solution; the solve gets as close as it can.
- **Precision.** A rule without `interval: true` that multiplies a ratio
  by an amount holds before rounding but can miss by a few units after the
  ratio is rounded to its reporting decimals.

`v4810_m` on COREP_OF is such a total of `max(...)`: column 0410 of
C_06.01 must equal the sum of that column over the rows of C_06.02.
`dpm-xl check-report` explains it:

```text
v4810_m: failed (warning)
  records: 22 passed, 1 failed, 0 null
  - c=0410: 246,627,000 should equal 251,695,000: difference 5,068,000, at least 5,067,998.5 given the reported precision
```

`v6290_m`, where other seeds leave it failing, is a sum with a `max(...)`
term whose total C_04.00 row 0740 is also divided by another cell in
`v6263_m` and `v6264_m`: a product or ratio coupled to a linear rule.

[Explain what still fails](../guides/validate-output.md#explain-what-still-fails)
shows how to explain a failing rule yourself.

## Rules that cannot be evaluated

dpm-xl reports some rules as `unsupported` or `error`, and the result's
`messages` give the reason:

- `time_shift` compares with an earlier period, and a single report has
  none (`unsupported`);
- a rule that uses a construct dpm-xl does not support.

A rule that does not parse, or that selects a table the template file does
not have, is an error of the template file. A rule on a reporting template
that is listed in `filing_indicators` but has no tables in the file is
`not_applicable`.

A rule of severity `error` that is an `error` makes exit status 1, as a
failing one does (with `--fail-on warning`, warnings count too); an
`unsupported` rule never changes the exit status.

## Rules that do not apply

`not_applicable` rules are those the generated report gives nothing to
check: the precondition is false, or the rule selects no generated cell.
On COREP_OF these are mostly rules that filter an open table on key values,
such as `[where CEG = [eba_GA:qx2014]]`, when the generated key rows use
other items. More rows (`--open-rows`) cover more items, at the cost of
time: enumerated keys take their items in order.

## Regular expressions

`match` is repaired for the two patterns EBA rules use, LEIs and
`dd/mm/yyyy` dates. Any other pattern is evaluated but not repaired.
