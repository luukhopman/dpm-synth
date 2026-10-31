---
description: The exit statuses of dpm-synth generate - 0 no rule at or above --fail-on fails or is an error, 1 one does, 2 usage error, 3 unreadable or invalid template or unwritable package - as in dpm-xl and dpm-xbrl.
---

# Exit statuses

`dpm-synth generate` exits with status 1 when, for some rule whose
severity is at least `--fail-on` (default `error`, so only rules of
severity `error` count):

- its status is `failed`, or
- its status is `error`: dpm-xl cannot evaluate it, such as `+` on a text
  cell.

Statuses `unsupported` (such as `time_shift`), `not_applicable` and
`skipped` never change the exit status. `--fail-on warning` makes rules of
severity `warning` count too.

| Status | Meaning | Package written |
| --- | --- | --- |
| 0 | No rule meets the conditions above. | yes |
| 1 | A rule meets them; the summary names it. | yes |
| 2 | Usage error: an unknown option, a missing argument, or a bad option value, such as `--open-rows 0`, `--open-rows 5000`, a reference date not written as `YYYY-MM-DD` or an output not ending in `.zip`. argparse prints the usage and the error. | no |
| 3 | The template file cannot be read, is not JSON or does not follow the [template format](template-format.md); or the package cannot be written. One line `error: ...` on standard error. | no |

With `--scale-rows`, the status is that of the unscaled report, since the
scaled rows are not evaluated. Statuses 0, 2 and 3 mean the same in
`dpm-xl` and `dpm-xbrl`, and their `--fail-on` also defaults to `error`;
see the [toolkit page](../toolkit.md#what-the-packages-share).

Status 1 does not mean dpm-synth crashed: the package is written and is
still useful for testing:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7 --max-rounds 0
rules: 9, passed: 1, failed: 7, unsupported: 1
rounds: 0 (failing rules per round: -)
still failing: rows, columns, ratio, item, open, open-total, lei
rule prior-period (unsupported): The rule compares with the previous reporting period (time_shift), which a single report does not include
wrote sample.zip (20 facts)
$ echo $?
1
```

To accept a known set of failing rules in CI, compare the rules whose
`status` is `failed` in the `results` of the
[JSON output](json-output.md) with the list you expect, instead of relying
on the status.
