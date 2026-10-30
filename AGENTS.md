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
- Both come from PyPI, within one major version (`>=1.0,<2`). Do not add
  `[tool.uv.sources]` overrides (local paths or git branches) to a
  committed `pyproject.toml`: the lock must resolve them from pypi.org, as
  CI and the published wheel do. To try an unreleased sibling locally, use
  `uv pip install -e ../dpm-xl` in your environment without committing it.

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
- Code annotations (`# (1)!` comments with a numbered list right after
  the block) may stand between a `python` block and its `text` output,
  and are removed from `console` commands before they run; the docs tests
  check that each annotation has its list item.
- Shared link targets for the docs (such as the sibling sites) are in
  `docs/.snippets/links.md`; the glossary tooltips, auto-appended to every
  page, in `docs/.snippets/glossary.md`, with each term also on
  `docs/reference/glossary.md`.
- The standards the reports follow, their versions, and how that is
  tested belong on `docs/reference/standards.md`; other pages link there.
- The toolkit cards, the toolkit page, the glossary and
  `docs/stylesheets/toolkit.css` are the same in dpm-xl, dpm-xbrl and
  dpm-synth; `tests/test_toolkit.py` pins their hashes.
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

1. Move the `Unreleased` changelog entries under a new version heading.
2. Set `version` in `pyproject.toml` and run `uv lock`; check that
   `uv.lock` resolves dpm-xl and dpm-xbrl from `https://pypi.org/simple`.
3. Run every check in "Commands" above.
4. Check the build: `uv build` and `uvx twine check --strict dist/*`.
5. Commit as `build: release X.Y.Z`, tag `vX.Y.Z` and publish a GitHub
   release. `.github/workflows/publish.yml` checks that the tag matches the
   version, tests, builds and uploads to PyPI through trusted publishing;
   `.github/workflows/docs.yml` deploys the docs on every push to `main`.
