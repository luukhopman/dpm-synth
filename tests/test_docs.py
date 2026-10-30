"""Run the examples in the documentation, so the docs cannot drift.

Every Markdown page under ``docs/`` (and the README) is checked, in a fresh
directory holding the sample templates from ``docs/samples``:

* ``python`` blocks run in order in one namespace per page. A ``text`` block
  that directly follows a ``python`` block is its expected output and must
  match what the code prints.
* ``console`` blocks hold ``$ dpm-synth ...`` commands, each followed by its
  expected output (stdout and stderr, as a terminal shows them);
  ``$ echo $?`` prints the previous command's exit status.

A block may carry code annotations: ``# (1)!`` comments, explained by the
numbered list right after the block. The list may stand between a ``python``
block and its output, and the comments are removed from ``console``
commands before they run.

``<!-- docs: skip -->`` on the line before a block leaves it out, with its
output; use it only for commands of other tools.

The docstring examples of every module run as doctests, in the same kind of
directory, and every page must be in the navigation.
"""

from __future__ import annotations

import contextlib
import doctest
import importlib
import io
import os
import re
import shlex
import shutil
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from dpmsynth.cli import main
from tests.support import SAMPLES

ROOT = Path(__file__).parent.parent
PAGES = [
    *sorted(
        path for path in (ROOT / "docs").rglob("*.md") if ".snippets" not in path.parts
    ),
    ROOT / "README.md",
]
FENCE = re.compile(r"^(?P<indent> *)```(?P<lang>[\w-]*)[^\n]*$")
MARKER = re.compile(r"^\s*<!-- docs: (?P<marker>[\w-]+) -->\s*$")
ANNOTATION = re.compile(r"\s*# \((?P<number>\d+)\)!?\s*$")
LIST_ITEM = re.compile(r"^\s*(?P<number>\d+)\.\s")


@dataclass
class Block:
    """One fenced code block of a page."""

    lang: str
    code: str
    line: int
    marker: str | None
    follows_python: bool


