---
description: What the repair loop achieves on real EBA modules, which rules stay failing, which are not evaluated or do not apply, and why.
---

# Limits of the loop

The [evaluate-and-repair loop](repair-loop.md) changes one cell at a time
to fix one failing comparison. That settles most rules of real modules, but
not all: some rules constrain the same cells in ways that local repairs
cannot reconcile. A report that passes every rule is therefore not
guaranteed; the result always says which rules still fail.

## Results on EBA modules

EBA DPM 4.3 modules, their EBA validation rules only, seed 7, default
options, on a laptop (AMD Ryzen 7 4700U):

| Module | Tables | Cells | Rules | Apply | Pass | Fail | Not applicable | Not evaluated | Rounds | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| COREP_OF | 81 | 21,339 | 1,205 | 1,051 | 988 | 63 | 154 | 0 | 15 | 15 s |
| FINREP9 | 124 | 13,834 | 2,260 | 2,258 | 1,938 | 320 | 0 | 2 | 19 | 15 s |
| AE | 23 | 1,306 | 218 | 218 | 207 | 11 | 0 | 0 | 10 | 1 s |
| COREP_LCR_DA | 14 | 5,119 | 328 | 328 | 321 | 7 | 0 | 0 | 9 | 3 s |
| COREP_LE | 5 | 79 | 25 | 25 | 24 | 1 | 0 | 0 | 8 | < 1 s |

"Apply" counts the rules that are evaluated and whose precondition holds.
On each of these modules, the rules that pass and fail on the generated values are
exactly those that pass and fail when the written package is read back with
dpm-xbrl and evaluated with dpm-xl, as in
[validate the output](../guides/validate-output.md).

## Rules that still fail

- **A cell defined twice.** Two rules give the same cell different
  definitions, such as a capital amount as the sum of its components and as
  a ratio times the total risk exposure, while the ratio has its own
  minimum. Each repair undoes the other; the loop stops when the failing
  count no longer improves.
- **Totals over open tables that are also constrained per row.** A sum
  over all rows of an open table must equal a total, and each row is
  bounded by other rules; the repair of the sum moves one row past its own
  bounds, or cannot.
- **Chains of inequalities.** `a <= b`, `b <= c` and `c <= a + d`, with
  some of the cells defined by sums elsewhere, can need several cells to
  move together.
- **Precision.** A rule without `interval: true` that multiplies a ratio
  by an amount holds before rounding but can miss by a few units after the
  ratio is rounded to its reporting decimals.

The [export guide](../guides/dpm-export.md#read-the-results) shows
how to explain each failing rule with dpm-xl.

## Rules that are not evaluated

`not_evaluated` holds the rules dpm-xl reports as an error or as
unsupported, with the reason:

- `time_shift` compares with an earlier period, and a single report has
  none;
- a rule on a table that is not in the module's template;
- a rule that does not parse, or uses a construct dpm-xl does not support.

They do not count towards the exit status.

## Rules that do not apply

`not_applicable` holds the rules that the generated report gives nothing to
check: the precondition is false, or the rule selects no generated cell.
On COREP_OF these are mostly rules that filter an open table on key values,
such as `[where CEG = [eba_GA:qx2014]]`, when the generated key rows use
other items. More rows (`--open-rows`) cover more items, at the cost of
time: enumerated keys take their items in order.

## Regular expressions

`match` is repaired for the two patterns EBA rules use, LEIs and
`dd/mm/yyyy` dates. Any other pattern is evaluated but not repaired.

## What would do better

Solving a module's linear equalities jointly, with a sparse least-squares
or mixed-integer solver, before repairing the rest would settle most cells
defined twice consistently, or prove that the rules contradict each other.
The template already carries what such a solver needs.
