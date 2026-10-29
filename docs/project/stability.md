---
description: dpm-synth's semantic versioning policy - what the public API is, what may change in minor releases, reproducibility, and the supported Python versions.
---

# Stability and versioning

dpm-synth follows [semantic versioning][semver]. A major version may break
the public API; minor and patch versions do not. The
[changelog](changelog.md) lists every change, with breaking changes marked.

## The public API

- The names in `dpmsynth.__all__`, documented in the
  [Python API](../reference/api.md), with the fields of `ModuleTemplate`,
  `TemplateTable`, `OpenKey`, `TemplateCell`, `TemplateRule` and
  `GenerationResult`, and the attributes of `SyntheticData` documented
  there.
- The `TemplateError` contract: every unreadable or invalid template raises
  `TemplateError`, a `ValueError`.
- The [`dpm-synth-template/1`](../reference/template-format.md) format. A
  change that a reader of version 1 cannot ignore gets a new format version;
  dpm-synth keeps reading version 1 for the rest of the major version.
- The CLI: its commands, options, [exit statuses](../reference/exit-statuses.md)
  and the [`--json` layout](../reference/json-output.md), versioned by
  `schema_version`.

Modules and names that start with an underscore are internal, as are names
not in `dpmsynth.__all__`; import public names from `dpmsynth`.
`dpmsynth.__version__` gives the installed version.

## What may change in a minor release

- New functions, parameters with defaults, fields, CLI options, JSON fields
  and repairs.
- **The values generated for a seed.** A better repair, or a fix in dpm-xl
  or dpm-xbrl, can change the values and which rules pass. The changelog
  notes it. Pin all three packages if a fixture must stay byte for byte the
  same; see [reproduce a report](../guides/reproducible-seeds.md).
- The wording of the text summary, error messages and the `messages` of
  rules that are `error` or `unsupported`.
- Performance characteristics.

## Python versions

dpm-synth supports Python 3.11 to 3.15. Support for a Python version is
dropped only in a minor release, after its end of life.

## Dependencies

dpm-synth depends on dpm-xl and dpm-xbrl, within one major version of
each (`>=1.0,<2`), and uses only their public APIs.
