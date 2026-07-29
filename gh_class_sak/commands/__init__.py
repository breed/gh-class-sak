"""Importing a command module registers its commands on the root click group."""

from gh_class_sak.commands import classrooms, repos

__all__ = [
    "classrooms",
    "repos",
]
