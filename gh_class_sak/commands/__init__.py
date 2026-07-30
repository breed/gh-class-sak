"""Importing a command module registers its commands on the root click group."""

from gh_class_sak.commands import classrooms, meta, repos, setup

__all__ = [
    "classrooms",
    "meta",
    "repos",
    "setup",
]
