# Changelog

All notable changes to this project are documented here. The project follows
[semantic versioning](https://semver.org).

## 1.0.0 - 2026-10-24

The first public release.

### Added

- `generate` fills every cell of a `dpm-synth-template/1` template and
  repairs the values, round by round, until the module's DPM-XL rules pass:
  sums, differences, products of two cells, `abs`, sign rules, `isnull`,
  `in`, `match` for LEIs and `dd/mm/yyyy` dates, `and`, `or`, `not` and
  `if`. Values are rounded to the reporting decimals and every rule is
  evaluated once more.
- `GenerationResult` with the report, the generated values (`data`, a
  dpm-xl provider) and every rule counted once: `passed`, `failed`,
  `not_evaluated` with the reason, and `not_applicable`.
- `write_scaled_package` streams open tables with millions of rows into a
  package laid out as dpm-xbrl writes it, for load tests.
- `load_template` validates templates field by field and raises
  `TemplateError` naming the field, such as `tables[2].cells[0].datapoint`,
  for unreadable, non-JSON or invalid templates.
- `dpm-synth generate` with `--seed`, `--open-rows`, `--max-rounds`,
  `--scale-rows`, `--reference-date`, `--entity`, `--level` and `--json`
  (with `schema_version` 1), `--version`, and examples in `--help`. Exit
  statuses: 0 every evaluable rule passes, 1 some fail (the package is
  written), 2 usage error, 3 unreadable or invalid template, or a package
  that cannot be written.
- `dpmsynth.__version__`, `DEFAULT_ENTITY` (the fictional LEI
  `SYNTHETICDPMXL000002`) and `DEFAULT_REFERENCE_DATE`.
- A documentation site at https://luukhopman.github.io/dpm-synth/, with
  `llms.txt` and `llms-full.txt` for AI agents.
- Python 3.11 to 3.15, tested in CI.

### Changed

- **Breaking:** depends on dpm-xl and dpm-xbrl 1.0 instead of 0.1, and uses
  only their public APIs.
- **Breaking:** `build_report(data)` and
  `write_scaled_package(data, target, rows=...)` take the entity,
  reporting level and reference date from the `SyntheticData` that
  `generate` returns. `GenerationResult.data` is always set. `lei` and
  `summarize` are no longer exported.
- An invalid template exits with status 3 instead of 2.

### Fixed

- `x in s` is repaired for any set operand, such as `{tT, r0010}`, a
  `set-*` parameter or `union(...)`, instead of failing on operands that
  are not set literals.
- Rules that do not parse, and rules whose precondition is false, are
  counted, as not evaluated and not applicable, instead of being left out
  of the totals.
- `{vReportingLevel}` is the reporting level asked for, not always `con`.
- Repairs no longer write numbers into text or enumerated cells, or text
  into numeric cells, nor numbers beyond 10^15.
- Strict sign rules and strict comparisons use one reporting step of the
  cell, so a percentage is no longer pushed a whole unit; starting values
  move fully inside bounds that are stricter than the sign.
- Items keep the prefix the template gives them, `-0` is written as `0`,
  generated LEIs have valid ISO 17442 check digits, and `dd/mm/yyyy`
  patterns get the reference date.
- Scaled packages declare the `rs` and `iso4217` namespaces, use the
  Report Packages 1.0 document type, name the root folder as the ZIP file
  and write `decimals*` parameters only for the data types used, so
  dpm-xbrl reads them without warnings.
