"""Guards the README's example output against drift.

A stale code sample is worse than none: it teaches the wrong thing and quietly
tells a reader the project isn't maintained. So every ```console fence in the
README is replayed against the demo fixture in tests/demo.py and compared
exactly — including duplicated blocks, so no copy can go stale.

If this fails, the CLI's output changed. Re-run the command against the demo
fixture and paste the new output into the README — don't relax the test.
"""

import re
import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from gh_class_sak import core
from gh_class_sak.commands import classrooms as classrooms_cmd
from gh_class_sak.commands import repos as repos_cmd
from gh_class_sak.core import gh_class_sak
from tests.demo import demo_github

README = Path(__file__).resolve().parent.parent / "README.md"

_CONSOLE_FENCE = re.compile(r"```console\n(.*?)```", re.DOTALL)


def _console_blocks():
    """every (args, expected_output) pair the README documents."""
    blocks = []
    for m in _CONSOLE_FENCE.finditer(README.read_text(encoding="utf-8")):
        lines = m.group(1).splitlines()
        assert lines and lines[0].startswith("$ gh-class-sak "), (
            f"console fence must open with a gh-class-sak command: {lines[:1]}"
        )
        args = shlex.split(lines[0])[2:]  # drop "$ gh-class-sak"
        blocks.append((args, "\n".join(lines[1:]).rstrip()))
    return blocks


BLOCKS = _console_blocks()


@pytest.fixture
def demo_cli(monkeypatch, tmp_path):
    gh = demo_github()
    for mod in (core, classrooms_cmd, repos_cmd):
        monkeypatch.setattr(mod, "get_github", lambda: gh, raising=False)
    # the demo runs with no config file, as a first-time reader would
    monkeypatch.setattr(core, "config_ini", str(tmp_path / "absent.ini"))
    return CliRunner()


def test_readme_documents_the_core_commands():
    documented = {tuple(args[:2]) for args, _ in BLOCKS}
    assert ("classrooms",) in documented
    assert ("repos", "list") in documented
    assert ("repos", "clone") in documented


@pytest.mark.parametrize(("args", "expected"), BLOCKS,
                         ids=[" ".join(args) for args, _ in BLOCKS])
def test_readme_output_matches_the_cli(demo_cli, args, expected):
    result = demo_cli.invoke(gh_class_sak, args)
    assert result.exit_code == 0, result.output
    assert result.output.rstrip() == expected, (
        f"README output for `gh-class-sak {' '.join(args)}` is stale.\n"
        f"README says:\n{expected}\n\nthe CLI prints:\n{result.output.rstrip()}"
    )


def test_readme_has_no_real_student_data():
    """The README must use the invented cs101-fall course, not a live org."""
    readme = README.read_text(encoding="utf-8")
    assert "SJSU-CMPE-195" not in readme
