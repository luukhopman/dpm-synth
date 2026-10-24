# AGENTS.md

Instructions for coding agents working on this repository. For using
dpm-synth as a library, see `docs/agents.md`
(<https://luukhopman.github.io/dpm-synth/agents/>).

## What this is

dpm-synth generates synthetic EBA xBRL-CSV report packages that satisfy a
module's DPM-XL validation rules, from a `dpm-synth-template/1` JSON
template. Python 3.11+. It depends on two sibling packages: dpm-xl
(evaluates the rules) and dpm-xbrl (writes and reads packages). Import name
`dpmsynth`, distribution name `dpm-synth`, CLI `dpm-synth`.

## Layout

```text
src/dpmsynth/
  __init__.py      public API re-exports (__all__)
  template.py      template dataclasses, load_template, TemplateError
  generator.py     generate, the repair loop, SyntheticData, build_report
  scale.py         write_scaled_package for load tests
  cli.py           dpm-synth generate
  _version.py      __version__                            (internal)
tests/
  support.py       template builders and PackageProvider (reads a package)
  test_end_to_end.py  generate, write, read back with dpm-xbrl, evaluate
  test_docs.py     runs every docs example and docstring example
docs/              documentation site (Zensical), nav in zensical.toml
docs/samples/      sample templates; the docs and the tests use them
scripts/build_docs.py  strict site build plus llms.txt and llms-full.txt
```

## Commands

```text
uv sync                              # environment with test, lint and docs tools
uv run pytest                        # all tests, including docs examples
uv run ruff check
uv run ruff format --check           # also formats Python in Markdown
uv run ty check
uv run python scripts/build_docs.py  # strict docs build into site/
```

All of these must pass before a commit.

## Dependencies on dpm-xl and dpm-xbrl

- Use only names in the `__all__` of their modules, as their docs define:
  `dpmxl`, `dpmxl.ast` and the other documented modules; `dpmxbrl`. Never
  import their underscore modules or names.
- Until dpm-xl 1.0 and dpm-xbrl 1.0 are on PyPI, `[tool.uv.sources]` in
  `pyproject.toml` takes both from their GitHub `main` branches, so that CI
  can resolve them. The wheel's metadata carries only the plain
  requirements `dpm-xl>=1.0,<2` and `dpm-xbrl>=1.0,<2`; `uv build` never
  writes the sources into it.
- **Once both are published on PyPI**, delete the `[tool.uv.sources]`
  table (and the comment above it) and run `uv lock`, so the lock resolves
  them from PyPI. Do this before tagging a release.

## Conventions

- Google-style docstrings on every public name, with `Args`, `Returns`,
  `Raises` and, where it helps, an `Example` that runs as a doctest in a
  directory holding `docs/samples` (`tests/test_docs.py`).
- No new runtime dependencies beyond dpm-xl and dpm-xbrl. Docs tools go in
  the `docs` dependency group.
- Keep `__all__`, the docs and `CHANGELOG.md` in step with the code. A new
  public name needs an entry on `docs/reference/api.md`.
- Every behaviour has a test. A new sample template in `docs/samples` is
  picked up by `tests/test_end_to_end.py`, which writes it, reads it back
  with dpm-xbrl and evaluates its rules with dpm-xl.
- Every invalid template raises `TemplateError`; the CLI never prints a
  traceback. Exit statuses: 0 all evaluable rules pass, 1 some fail,
  2 usage error, 3 invalid input or unwritable output.
- A change to the values generated for a seed goes in the changelog.
- Docs examples: a `text` block directly after a `python` block is its
  expected output; `console` blocks run `dpm-synth` commands (`$ echo $?`
  prints the exit status); `<!-- docs: skip -->` before a block skips it.
  Show real output, never invented output.
- Shared link targets for the docs (such as the sibling sites) are in
  `docs/.snippets/links.md`.
- Never use a real company's LEI in code, tests or docs; use the fictional
  `SYNTHETICDPMXL000002` (`DEFAULT_ENTITY`) or another checksum-valid
  fictional one.
- Commit messages follow Conventional Commits (`type(scope): description`),
  imperative, under 72 characters, no trailing period.
- British spelling in prose, as in the existing docs. Plain, precise
  sentences; no marketing language.
- dpm-synth is independent and not affiliated with the EBA; keep that
  statement where it appears.

## Release

1. Make sure the git sources are gone and `uv.lock` resolves dpm-xl and
   dpm-xbrl from PyPI (see above).
2. Move the `Unreleased` changelog entries under a new version heading.
3. Set `version` in `pyproject.toml` and run `uv lock`.
4. Check the build: `uv build` and `uvx twine check --strict dist/*`.
5. Commit as `build: release X.Y.Z`, tag `vX.Y.Z` and publish a GitHub
   release. `.github/workflows/publish.yml` checks that the tag matches the
   version, tests, builds and uploads to PyPI through trusted publishing;
   `.github/workflows/docs.yml` deploys the docs on every push to `main`.
