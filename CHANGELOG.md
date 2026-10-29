# Changelog

All notable changes to this project are documented here. The project follows
[semantic versioning](https://semver.org).

## Unreleased

- `load_template` rejects a rule that does not parse or selects a table
  the template does not have, instead of reporting it as not evaluated.
- Typed open keys take an optional `data_type`: `i` keys get integers and
  `d` keys get dates instead of LEI-shaped identifiers.
- Enumeration-set (`es`) cells get an allowed item instead of an
  LEI-shaped identifier.
- `load_template` rejects an enumerated cell without `items`, which used to
  get the invalid value `eba_qx:qx0`.
- A template's optional `filing_indicators` lists every template of the
  module; those without tables are reported with a negative filing
  indicator.
- The reporting currency is the template's `currency`, or `--currency`
  (`currency=` in `generate`), instead of always EUR, and `baseCurrency`
  is left out when no monetary fact is reported.
- Cells with `"unit": true` are reported in their currency of
  denomination, in a `unit` column that follows the row's `CUS` or `CUA`
  key.
- Values are rounded half to even, as EBA filing rule 2.18 requires,
  instead of half up; a value that ends in exactly 5 past the reporting
  decimals can change.
- `load_template` rejects decimals below the minimums of EBA filing rule
  2.18: `p` below 4, `i` other than 0 and `m` below -6.
- Reports with a reference date before 2022-12-31, or for a module whose
  code has `_con` or `_ind`, identify the entity by its bare LEI in the LEI
  scheme, as EBA filing rule 3.6 requires.

## 1.0.0 - 2026-10-24

The first public release.

### Generating reports

- `generate` fills every cell of a `dpm-synth-template/1` template with a
  value for its data type and repairs the values, round by round, until
  the module's DPM-XL rules pass. Repairs cover sums, differences, products
  of two cells, `abs`, sign rules (also inside `and`), `isnull`, `in` with
  any set operand, `match` for LEIs and `dd/mm/yyyy` dates, `and`, `or`,
  `not` and `if`. Values are rounded to the reporting decimals and every
  rule is evaluated once more.
- `GenerationResult` holds the report, ready for `dpmxbrl.write_xbrl_csv`,
  the generated values (`data`, a dpm-xl data provider) and every rule
  counted once: `passed`, `failed`, `not_evaluated` with the reason, and
  `not_applicable`.
- Reports are reproducible: the same template, seed, options and versions
  give the same bytes.
- Reports are synthetic: the entity is the fictional LEI
  `SYNTHETICDPMXL000002` (`DEFAULT_ENTITY`), and every generated LEI-shaped
  identifier starts with `SYNTH` (`LEI_PREFIX`) and has valid ISO 17442
  check digits, so none can be a real entity's LEI.
- `build_report` turns changed values into a report again.
- `write_scaled_package` streams open tables with millions of rows into a
  package laid out as dpm-xbrl writes it, for load tests; scaled rows keep
  the enumerated key values of the solved rows they repeat.

### Templates

- `load_template` reads and validates a template field by field, and
  raises `TemplateError`, naming the field such as
  `tables[2].cells[0].datapoint`, for an unreadable, non-JSON or invalid
  template, including repeated table, cell or rule codes and text that
  cannot be written as UTF-8. Unknown fields are ignored.

### Command line

- `dpm-synth generate` with `--seed`, `--open-rows`, `--max-rounds`,
  `--scale-rows`, `--reference-date`, `--entity`, `--level` and `--json`
  (with `schema_version` 1), `--version`, and examples in `--help`.
- Exit statuses: 0 every evaluable rule passes, 1 some fail (the package is
  written), 2 usage error, 3 unreadable or invalid template, or a package
  that cannot be written.

### Project

- Depends on dpm-xl and dpm-xbrl 1.x, and uses only their public APIs.
- Python 3.11 to 3.15, tested in CI.
- A documentation site at https://luukhopman.github.io/dpm-synth/, with
  `llms.txt` and `llms-full.txt` for AI agents.
