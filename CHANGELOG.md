# Changelog

All notable changes to this project are documented here. The project follows
[semantic versioning](https://semver.org).

## 1.1.0 - 2026-10-31

### Breaking

- rules end with dpm-xl's statuses; `GenerationResult.statuses`,
  `messages` and `summary` replace `passed`, `rules`, `not_evaluated` and
  `not_applicable`, and the text summary uses the same words.
- `generate --json` has `schema_version` 2, with `tool`,
  `version`, counts under `summary` and a `results` entry per rule.
- Values generated for a seed change: rounding, filing indicators,
  currencies, typed keys, realism options and the joint solve all affect
  them.
- The exit status follows the rules' severity: failing warnings exit 0
  unless `--fail-on warning`, and a rule of severity `error` that fails or
  is an `error` (dpm-xl cannot evaluate it) exits 1; `unsupported` rules
  never change it. 1.0 exited 1 on any failing rule and ignored rules it
  could not evaluate.
- `load_template` rejects a rule that does not parse or selects a table
  the template does not have, which 1.0 reported as not evaluated.
- `load_template` rejects an enumerated cell or open key without `items`;
  1.0 gave such a cell the invalid value `eba_qx:qx0`.
- `load_template` rejects decimals below the minimums of EBA filing rule
  2.18, which 1.0 accepted: `p` below 4, `i` other than 0 and `m` below -6.

### Changed

- A comparison with `max` or `min` of several values is repaired by moving
  the argument that gives the value, instead of the other cells only.
- A repair no longer writes a value into a cell that an `isnull` repair
  emptied; the other cells of the comparison take the difference, so the
  `isnull` rule keeps holding.
- The joint solve of linear rules includes the comparison of the `if`
  branch whose condition holds, so a total that one rule sums and another
  compares under a condition is solved with both. This changes the values
  generated for every seed.
- The text summary gives the reason for an `error` or `unsupported` rule
  as `rule CODE (status): reason`, so a rule code cannot read as a heading.
- Typed open keys take the same identifiers in every table keyed by the
  same property, so rules that join such tables find matching rows.
- A rule on a template in `filing_indicators` without tables is
  `not_applicable`.
- A rule may select an abstract table, such as `C_02.00`, by the filing
  indicator of the tables it was split into; it reads their cells together.
- `load_template` warns about a template without `entry_point`, and
  `dpm-synth generate` prints the warning: the package is written without
  `extends`, which xBRL-CSV processors reject.
- Typed open keys take an optional `data_type`: `i` keys get integers and
  `d` keys get dates instead of LEI-shaped identifiers.
- `es` cells are text that may be empty, as the DPM defines them, and need
  no `items`; they get non-empty text, as EBA filing rule 2.19 requires.
- `t` cells are always `true`.
- `dt` cells get dates, `u` cells URIs and `o` cells whole numbers; `o`
  and `dt` keys count like `i` and `d` keys.
- `load_template` reads a dpm-xl module file (`"format": "dpm-module/1"`),
  so the file `dpm-xl export-module` writes serves both tools.
- A template's optional `filing_indicators` lists every template of the
  module, each once ignoring case; those without tables are reported with
  a negative filing indicator.
- The reporting currency is the template's `currency`, or `--currency`
  (`currency=` in `generate`), instead of always EUR, and `baseCurrency`
  is left out when no monetary fact is reported.
- Cells with `"unit": true` are reported in their currency of
  denomination, in a `unit` column that follows the row's `CUS` or `CUA`
  key.
- Values are rounded half to even, as EBA filing rule 2.18 requires,
  instead of half up; a value that ends in exactly 5 past the reporting
  decimals can change.
- Reports with a reference date before 2022-12-31, or for a module whose
  code has `_con` or `_ind`, identify the entity by its bare LEI in the LEI
  scheme, as EBA filing rule 3.6 requires.
- Rules take an optional `severity`, `error` (the default) or `warning`,
  shown in the output.
- Rules with `"active": false` are neither repaired nor evaluated, and are
  reported as `skipped`.
- `generate` solves the linear rules jointly before the repair loop, and
  once more if rules still fail, keeping the pass with fewer failing
  errors, then warnings: on EBA DPM 4.3 COREP_OF 0 to 2 rules fail
  instead of about 52. Repairs also share a difference among cells that
  cannot take it alone, and move dates compared with each other. This
  changes the values generated for every seed.
- Monetary amounts start spread over three orders of magnitude for an
  institution size, `size` (`--size small|medium|large`, default
  `medium`: 100,000 to 100,000,000), instead of 1,000 to 1,000,000.
- Booleans start as `true` or `false`, dates in the ten years up to the
  reference date, and text cells as `Synthetic text` with a number instead
  of an LEI-shaped identifier.
- `fill` (`--fill RATIO`) leaves a share of the cells out, for sparse
  reports that still satisfy the rules.
- The starting values above change the values generated for every seed.
- The documentation site has sitemap dates, social preview tags and a 404
  page that links home.

### Known issues

- FINREP9 reports leave 45 to 65 of its rules failing: its linear rules
  can all hold together, but the dependency-free solver does not settle
  them before repairs of other rules undo them. See the limits page.

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
