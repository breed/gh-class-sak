"""Guards docs/demo.svg against drift, as test_readme.py guards the fences.

The animated cast on the README is rendered from tests/demo.py, never drawn by
hand. If this fails, the CLI's output changed — regenerate the cast:

    python -m tests.demo_svg
"""

from pathlib import Path

from tests.demo_svg import SVG_PATH, render_svg


def test_demo_svg_matches_regeneration():
    assert SVG_PATH.exists(), "docs/demo.svg is missing; run: python -m tests.demo_svg"
    committed = SVG_PATH.read_text(encoding="utf-8")
    assert committed == render_svg(), (
        "docs/demo.svg is stale. Regenerate it:  python -m tests.demo_svg"
    )


def test_readme_embeds_the_demo():
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "docs/demo.svg" in readme
