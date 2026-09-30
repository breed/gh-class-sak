"""Importing a command module registers its commands on the root click group."""

from gh_class_sak.commands import canvas, classrooms, completion, course, demo, meta, repos, setup

__all__ = [
    "canvas",
    "classrooms",
    "completion",
    "course",
    "demo",
    "meta",
    "repos",
    "setup",
]
