---
description: Write report packages with millions of open-table rows for load and performance tests, from the command line or with write_scaled_package, and know which rules still hold.
---

# Load-test with scaled packages

Loaders and validators need to be tested on reports far larger than any
that the repair loop could solve row by row. A scaled package keeps the
solved values and multiplies the open tables: every open table gets as many
key rows as you ask for, whose values repeat the solved rows under new keys.
Tables are streamed into the ZIP file, so memory stays flat however many
rows you write.

## From the command line

```console
$ dpm-synth generate sample.json -o big.zip --seed 7 --scale-rows 100000
rules: 9, passed: 8, failed: 0, not evaluated: 1, not applicable: 0
rounds: 5 (failing rules per round: 5, 3, 1, 1, 0)
wrote big.zip (100018 facts)
```

The summary is that of the solved report; the scaled rows are not
evaluated. Table `S_03.00`, keyed by LEIs, got 100,000 rows. Table
`S_02.00.a` is keyed by an enumerated property with two allowed items, so
it cannot have more than two distinct rows and keeps two. On a laptop, a
million rows take about six seconds and 35 MB of memory.

## From Python

[`write_scaled_package`][dpmsynth.write_scaled_package] takes one row count
for every open table, or a mapping of table code to rows; tables left out
of the mapping keep their generated rows:

```python
from dpmsynth import generate, load_template, write_scaled_package

result = generate(load_template("sample.json"), seed=7)
written = write_scaled_package(result.data, "big.zip", rows={"S_03.00": 50_000})
print(written)
```

```text
{'S_01.00': 14, 'S_02.00.a': 4, 'S_03.00': 50000}
```

It returns the fact rows written per table. Read the package back with
dpm-xbrl; for millions of facts its `frames` extra reads them into polars
frames in seconds:

```python
from dpmxbrl import read_report

report = read_report("big.zip")
print(len(report.facts), report.facts[-1].keys)
```

```text
50018 {'c0010': 'ERIXXX00000004999989'}
```

## New keys

- A typed key, such as an LEI column, gets identifiers made of the first
  six letters and digits of the key code, padded with `X`, a 12-digit row
  number and two ISO 17442 check digits, so they are unique and pass LEI
  validation.
- An enumerated key cycles through its allowed items. When every key of a
  table is enumerated, the table gets at most as many rows as the item
  combinations.
- Closed tables are written as generated.

## Which rules still hold

Row-wise rules, such as "amount at most the exposure" within one row or a
`match` on the key, hold on every scaled row, because each row repeats a
solved one. Rules that add up an open table, such as "the sum over all
counterparties equals the total in another table", are not re-solved and
will fail: the totals are those of the solved rows. Use the scaled package
to test volume, and the unscaled package to test validation results.

The package is the same as `dpmxbrl.write_xbrl_csv` would write: the same
report package and metadata files, the root folder named as the ZIP file,
and the same CSV layout.
