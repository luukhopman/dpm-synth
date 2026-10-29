---
description: How dpm-synth satisfies DPM-XL rules - starting values by data type, sign bounds, defining equalities and rule order, linearized repairs, rounds, stopping and rounding.
---

# The evaluate-and-repair loop

[`generate`][dpmsynth.generate] does not solve a module's rules as a system
of equations. It starts from plausible values, evaluates every rule with
[dpm-xl], and changes one cell for each failing record so that the failing
comparison holds; then it evaluates again. Most rules in EBA modules are
local (a total is the sum of its components, an amount is not negative), so
this converges in a few rounds for most of a module.

## 1. Starting values

Every cell gets a value for its [data type](../reference/template-format.md#data-types):
monetary amounts in thousands, ratios between 0 and 1, small integers, the
first allowed item of an enumerated cell, the reference date for dates and
an LEI-shaped identifier for text. Every open table gets `open_rows` key
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
['332000', '971000', '155000'] ['v1']
```

The total in row 0010 is not the sum of rows 0020 and 0030, so rule `v1`
fails. The first round repairs it by setting the total, the cell that `v1`
defines, to 1,126,000; the second round finds no failing rule.

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

## 3. Repairs

Each failing record of a rule is traced to the comparison that fails, using
the evaluation trace that dpm-xl keeps. Its repair depends on the
construct:

| Construct | Repair |
| --- | --- |
| `a = b`, `a <= b`, `a > b`, ... on numbers | Expand `a - b` into terms `coefficient × cell`: sums, differences, unary minus, constants, `sum(...)`, `abs` (at its current sign), a product of two cells (each at the other's current value) and division by a constant or cell. One cell absorbs the whole difference, the first that no other rule defines and whose new value respects its bounds. Strict comparisons are met by one reporting step. |
| `a = b` on items, text or dates | Copy the known side into the cells of the other. |
| `and`, `or`, `not` | Repair both sides of `and`; the first side of `or` that can be changed; `not` repairs its operand towards the opposite. |
| `if c then a else b endif` | Repair the branch that the condition selects. |
| `isnull(x)` | Clear `x`; `not isnull(x)` gives a cleared cell a starting value again. |
| `x in {…}` or `x in s` | Set `x` to the first member of the set that fits its cell: a number for a numeric cell, an item for an enumerated one. Any set works: a literal, a `set-*` parameter, `union(...)`, or a selection of cells. |
| `match(x, pattern)` | For the LEI pattern `[A-Z0-9]{18}[0-9]{2}`, a checksum-valid LEI-shaped identifier starting with `SYNTH`; for `dd/mm/yyyy`, the reference date. |

Numbers never go into text or enumerated cells and nothing else goes into a
numeric cell. A repair that would need a number beyond 10^15, as a ratio
dividing by an almost-zero cell can, is not made.

## 4. Rounds and stopping

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
[5, 3, 1, 1, 0] 5 16
```

## 5. Rounding and the final evaluation

Repairs work on values with eight decimals. At the end, every number is
rounded to its reporting decimals (`m` 0, `p` 4, `i` 0, `r` 2 unless the
template says otherwise), and every rule is evaluated once more on the
rounded values. That final evaluation is what `passed`, `failed`,
`not_evaluated` and `not_applicable` report.

The generated values are evaluated as the written package will be: each
number carries its reporting decimals, which dpm-xl turns into a tolerance
for rules with `interval: true`. A ratio rounded to four decimals is judged
as a validator would judge the reported ratio, so a rule that passes here
passes on the package; the
[validation guide](../guides/validate-output.md) checks this.

## Why not a solver

A complete approach would solve a module's linear equalities jointly, for
example with a sparse least-squares or a mixed-integer solver, and then
repair the rest. The repair loop needs no solver dependency, handles the
non-linear and non-numeric constructs uniformly, and satisfies most rules
of real modules in seconds. The template carries everything a solver would
need, so one can be added without changing the format.
[Limits of the loop](limits.md) shows what remains.
