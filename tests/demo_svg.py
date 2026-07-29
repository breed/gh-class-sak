"""Renders docs/demo.svg — an animated terminal cast of the core commands.

Like the README's console fences (guarded by test_readme.py), the cast is
produced by running the real CLI against the invented course in tests/demo.py,
so it cannot show output the tool doesn't actually print. test_demo_svg.py
asserts the committed file matches a fresh render; when it goes stale:

    python -m tests.demo_svg
"""

import contextlib
import os
import shlex
import tempfile
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

from click.testing import CliRunner

from gh_class_sak import core
from gh_class_sak import meta_store as ms
from gh_class_sak.commands import classrooms as classrooms_cmd
from gh_class_sak.commands import meta as meta_cmd
from gh_class_sak.commands import repos as repos_cmd
from gh_class_sak.core import gh_class_sak
from tests.demo import demo_github, seed_demo_meta

SVG_PATH = Path(__file__).resolve().parent.parent / "docs" / "demo.svg"

# the story the cast tells: discover the org, inspect a roster, pull it all
# down for grading
COMMANDS = [
    "gh-class-sak classrooms cs101-fall",
    "gh-class-sak repos list cs101-fall project --members --name",
    "gh-class-sak repos clone cs101-fall project --dest grading",
]

# geometry and pacing. everything below is deterministic — the drift test
# compares the committed file byte-for-byte against a fresh render
WIDTH = 740
PAD = 24
TITLE_H = 40
LINE_H = 20
FONT_S = 13
TYPE_S = 0.032  # per typed character
ENTER_S = 0.45  # pause between a command and its output
OUT_S = 0.085   # per output line
GAP_S = 0.75    # pause before the next prompt
HOLD_S = 4.0    # hold the full transcript before the loop restarts
BLINK_S = 0.55  # cursor half-period


def _outputs():
    """Run every COMMANDS entry against the demo fixture, fully offline."""
    with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(
            ms, "meta_checkout_dir", lambda org: str(Path(tmp) / "checkouts" / org)))
        gh = demo_github(seed_demo_meta(Path(tmp) / "origins"))
        # the demo runs with no config file, as a first-time reader would
        stack.enter_context(
            mock.patch.object(core, "config_ini", str(Path(tmp) / "absent.ini")))
        for mod in (core, classrooms_cmd, repos_cmd, meta_cmd):
            stack.enter_context(
                mock.patch.object(mod, "get_github", lambda: gh, create=True))
            stack.enter_context(
                mock.patch.object(mod, "get_token", lambda: "ghp_faketoken", create=True))
        runner = CliRunner()
        cast = []
        for line in COMMANDS:
            result = runner.invoke(gh_class_sak, shlex.split(line)[1:])
            if result.exit_code != 0:
                raise RuntimeError(f"{line!r} failed:\n{result.output}")
            out = result.output.rstrip()
            if os.sep != "/":  # the cast documents the unix flavor, as the README does
                out = out.replace(os.sep, "/")
            cast.append((line, out.splitlines()))
        return cast


