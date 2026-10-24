---
description: The dpm-synth command - generate, every option, the text output, and the exit statuses.
---

# CLI

Installing dpm-synth installs the `dpm-synth` command, with one subcommand,
`generate`. `uvx dpm-synth` runs it without installing.

```console
$ dpm-synth --help
usage: dpm-synth [-h] [--version] {generate} ...

Generate synthetic EBA xBRL-CSV reports that satisfy a module's
DPM-XL validation rules.

positional arguments:
  {generate}
    generate  write an xBRL-CSV report package for a template

options:
  -h, --help  show this help message and exit
  --version   show program's version number and exit

examples:
  dpm-synth generate template.json -o report.zip
  dpm-synth generate template.json -o report.zip --seed 7 --open-rows 3
  dpm-synth generate template.json -o report.zip --json
  dpm-synth generate template.json -o big.zip --scale-rows 1000000

exit statuses: 0 every evaluable rule passes, 1 some rules still fail (the
package is written), 2 usage error, 3 unreadable or invalid template, or the
package cannot be written.

The template format: https://luukhopman.github.io/dpm-synth/reference/template-format/
```

## `dpm-synth generate`

```console
$ dpm-synth generate --help
usage: dpm-synth generate [-h] -o ZIP [--seed N] [--open-rows N]
                          [--max-rounds N] [--scale-rows N]
                          [--reference-date YYYY-MM-DD] [--entity LEI]
                          [--level {CON,IND}] [--json]
                          template

Generate values for every cell of a template, repair them until the rules
pass, and write an xBRL-CSV report package.

positional arguments:
  template              dpm-synth-template/1 JSON file

options:
  -h, --help            show this help message and exit
  -o, --output ZIP      report package to write (.zip)
  --seed N              random seed (default 0)
  --open-rows N         key rows per open table, at most 1000 (default 2)
  --max-rounds N        most evaluate-and-repair rounds (default 40)
  --scale-rows N        after solving, write every open table with N key rows
                        (load testing; rules over open-table totals will fail)
  --reference-date YYYY-MM-DD
                        reference date (default: the template's, else
                        2026-12-31)
  --entity LEI          LEI of the reporting entity (default
                        SYNTHETICDPMXL000002)
  --level {CON,IND}     reporting level, the entity suffix (default CON)
  --json                print a JSON summary
```

`generate` loads the [template](template-format.md), runs
[`generate`][dpmsynth.generate] and writes the report with
`dpmxbrl.write_xbrl_csv`, or with
[`write_scaled_package`][dpmsynth.write_scaled_package] for
`--scale-rows`. It prints a summary:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7
rules: 9, passed: 8, failed: 0, not evaluated: 1, not applicable: 0
rounds: 5 (failing rules per round: 5, 3, 1, 1, 0)
wrote sample.zip (20 facts)
```

- `rules` counts the template's rules; `passed`, `failed`, `not evaluated`
  (dpm-xl could not evaluate the rule, such as a `time_shift`) and
  `not applicable` (its precondition is false, or it selects no cell) add
  up to it.
- `rounds` lists the failing rules at the start of each round.
- When rules still fail, a line `still failing: ...` names up to 20 of them.
- `wrote` names the package and the facts in it.

| Option | Effect |
| --- | --- |
| `-o`, `--output ZIP` | The package to write; required, and must end in `.zip`. Its name without `.zip` names the package's root folder. An existing file is replaced. |
| `--seed N` | Random seed, any whole number. The same template, seed, options and versions give the same package; see [reproduce a report](../guides/reproducible-seeds.md). |
| `--open-rows N` | Key rows per open table while solving, from 1 to 1,000 ([`MAX_OPEN_ROWS`][dpmsynth.MAX_OPEN_ROWS]). A table whose keys are all enumerated gets at most as many rows as its item lists repeat after. |
| `--max-rounds N` | Most evaluate-and-repair rounds, 0 or more; 0 writes the starting values. |
| `--scale-rows N` | Write every open table with `N` key rows, from 1 to 9,999,999,999, by repeating the solved rows under new keys; see [load-test with scaled packages](../guides/load-testing.md). The summary and the exit status are those of the unscaled report. |
| `--reference-date YYYY-MM-DD` | Overrides the template's reference date; exactly `YYYY-MM-DD`, as in the template. |
| `--entity LEI` | The reporting entity, letters and digits (`.`, `_` and `-` allowed). The entity identifier is `<LEI>.<level>` in the reporting-subject scheme. |
| `--level CON\|IND` | The reporting level, consolidated or individual. |
| `--json` | Print the summary as JSON instead; see [JSON output](json-output.md). |
| `--version` | Print the version and exit. |

## Errors

Errors are one line on standard error, starting with `error:`, and never a
traceback:

```console
$ dpm-synth generate missing.json -o report.zip
error: missing.json: cannot read: No such file or directory
$ echo $?
3
$ dpm-synth generate minimal.json -o report.csv
usage: dpm-synth generate [-h] -o ZIP [--seed N] [--open-rows N]
                          [--max-rounds N] [--scale-rows N]
                          [--reference-date YYYY-MM-DD] [--entity LEI]
                          [--level {CON,IND}] [--json]
                          template
dpm-synth generate: error: argument -o/--output: expected a .zip file, got 'report.csv'
$ echo $?
2
```

See [exit statuses](exit-statuses.md) for every status.
