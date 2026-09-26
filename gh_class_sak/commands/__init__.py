"""Importing a command module registers its commands on the root click group."""

from gh_class_sak.commands import canvas, classrooms, course, meta, repos, setup

__all__ = [
    "canvas",
    "classrooms",
    "course",
    "meta",
    "repos",
    "setup",
]
