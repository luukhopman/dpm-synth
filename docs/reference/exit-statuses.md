---
description: The exit statuses of dpm-synth generate - 0 all evaluable rules pass, 1 some fail, 2 usage error, 3 unreadable or invalid input - and how to use them in scripts and CI.
---

# Exit statuses

| Status | Meaning | Package written |
| --- | --- | --- |
| 0 | Every rule that could be evaluated passes. Rules that are not evaluated (such as `time_shift`) or not applicable do not count. | yes |
| 1 | Some rules still fail; the summary names them. | yes |
| 2 | Usage error: an unknown option, a missing argument, or a bad option value, such as `--open-rows 0`, `--open-rows 5000`, a reference date not written as `YYYY-MM-DD` or an output not ending in `.zip`. argparse prints the usage and the error. | no |
| 3 | The template cannot be read, is not JSON or is not a valid [template](template-format.md); or the package cannot be written. One line `error: ...` on standard error. | no |

The statuses match the sibling commands: 2 is always a usage error, and
neither tool prints a traceback for bad input. With `--scale-rows`, the
status is that of the unscaled report, since the scaled rows are not
evaluated.

A rule that cannot be satisfied makes status 1, not a failure of the run:
the package is still useful for testing. To accept a known set of failing
rules in CI, compare the `failed` list of the
[JSON output](json-output.md) with the list you expect instead of relying
on the status:

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7 --json --max-rounds 1
{
  "schema_version": 1,
  "output": "sample.zip",
  "release": "1.0",
  "module": "SAMPLE",
  "seed": 7,
  "rules": 9,
  "passed": 5,
  "failed": [
    "open",
    "open-total",
    "rows"
  ],
  "not_evaluated": {
    "history": "The rule compares with the previous reporting period (time_shift), which a single report does not include"
  },
  "not_applicable": [],
  "rounds": 1,
  "history": [
    5
  ],
  "repairs": 10,
  "facts": 20
}
$ echo $?
1
```
