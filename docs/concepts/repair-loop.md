---
description: How dpm-synth satisfies DPM-XL rules - starting values by data type, sign bounds, a joint solve of the linear rules, linearized repairs, rounds, stopping and rounding.
---

# The evaluate-and-repair loop

[`generate`][dpmsynth.generate] starts from plausible values and first
solves the module's linear rules together: sums, differences, constant
factors and `abs`, as equalities and inequalities. It then evaluates every
rule with [dpm-xl] and changes one cell for each failing record so that the
failing comparison holds, which covers the rest (products of cells, `max`,
`if`, `isnull`, items, dates); then it evaluates again.

## 1. Starting values

Every cell gets a value for its [data type](../reference/template-format.md#data-types),
drawn from the seed: monetary amounts in thousands, spread over three
orders of magnitude for the institution size (`size`), ratios between 0
and 1, small integers, the first allowed item of an enumerated cell,
`true` or `false`, a date in the ten years up to the reference date, and
`Synthetic text` with a number for text. With `fill` below 1, a share of
the cells starts empty instead: an empty cell counts as 0 in rules with
`default: 0`, the joint solve leaves it empty, and a repair gives it a
value only when a rule needs one, so the report is sparse but still
satisfies the rules. Every open table gets `open_rows` key
rows: allowed items for enumerated keys; integers, dates or LEI-shaped
identifiers for typed keys, by their data type.

Every generated LEI-shaped identifier starts with `SYNTH`
([`LEI_PREFIX`][dpmsynth.LEI_PREFIX]), followed by 13 random letters and
digits and two valid ISO 17442 check digits: it passes LEI validation, but
is visibly fictional and cannot coincide with a real entity's LEI. The
reporting entity is the fictional `SYNTHETICDPMXL000002` unless you pass
another. With `max_rounds=0` you see the starting values unrepaired:

```python
from dpmsynth import generate, load_template

template = load_template("minimal.json")
start = generate(template, seed=7, max_rounds=0)
print([fact.value for fact in start.report.facts], start.failed)
```

```text
['936000', '283000', '8970000'] ['v1']
```

The total in row 0010 is not the sum of rows 0020 and 0030, so rule `v1`
fails. Without `max_rounds=0`, the joint solve of the linear rules sets
the total to 9,253,000 before the first round, which finds no failing rule.

## 2. Analysis

Before the first round, the rules are read once:

- **Bounds.** A rule that compares cells with a constant, such as
  `{(r0020, r0030)} >= 0` or `{c0020} <= 0`, becomes a bound on each of
  those cells, and so does such a comparison joined to the rest of a rule
  by `and`. Starting values outside a bound change sign, or take the
  bound; repairs never move a cell outside its bounds. A strict bound
  (`> 0`) is one reporting step past the constant, such as 1 for an amount
  or 0.0001 for a percentage.
- **Definitions.** A rule whose `=` has a single cell on one side, such as
  `{r0010} = {r0020} + {r0030}`, *defines* that cell. Repairs of other rules
  prefer to change cells that no other rule defines, so a total that one
  rule owns is not pulled around by rules that merely use it.
- **Order.** Rules are sorted so that a rule defining a component runs
  before the rule that sums the components: totals are then settled from
  components that no longer change in that round.
- **Linear rules.** Each record of a comparison whose sides are sums of
  cells times constants, such as `{c0010} * 12.5 = {c0020}` or
  `abs({r0010}) >= abs({r0020}) + abs({r0030})`, becomes a linear
  constraint. An `abs` keeps the sign its operand starts with, and an
  `if` contributes the branch its condition picks at the start.

## 3. Solving the linear rules

A total that is both the sum of its row and the sum of its column, or an
amount that is a sum and 12.5 times a requirement with parts of its own,
is defined twice: repairs of one cell at a time move it back and forth. So
the linear constraints are solved together before the first round:

1. Gaussian elimination solves each equality for one of its cells, so the
   equalities hold whatever the other cells are.
2. The inequalities and the bounds, rewritten in the other cells, are met
   by projections: a violated one moves its cells as little as possible
   together, within their bounds, until all hold or a limit of steps is
   reached.
3. Values are rounded to their reporting decimals, and the rounds repair
   what rounding and the other rules still need.

When rules still fail after the rounds, the linear rules are solved once
more from the repaired values, and the rounds run again. The pass that
ends with fewer failing rules of severity `error` is kept, and with as
many, the one with fewer failing warnings; the first pass wins a tie.

## 4. Repairs

Each failing record of a rule is traced to the comparison that fails, using
the evaluation trace that dpm-xl keeps. Its repair depends on the
construct:

| Construct | Repair |
| --- | --- |
| `a = b`, `a <= b`, `a > b`, ... on numbers | Expand `a - b` into terms `coefficient × cell`: sums, differences, unary minus, constants, `sum(...)`, `abs` (at its current sign), `max` and `min` of several values (the argument that gives the value), a product of two cells (each at the other's current value) and division by a constant or cell. One cell absorbs the whole difference, the first that no other rule defines and whose new value respects its bounds; when none can, the cells move in turn as far as their bounds allow. Strict comparisons are met by one reporting step. |
| `a < b`, `a >= b`, ... on dates | Move the earlier side: `a < b` sets `a` to the day before `b`. |
| `a = b` on items, text or dates | Copy the known side into the cells of the other. |
| `and`, `or`, `not` | Repair both sides of `and`; the first side of `or` that can be changed; `not` repairs its operand towards the opposite. |
| `if c then a else b endif` | Repair the branch that the condition selects. |
| `isnull(x)` | Clear `x`; `not isnull(x)` gives a cleared cell a starting value again. Other repairs leave a cleared cell empty. |
| `x in {…}` or `x in s` | Set `x` to the first member of the set that fits its cell: a number for a numeric cell, an item for an enumerated one. Any set works: a literal, a `set-*` parameter, `union(...)`, or a selection of cells. |
| `match(x, pattern)` | For the LEI pattern `[A-Z0-9]{18}[0-9]{2}`, a checksum-valid LEI-shaped identifier starting with `SYNTH`; for `dd/mm/yyyy`, the reference date. |

Numbers never go into text or enumerated cells and nothing else goes into a
numeric cell. A repair that would need a number beyond 10^15, as a ratio
dividing by an almost-zero cell can, is not made.

## 5. Rounds and stopping

A round evaluates every rule and repairs every failing record. The loop
stops when no rule fails, when a round changes nothing, after
`max_rounds` (default 40), or when the failing count has not reached a new
low for six rounds: rules that keep undoing each other's repairs. The
failing count per round is `GenerationResult.history`:

```python
result = generate(load_template("sample.json"), seed=7)
print(result.history, result.rounds, result.repairs)
```

```text
[3, 0] 2 4
```

## 6. Rounding and the final evaluation

Repairs work on values with eight decimals. At the end, every number is
rounded to its reporting decimals (`m` 0, `p` 4, `i` 0, `r` 2 unless the
template says otherwise), with ties to the even digit as EBA filing rule
2.18 requires, and every rule is evaluated once more on the
rounded values. That final evaluation gives each rule's status in
`statuses`.

The generated values are evaluated as the written package will be: each
number carries its reporting decimals, which dpm-xl turns into a tolerance
for rules with `interval: true`. A ratio rounded to four decimals is judged
as a validator would judge the reported ratio, so a rule that passes here
passes on the package; the
[validation guide](../guides/validate-output.md) checks this.

## Why not a complete solver

The joint solve is linear: it keeps the signs inside `abs` and the branch
of each `if`, and leaves products of cells and `max` to the rounds. A
mixed-integer solver could also choose those, or prove that rules
contradict each other, but needs a dependency and much longer for a module
of thousands of rules.
[Limits of the loop](limits.md) shows what remains.
