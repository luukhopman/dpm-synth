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
rules: 9, passed: 8, failed: 0, unsupported: 1
rounds: 2 (failing rules per round: 3, 0)
history: unsupported: The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote big.zip (100018 facts)
```

The summary is that of the solved report; the scaled rows are not
evaluated. Table `S_03.00`, keyed by LEIs, got 100,000 rows. Table
`S_02.00.a` is keyed only by an enumerated property, so it keeps its two
solved rows. On a laptop, a
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
50018 {'c0010': 'SYNTHERI000004999908'}
```

## New keys

- A typed key, such as an LEI column, gets identifiers made of `SYNTH`, the
  first three letters and digits of the key code (padded with `X`), a
  10-digit row number and two ISO 17442 check digits, so they are unique,
  pass LEI validation and are visibly fictional. A table can have up to
  9,999,999,999 rows.
- An integer key counts the rows from 1; a date key counts back from the
  reference date, so a table whose typed keys are all dates has at most one
  row per day back to 1900-01-01.
- An enumerated key keeps the value of the solved row that the scaled row
  repeats, so the scaled rows have the same mix of items as the solved
  ones. When every key of a table is enumerated, the table keeps its solved
  rows; generate with more `--open-rows` to have more item combinations.
- Closed tables are written as generated.

## Which rules still hold

Row-wise rules, such as "amount at most the exposure" within one row, a
`match` on the key, or a rule on the rows with one enumerated key value
(`[where CT = [eba_CT:x1]]`), hold on every scaled row, because each row
repeats a solved one with its enumerated key values. Rules that add up an open table, such as "the sum over all
counterparties equals the total in another table", are not re-solved and
will fail: the totals are those of the solved rows. Use the scaled package
to test volume, and the unscaled package to test validation results.

The package is the same as `dpmxbrl.write_xbrl_csv` would write: the same
report package and metadata files, the root folder named as the ZIP file,
and the same CSV layout.