def blocks(path: Path) -> list[Block]:
    """Return the fenced code blocks of a Markdown page.

    Returns:
        list[Block]: Blocks in page order.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[Block] = []
    index = 0
    previous_end: int | None = None
    while index < len(lines):
        match = FENCE.match(lines[index])
        if not match:
            index += 1
            continue
        indent = len(match["indent"])
        start = index
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != "```":
            body.append(lines[index][indent:])
            index += 1
        marker_match = MARKER.match(lines[start - 1]) if start else None
        between = lines[previous_end + 1 : start] if previous_end is not None else []
        follows_python = (
            bool(found)
            and found[-1].lang == "python"
            and (
                all(not line.strip() for line in between)
                or (
                    bool(annotations(found[-1].code))
                    and annotation_list(between) is not None
                )
            )
        )
        found.append(
            Block(
                match["lang"],
                "\n".join(body) + "\n",
                start + 1,
                marker_match["marker"] if marker_match else None,
                follows_python,
            )
        )
        previous_end = index
        index += 1
    return found


def annotations(code: str) -> list[int]:
    """Return the numbers of the code annotations in a block, in order.

    Returns:
        list[int]: The numbers of the ``# (n)!`` comments.
    """
    return [
        int(match["number"])
        for line in code.splitlines()
        if (match := ANNOTATION.search(line))
    ]


def annotation_list(lines: list[str]) -> list[int] | None:
    """Return the item numbers of the annotation list in these lines.

    Returns:
        list[int] | None: The numbers of the list items, or None if the
        lines are not one numbered list (with indented continuation lines),
        surrounded by blank lines only.
    """
    numbers: list[int] = []
    for line in lines:
        if not line.strip():
            continue
        match = LIST_ITEM.match(line)
        if match:
            numbers.append(int(match["number"]))
        elif not numbers or not line[:1].isspace():
            return None
    return numbers or None


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def _run_cli(command: str) -> tuple[int, str]:
    output = io.StringIO()
    # argparse wraps help text to the terminal width.
    os.environ["COLUMNS"] = "80"
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            status = main(shlex.split(command)[1:])
        except SystemExit as exit_:
            status = exit_.code if isinstance(exit_.code, int) else 0
    return status, output.getvalue()


def _check_console(block: Block, where: str) -> None:
    status = 0
    commands: list[tuple[str, list[str]]] = []
    for line in block.code.splitlines():
        if line.startswith("$ "):
            commands.append((ANNOTATION.sub("", line[2:]), []))
        elif commands:
            commands[-1][1].append(line)
        elif line.strip():
            pytest.fail(f"{where}: output before the first command")
    for command, expected in commands:
        if command == "echo $?":
            output = f"{status}\n"
        elif command.startswith("dpm-synth"):
            status, output = _run_cli(command)
        else:
            pytest.fail(f"{where}: only dpm-synth commands run in console blocks")
        assert _normalize(output) == _normalize("\n".join(expected)), (
            f"{where}: output of {command!r} differs"
        )


@pytest.fixture
def samples_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for sample in SAMPLES.iterdir():
        shutil.copy(sample, tmp_path / sample.name)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("path", PAGES, ids=lambda path: str(path.relative_to(ROOT)))
@pytest.mark.usefixtures("samples_directory")
def test_page_examples(path: Path) -> None:
    namespace: dict[str, object] = {"__name__": "__docs__"}
    last_output: str | None = None
    skipped = False
    for block in blocks(path):
        where = f"{path.relative_to(ROOT)}:{block.line}"
        if block.lang == "text" and block.follows_python and skipped:
            continue  # the output of a skipped block
        skipped = block.marker == "skip"
        if skipped:
            last_output = None
            continue
        if block.lang == "python":
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(block.code, where, "exec"), namespace)
            last_output = output.getvalue()
        elif block.lang == "text" and block.follows_python:
            assert last_output is not None
            assert _normalize(last_output) == _normalize(block.code), (
                f"{where}: printed output differs"
            )
            last_output = None
        elif block.lang == "console":
            _check_console(block, where)


def test_annotated_python_block_keeps_its_output(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        "```python\n"
        "print(1)  # (1)!\n"
        "```\n\n"
        "1. Prints one,\n"
        "   as the output shows.\n\n"
        "```text\n1\n```\n\n"
        "```python\nprint(2)\n```\n\n"
        "1. Not an annotation list: the block has no annotations.\n\n"
        "```text\n2\n```\n",
        encoding="utf-8",
    )
    found = blocks(page)
    assert [block.lang for block in found] == ["python", "text", "python", "text"]
    assert [block.follows_python for block in found] == [False, True, False, False]
    assert annotations(found[0].code) == [1]


def test_annotation_list_needs_a_numbered_list() -> None:
    assert annotation_list(["", "1. One", "   more", "2. Two", ""]) == [1, 2]
    assert annotation_list(["Some text", "1. One"]) is None
    assert annotation_list(["   indented first"]) is None
    assert annotation_list(["", ""]) is None


def test_console_annotations_are_not_run() -> None:
    block = Block("console", "$ dpm-synth --version  # (1)!\n", 1, None, False)
    with pytest.raises(AssertionError, match="output of 'dpm-synth --version'"):
        _check_console(block, "page.md:1")


@pytest.mark.parametrize("path", PAGES, ids=lambda path: str(path.relative_to(ROOT)))
def test_code_annotations_are_explained(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for block in blocks(path):
        numbers = annotations(block.code)
        if not numbers:
            continue
        end = block.line + block.code.count("\n")
        after: list[str] = []
        for line in lines[end + 1 :]:
            if line.strip() and not LIST_ITEM.match(line) and not line[:1].isspace():
                break
            after.append(line)
        assert annotation_list(after) == numbers, (
            f"{path.relative_to(ROOT)}:{block.line}: annotations {numbers} need "
            "a numbered list with one item each right after the block"
        )


def test_every_glossary_term_is_defined_on_the_glossary_page() -> None:
    docs = ROOT / "docs"
    terms = re.findall(
        r"^\*\[(.+?)\]:", (docs / ".snippets" / "glossary.md").read_text("utf-8"), re.M
    )
    page = (docs / "reference" / "glossary.md").read_text(encoding="utf-8")
    defined = {line.strip() for line in page.splitlines()}
    # A plural shares the definition of its singular.
    missing = [term for term in terms if not {term, term.removesuffix("s")} & defined]
    assert not missing, f"glossary terms not on the glossary page: {missing}"


def test_markdown_copies_leave_out_presentation_markup() -> None:
    spec = spec_from_file_location("build_docs", ROOT / "scripts" / "build_docs.py")
    assert spec and spec.loader
    build_docs = module_from_spec(spec)
    spec.loader.exec_module(build_docs)
    text = (
        '<div class="grid cards" markdown>\n\n'
        "-   :lucide-rocket:{ .lg .middle } **Start**\n\n"
        "    [:lucide-arrow-right: Tutorial](start.md)\n\n"
        "</div>\n\n"
        "[Get started](start.md){ .md-button .md-button--primary }\n"
    )
    assert build_docs.plain(text) == (
        "-   **Start**\n\n    [Tutorial](start.md)\n\n[Get started](start.md)\n"
    )


MODULES = [
    "dpmsynth",
    "dpmsynth.template",
    "dpmsynth.generator",
    "dpmsynth.scale",
    "dpmsynth.cli",
]


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.usefixtures("samples_directory")
def test_docstring_examples(name: str) -> None:
    module = importlib.import_module(name)
    finder = doctest.DocTestFinder(exclude_empty=True)
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in finder.find(module):
        runner.run(test)
    result = runner.summarize(verbose=False)
    assert result.failed == 0


def test_every_page_is_in_the_navigation() -> None:
    config = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    for page in (ROOT / "docs").rglob("*.md"):
        if ".snippets" in page.parts:
            continue
        relative = page.relative_to(ROOT / "docs").as_posix()
        assert f'"{relative}"' in config, f"{relative} is not in the zensical.toml nav"
