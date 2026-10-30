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

EBA DPM 4.3 modules, their EBA validation rules only, seed 7, default
options, with dpm-xl and dpm-xbrl 1.0.0. COREP_OF is measured with this
version; the other modules with dpm-synth 1.0.0, before the joint solve of
linear rules, which on COREP_OF had 52 failing rules. Times are wall clock
on a laptop (AMD Ryzen 7 4700U) and only indicate the scale; the other
columns do not depend on the machine:

| Module | Tables | Cells | Rules | Apply | Pass | Fail | Not applicable | Unsupported | Rounds | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| COREP_OF | 81 | 21,339 | 1,205 | 1,051 | 1,051 | 0 | 154 | 0 | 13 | 17 s |
| FINREP9 (1.0.0) | 124 | 13,834 | 2,260 | 2,258 | 1,929 | 329 | 0 | 2 | 14 | 10 s |
| AE (1.0.0) | 23 | 1,306 | 218 | 218 | 207 | 11 | 0 | 0 | 10 | < 1 s |
| COREP_LCR_DA (1.0.0) | 14 | 5,119 | 328 | 328 | 321 | 7 | 0 | 0 | 9 | 2 s |
| COREP_LE (1.0.0) | 5 | 79 | 25 | 25 | 24 | 1 | 0 | 0 | 9 | < 1 s |

On COREP_OF, seeds 0 to 4 leave 0 to 2 failing rules, against 51 to 55
before the joint solve.

"Apply" counts the rules that are evaluated and whose precondition holds.
On each of these modules, the rules that pass and fail on the generated values are
exactly those that pass and fail when the written package is read back with
dpm-xbrl and evaluated with dpm-xl, as in
[validate the output](../guides/validate-output.md).

## Rules that still fail

- **Totals of `max(...)`.** A total row of an open table holds
  `c0410 = c0420 + ... + max(c0470, c0480)`, and so does every row, and the
  total row is the sum of the rows. That holds only if the same column is
  the larger one in every row; the loop does not choose it.
- **Other non-linear rules coupled to linear ones.** Products of two cells,
  `max`, `min` and `if` are repaired one cell at a time, after the joint
  solve; a repair can break a linear rule that the second solve then
  restores at the cost of the first.
- **Contradictions.** Equalities that contradict each other, or bounds that
  leave no room, have no solution; the solve gets as close as it can.
- **Precision.** A rule without `interval: true` that multiplies a ratio
  by an amount holds before rounding but can miss by a few units after the
  ratio is rounded to its reporting decimals.

[Build a template from a DPM release](../guides/from-a-dpm-release.md#read-the-results) shows
how to explain each failing rule with dpm-xl.

## Rules that cannot be evaluated

dpm-xl reports some rules as `unsupported` or `error`, and the result's
`messages` give the reason:

- `time_shift` compares with an earlier period, and a single report has
  none (`unsupported`);
- a rule that uses a construct dpm-xl does not support.

A rule that does not parse, or that selects a table the template does not
have, is an error of the template.

They do not count towards the exit status.

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

## What would do better

Solving a module's linear equalities jointly, with a sparse least-squares
or mixed-integer solver, before repairing the rest would settle most cells
defined twice consistently, or prove that the rules contradict each other.
The template already carries what such a solver needs.
