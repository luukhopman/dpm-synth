---
description: The JSON layout printed by dpm-synth generate --json, field by field, with the rule statuses and schema_version.
---

# JSON output

`dpm-synth generate --json` prints one JSON object (UTF-8, two-space
indentation) instead of the text summary. The package is written and the
[exit status](exit-statuses.md) is the same as without `--json`. The layout
follows the conventions of the sibling tools, [dpm-xl] and [dpm-xbrl]: it
starts with `schema_version`, `tool` and `version`, and counts go under
`summary`.

```console
$ dpm-synth generate sample.json -o sample.zip --seed 7 --json
{
  "schema_version": 2,
  "tool": "dpm-synth",
  "version": "1.0.0",
  "summary": {
    "rules": 9,
    "passed": 8,
    "failed": 0,
    "not_applicable": 0,
    "error": 0,
    "unsupported": 1,
    "skipped": 0,
    "facts": 20
  },
  "output": "sample.zip",
  "release": "1.0",
  "module": "SAMPLE",
  "seed": 7,
  "rounds": 2,
  "history": [
    3,
    0
  ],
  "repairs": 4,
  "results": [
    {
      "rule": "rows",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "columns",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "sign",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "ratio",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "item",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "open",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "open-total",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "lei",
      "severity": "error",
      "status": "passed",
      "message": null
    },
    {
      "rule": "history",
      "severity": "error",
      "status": "unsupported",
      "message": "The rule compares with the previous reporting period (time_shift), which a single report does not include"
    }
  ]
}
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Version of this layout, currently `2`. |
| `tool` | string | Always `"dpm-synth"`. |
| `version` | string | The dpm-synth version. |
| `summary` | object | `rules`, the rules in the template; the number of rules with each [status](#rule-statuses), which add up to `rules`; and `facts`, the facts written (with `--scale-rows`, those of the scaled package). |
| `output` | string | The package written, as given to `--output`. |
| `release` | string | The template's `release`. |
| `module` | string | The template's `module`. |
| `seed` | integer | The random seed. |
| `rounds` | integer | Evaluate-and-repair rounds run. |
| `history` | array of integers | Failing rules at the start of each round. |
| `repairs` | integer | Failing records repaired over all rounds. |
| `results` | array of objects | Every rule, in template order: `rule`, its code; its `severity`, `error` or `warning`; its `status`; and `message`, why it is `error` or `unsupported`, else null. |

The fields are those of [`GenerationResult`][dpmsynth.GenerationResult]:
`summary` is its `summary`, and `results` its `statuses` and `messages`.

## Rule statuses

A rule's status is dpm-xl's, on the written values, or `skipped`:

| Status | Meaning |
| --- | --- |
| `passed` | The rule holds. |
| `failed` | The rule still fails. |
| `not_applicable` | The precondition is false, or the rule selects no cell. |
| `error` | dpm-xl cannot evaluate the rule. |
| `unsupported` | The rule uses something one report does not have, such as `time_shift`, which compares with the previous period. |
| `skipped` | The rule is inactive (`"active": false` in the template) and is not evaluated. |

The text summary prints the same words, with a space for the underscore.

## Compatibility

`schema_version` changes whenever the layout does: version 2 added `tool`,
`version`, `summary`, `results`, severities and `skipped`, and replaced the lists of failing, not
evaluated and not applicable rules. New fields may be added without a
change, so ignore fields you do not know. The messages come from dpm-xl and
may be reworded. See [stability and versioning](../project/stability.md).
