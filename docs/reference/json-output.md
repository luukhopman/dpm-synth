---
description: The JSON layout printed by dpm-synth generate --json, field by field, with schema_version and its compatibility promise.
---

# JSON output

`dpm-synth generate --json` prints one JSON object (UTF-8, two-space
indentation) instead of the text summary. The package is written and the
[exit status](exit-statuses.md) is the same as without `--json`.

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7 --json
{
  "schema_version": 1,
  "output": "sample.zip",
  "release": "1.0",
  "module": "SAMPLE",
  "seed": 7,
  "rules": 9,
  "passed": 8,
  "failed": [],
  "not_evaluated": {
    "history": "The rule compares with the previous reporting period (time_shift), which a single report does not include"
  },
  "not_applicable": [],
  "rounds": 5,
  "history": [
    5,
    3,
    1,
    1,
    0
  ],
  "repairs": 16,
  "facts": 20
}
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Version of this layout, currently `1`. |
| `output` | string | The package written, as given to `--output`. |
| `release` | string | The template's `release`. |
| `module` | string | The template's `module`. |
| `seed` | integer | The random seed. |
| `rules` | integer | Rules in the template. |
| `passed` | integer | Rules that pass on the written values. |
| `failed` | array of strings | Codes of the rules that still fail, in the order they were last evaluated. |
| `not_evaluated` | object | Rule code to the reason dpm-xl could not evaluate the rule, in template order. |
| `not_applicable` | array of strings | Codes of the rules whose precondition is false or that select no cell. |
| `rounds` | integer | Evaluate-and-repair rounds run. |
| `history` | array of integers | Failing rules at the start of each round. |
| `repairs` | integer | Failing records repaired over all rounds. |
| `facts` | integer | Facts written; with `--scale-rows`, those of the scaled package. |

`passed`, the lengths of `failed`, `not_evaluated` and `not_applicable` add
up to `rules`. The fields are those of
[`GenerationResult`][dpmsynth.GenerationResult].

## Compatibility

`schema_version` changes only with a new major version of dpm-synth. Within
a major version, fields are not removed or renamed and their types do not
change; new fields may be added, so ignore fields you do not know. The
`not_evaluated` reasons come from dpm-xl and may be reworded. See
[stability and versioning](../project/stability.md).
