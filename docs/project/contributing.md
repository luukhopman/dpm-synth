---
description: How to set up a development environment for dpm-synth, run the tests, linters and docs build, and the conventions for changes.
---

# Contributing

Bug reports, questions and pull requests are welcome on
[GitHub](https://github.com/luukhopman/dpm-synth/issues). For a larger
change, such as a new repair or a solver, open an issue first to agree on
the approach.

## Set up

dpm-synth uses [uv](https://docs.astral.sh/uv/):

```text
git clone https://github.com/luukhopman/dpm-synth
cd dpm-synth
uv sync
```

## Check a change

```text
uv run pytest                        # tests, including every docs example
uv run ruff check
uv run ruff format --check
uv run ty check
uv run python scripts/build_docs.py  # strict docs build into site/
```

`uv run zensical serve` previews the documentation while you edit it.

## Conventions

- Every behaviour has a test. Build templates in code with
  `tests/support.py`, or add a small one to `docs/samples`: every sample is
  generated, written, read back with dpm-xbrl and evaluated with dpm-xl by
  `tests/test_end_to_end.py`.
- Public functions and classes have Google-style docstrings; they are the
  API reference.
- dpm-synth depends on dpm-xl and dpm-xbrl only, and uses only the names in
  their `__all__`. New runtime dependencies need a good reason.
- Keep `__all__`, the docs and the [changelog](changelog.md) in step with
  the code. Examples in the docs are run by `tests/test_docs.py`, so show
  real output.
- A change to the generated values for a seed is noted in the changelog.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
  such as `fix(generator): keep bounds when repairing products`.

`AGENTS.md` in the repository holds the same information for coding
agents.
