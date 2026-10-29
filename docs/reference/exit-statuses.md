---
description: The exit statuses of dpm-synth generate - 0 all evaluable rules pass, 1 some fail, 2 usage error, 3 unreadable or invalid input - the same as dpm-xl and dpm-xbrl.
---

# Exit statuses

| Status | Meaning | Package written |
| --- | --- | --- |
| 0 | Every rule that could be evaluated passes, or only rules below `--fail-on` fail. Rules that are `unsupported` (such as `time_shift`), `error`, `not_applicable` or `skipped` do not count. | yes |
| 1 | Some rules at or above `--fail-on` still fail; the summary names them. By default only rules of severity `error` count; `--fail-on warning` counts warnings too. | yes |
| 2 | Usage error: an unknown option, a missing argument, or a bad option value, such as `--open-rows 0`, `--open-rows 5000`, a reference date not written as `YYYY-MM-DD` or an output not ending in `.zip`. argparse prints the usage and the error. | no |
| 3 | The template cannot be read, is not JSON or is not a valid [template](template-format.md); or the package cannot be written. One line `error: ...` on standard error. | no |

The statuses match the sibling commands: `dpm-xl eval` and `dpm-xbrl`
also exit with 0 when nothing is wrong, 1 when the input was read and has
problems (a failing rule, or a filing rule broken at or above `--fail-on`),
2 for a usage error and 3 for unreadable or invalid input. With
`--scale-rows`, the status is that of the unscaled report, since the scaled
rows are not evaluated.

A rule that cannot be satisfied makes status 1, not a failure of the run:
the package is still useful for testing:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7 --max-rounds 1
rules: 9, passed: 5, failed: 3, unsupported: 1
rounds: 1 (failing rules per round: 5)
still failing: rows, open, open-total
history: unsupported: The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sample.zip (20 facts)
$ echo $?
1
```

To accept a known set of failing rules in CI, compare the rules whose
`status` is `failed` in the `results` of the
[JSON output](json-output.md) with the list you expect, instead of relying
on the status.
