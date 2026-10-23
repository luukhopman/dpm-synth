# dpm-synth

Generate synthetic EBA xBRL-CSV report packages that satisfy a module's DPM-XL
validation rules. Useful for exercising downstream pipelines, loaders and
validators with realistic, internally consistent submissions for any module.

```bash
# 1. Describe a module from a prepared a DPM tool release
dpm-export 4.3 COREP_OF -o corep_of.json

# 2. Generate a report package
dpm-synth generate corep_of.json -o corep_of.zip --seed 7
# rules: 1205, passed: 982, failed: 61
# rounds: 16 (failing rules per round: [703, 200, 133, …])
```

Depends on [`dpm-xl`](../dpm-xl) (evaluation) and [`dpm-xbrl`](../dpm-xbrl)
(writing the package). The same seed and template always give the same report.

## How it works

`dpmsynth.generate` is an evaluate-and-repair loop, not a complete solver:

1. **Initial values** by data type: monetary amounts in thousands, ratios in
   `(0, 1)`, integers, the first allowed item for enumerations, the reference
   date, LEI-shaped text. Open tables get `--open-rows` key rows (allowed items,
   or LEI-shaped identifiers for typed keys).
2. **Analysis.** Single-cell sign rules (`{x} >= 0`, `{(c0020, c0030)} <= 0`)
   become per-cell bounds, and initial values are moved inside them. Every
   `=` rule with a single-cell side *defines* that cell; rules are ordered so
   that the definitions of components run before the totals that use them.
3. **Repair rounds.** Each failing record is traced to the first failing
   comparison. Its two sides are linearized into `coefficient × cell` terms
   (sums, differences, constants, `abs`, and products of two cells at their
   current values) and one cell absorbs the difference — preferably a cell no
   other rule defines, and never outside its bounds. `isnull`, `not isnull`,
   `in {…}` and `match` (LEI and `dd/mm/yyyy` patterns) are repaired directly.
4. The loop stops when nothing fails, nothing changes, or the failing count
   stops improving; values are then rounded to the reporting decimals
   (`m` 0, `p` 4, `i` 0, `r` 2 by default) and the rules are evaluated once more.

Generated facts carry the same decimals tolerance during evaluation that the
written package declares, so rounded ratios are judged as a validator would.

## Results and limits

On EBA DPM 4.3 COREP_OF (81 tables, 21,339 cells, 1,205 rules) the loop
satisfies 982 of the 1,043 rules that apply, in about 20 seconds; DPM
A DPM validator reports the same 61 failures for the written package.
The remainder are coupled systems that local repair cannot settle:

- a cell defined by two different rules (for example CET1 as a sum of
  components and as ratio × TREA, while the ratio also has a minimum);
- totals over open-table key rows that are also constrained per key;
- rules on tables outside the module, `time_shift` (needs a previous period)
  and regular expressions other than the two recognized shapes.

A complete approach would solve the linear equalities jointly (for example
with a sparse least-squares or MILP solver) before repairing the rest; the
template format already carries everything such a solver needs.

## Template format

`dpm-synth-template/1` JSON: `release`, `module`, `entry_point`,
`reference_date`, `decimals` (per data type), `tables[]` (`code`,
`filing_indicator`, `open_keys[]` with `code`, `column`, `items`, and
`cells[]` with `id`, `row`, `column`, `sheet`, `datapoint`, `data_type`,
`items`) and `rules[]` (`source`, `code`, `expression`, `precondition`). See
`src/dpmsynth/template.py` for the full description.

## CLI

```text
dpm-synth generate TEMPLATE -o REPORT.zip [--seed N] [--open-rows N]
    [--max-rounds N] [--reference-date YYYY-MM-DD] [--entity LEI]
    [--level CON|IND] [--json]
```

Exit status is 0 when every evaluable rule passes, 1 when some still fail
(the package is written either way), and 2 for an invalid template.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run ty check
```