def render_svg():
    """One shared, infinitely looping timeline; each element gets a keyframe
    window on it.

    Browsers render an SVG referenced from <img> (the GitHub README case) with
    a quirk: animation-delay plus a millisecond animation held by
    fill:forwards is unreliable — fills from before the image rasterizes can
    be dropped, freezing the cast. Continuous animations are not affected, so
    every element runs one infinite animation from t=0 and reveals itself at a
    percentage of the shared cycle instead of after a delay. The cast loops,
    holding the finished transcript HOLD_S before it restarts.
    """
    cast = _outputs()
    reveals = []  # per-element reveal time; the index names its keyframes

    def _a(t):
        reveals.append(t)
        return f'class="a" style="animation-name:k{len(reveals) - 1}"'

    body = []
    t = 0.6
    y = TITLE_H + PAD + FONT_S
    for cmd, out_lines in cast:
        spans = [f'<tspan {_a(t)} fill="#7ee787" font-weight="600">$ </tspan>']
        t += TYPE_S
        for ch in cmd:
            spans.append(f'<tspan {_a(t)}>{escape(ch)}</tspan>')
            t += TYPE_S
        body.append(f'<text x="{PAD}" y="{y}" xml:space="preserve">{"".join(spans)}</text>')
        y += LINE_H
        t += ENTER_S
        for line in out_lines:
            body.append(f'<text {_a(t)} fill="#b6c2cf" x="{PAD}" y="{y}" '
                        f'xml:space="preserve">{escape(line)}</text>')
            y += LINE_H
            t += OUT_S
        y += LINE_H  # blank line between blocks
        t += GAP_S
    cursor_t = t
    body.append(
        f'<text x="{PAD}" y="{y}" xml:space="preserve">'
        f'<tspan {_a(t)} fill="#7ee787" font-weight="600">$ </tspan>'
        f'<tspan class="cursor">█</tspan></text>')
    height = y + PAD

    total = cursor_t + HOLD_S

    def pct(seconds):
        return round(seconds / total * 100, 3)

    frames = []
    for i, reveal in enumerate(reveals):
        on = pct(reveal)
        frames.append(f'@keyframes k{i} {{ 0%, {on}% {{ opacity: 0; }} '
                      f'{min(on + 0.05, 100.0)}%, 100% {{ opacity: 1; }} }}')
    # the cursor blinks through the tail of the cycle
    marks = []
    mark = cursor_t
    while mark < total:
        marks.append(mark)
        mark += BLINK_S
    blink = [f'0%, {pct(marks[0])}% {{ opacity: 0; }}']
    for i, mark in enumerate(marks):
        end = pct(marks[i + 1]) if i + 1 < len(marks) else 100.0
        state = 1 - i % 2
        blink.append(f'{min(pct(mark) + 0.05, 100.0)}%, {end}% {{ opacity: {state}; }}')
    frames.append('@keyframes blink { ' + ' '.join(blink) + ' }')

    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" '
        'aria-label="gh-class-sak terminal demo">',
        '<style>',
        f'text {{ font: {FONT_S}px ui-monospace, SFMono-Regular, "Cascadia Mono", Menlo, '
        'Consolas, "Liberation Mono", monospace; fill: #e6edf3; }',
        '.dim { fill: #8b949e; }',
        f'.a, .cursor {{ opacity: 0; animation-duration: {total:.2f}s; '
        'animation-timing-function: steps(1, end); '
        'animation-iteration-count: infinite; }',
        '.cursor { animation-name: blink; }',
        *frames,
        '</style>',
        f'<rect width="{WIDTH}" height="{height}" rx="9" fill="#0d1117"/>',
        f'<rect width="{WIDTH}" height="{TITLE_H}" rx="9" fill="#161b22"/>',
        f'<rect y="{TITLE_H - 9}" width="{WIDTH}" height="9" fill="#161b22"/>',
        f'<circle cx="{PAD}" cy="{TITLE_H // 2}" r="6" fill="#ff5f57"/>',
        f'<circle cx="{PAD + 22}" cy="{TITLE_H // 2}" r="6" fill="#febc2e"/>',
        f'<circle cx="{PAD + 44}" cy="{TITLE_H // 2}" r="6" fill="#28c840"/>',
        f'<text class="dim" x="{WIDTH // 2}" y="{TITLE_H // 2 + 5}" text-anchor="middle">'
        'gh-class-sak — the invented course from tests/demo.py</text>',
    ]
    return "\n".join(head + body + ["</svg>"]) + "\n"


def main():
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SVG_PATH.open("w", encoding="utf-8", newline="\n") as f:
        f.write(render_svg())
    print(f"wrote {SVG_PATH}")


if __name__ == "__main__":
    main()
