"""demo: try any command on a made-up course, offline."""

import shutil
import sys
import tempfile

import click

from gh_class_sak.core import error, gh_class_sak, info, output

INTRO = """\
a made-up course to try any command on, offline: nothing touches github or
canvas, and nothing is kept — every run starts from the same course.

  org cs101-fall, course cs101_fall
  assignments hw1 (jdoe, rpatel) and project (team-1, nightowls, team-3)

try:
  gh-class-sak demo course status cs101_fall
  gh-class-sak demo repos list cs101_fall project --members --name
  gh-class-sak demo sync cs101_fall --apply
  gh-class-sak demo course ta add cs101_fall /ta-ann --apply
  gh-class-sak demo repos clone cs101_fall project --dest /tmp/grading --apply

canvas features need a real canvas, so they aren't in the demo."""


@gh_class_sak.command("demo", context_settings={
    "ignore_unknown_options": True, "allow_interspersed_args": False})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def demo(args):
    """Try any command on a made-up course, offline.

    Nothing touches GitHub or Canvas and nothing is kept, so --apply is safe
    here: every run starts from the same course. Without a command, it
    describes the course and suggests a few.

    \b
    Examples:
      gh-class-sak demo
      gh-class-sak demo course status cs101_fall
      gh-class-sak demo sync cs101_fall --apply
    """
    from gh_class_sak.demo import demo_world

    if not args:
        output(INTRO)
        return
    if args[0] == "demo":
        error("already in the demo: drop the second demo")
        sys.exit(2)
    root = tempfile.mkdtemp(prefix="gh-class-sak-demo-")
    try:
        with demo_world(root, with_config=True, with_git=True):
            info("(demo: a made-up course, offline — nothing is kept)")
            gh_class_sak.main(args=list(args), prog_name="gh-class-sak")
    finally:
        # git marks pack files read-only, which a plain rmtree can't
        # delete on windows; a leftover temp dir is harmless
        shutil.rmtree(root, ignore_errors=True)
