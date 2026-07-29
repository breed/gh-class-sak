"""Guards the documentation's example output against drift.

A stale code sample is worse than none: it teaches the wrong thing and quietly
tells a reader the project isn't maintained. So every ```console fence in the
README and in docs/*.md is replayed against the demo fixture in tests/demo.py
and compared exactly — including duplicated blocks, so no copy can go stale.

If this fails, the CLI's output changed. Re-run the command against the demo
fixture and paste the new output into the offending page — don't relax the test.
"""

import os
import re
import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from gh_class_sak import core
from gh_class_sak import meta_store as ms
from gh_class_sak.commands import classrooms as classrooms_cmd
from gh_class_sak.commands import meta as meta_cmd
from gh_class_sak.commands import repos as repos_cmd
from gh_class_sak.core import gh_class_sak
from tests.demo import demo_github, seed_demo_meta

ROOT = Path(__file__).resolve().parent.parent
DOC_PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

_CONSOLE_FENCE = re.compile(r"```console\n(.*?)```", re.DOTALL)


def _console_blocks():
    """every (page, args, expected_output) triple the documentation shows."""
    blocks = []
    for page in DOC_PAGES:
        for m in _CONSOLE_FENCE.finditer(page.read_text(encoding="utf-8")):
            lines = m.group(1).splitlines()
            assert lines and lines[0].startswith("$ gh-class-sak "), (
                f"{page.name}: console fence must open with a gh-class-sak"
                f" command: {lines[:1]}"
            )
            args = shlex.split(lines[0])[2:]  # drop "$ gh-class-sak"
            blocks.append((page.name, args, "\n".join(lines[1:]).rstrip()))
    return blocks


BLOCKS = _console_blocks()


@pytest.fixture
def demo_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "meta_checkout_dir",
                        lambda org: str(tmp_path / "checkouts" / org))
    gh = demo_github(seed_demo_meta(tmp_path / "origins"))
    for mod in (core, classrooms_cmd, repos_cmd, meta_cmd):
        monkeypatch.setattr(mod, "get_github", lambda: gh, raising=False)
        monkeypatch.setattr(mod, "get_token", lambda: "ghp_faketoken", raising=False)
    # the demo runs with no config file, as a first-time reader would
    monkeypatch.setattr(core, "config_ini", str(tmp_path / "absent.ini"))
    return CliRunner()


def test_docs_document_the_core_commands():
    documented = {tuple(args[:2]) for _page, args, _ in BLOCKS}
    assert any(args[0] == "classrooms" for args in documented)
    assert ("repos", "list") in documented
    assert ("repos", "clone") in documented


def test_readme_opens_with_runnable_examples():
    """the README is the pitch; it must show the tool actually running."""
    assert any(page == "README.md" for page, _args, _ in BLOCKS)


def _normalized(text):
    # windows prints paths with native separators; the docs document the
    # unix flavor. separator direction is not the drift this test guards.
    return text.replace(os.sep, "/") if os.sep != "/" else text


@pytest.mark.parametrize(("page", "args", "expected"), BLOCKS,
                         ids=[f"{page}: {' '.join(args)}" for page, args, _ in BLOCKS])
def test_documented_output_matches_the_cli(demo_cli, page, args, expected):
    result = demo_cli.invoke(gh_class_sak, args)
    assert result.exit_code == 0, result.output
    assert _normalized(result.output.rstrip()) == expected, (
        f"{page} output for `gh-class-sak {' '.join(args)}` is stale.\n"
        f"{page} says:\n{expected}\n\nthe CLI prints:\n{result.output.rstrip()}"
    )


def test_docs_have_no_real_student_data():
    """the docs must use the invented cs101-fall course, not a live org."""
    for page in DOC_PAGES:
        assert "SJSU-CMPE-195" not in page.read_text(encoding="utf-8"), page.name
