"""The invented course behind the documentation's example output and the
offline `demo` command.

Kept here, rather than written by hand into the docs, so `test_readme.py` can
assert the documented output still matches what the CLI actually prints. A
sample that drifts from reality is worse than no sample.

Everyone here is made up. Never put real student data in a fixture.
"""

from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from gh_class_sak.fakes import FakeCommit, FakeGithub, FakeNamedUser, FakeOrg, FakeRepo

DEMO_ORG = "cs101-fall"
DEMO_CLASSROOM = "cs101_fall"
DEMO_ASSIGNMENT = "project"


def _member(login, name):
    return FakeNamedUser(login, name=name, role_name="write")


def _instructor():
    return FakeNamedUser("prof-ada", name="Ada Lovelace", role_name="admin", admin=True)


def _row(name, students):
    return {"name": name, "students": students, "repo": None, "repo_id": None}


def seed_demo_meta(root):
    """The demo course's classroom-meta content, in a real local bare git.

    Returns the bare repo's path, for demo_github(meta_origin=...). The
    caller must also point meta_store.meta_checkout_dir somewhere disposable.
    """
    from git import Repo as GitRepo

    from gh_class_sak import meta_store as ms

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    bare = root / "classroom-meta.git"
    GitRepo.init(bare, bare=True).close()
    work = root / "seed-work"
    GitRepo.clone_from(str(bare), str(work)).close()
    # no prefix, so repo names start at the assignment segment — matching the
    # org's existing project-* and hw1-* repos
    ms.save_classroom(str(work), DEMO_CLASSROOM, assignments={
        "project": [
            _row("team-1", ["/jdoe", "/msmith"]),
            _row("nightowls", ["/rpatel", "/tk-codes"]),
            _row("team-3", ["/lchen"]),
        ],
        "hw1": [
            _row("jdoe", ["/jdoe"]),
            _row("rpatel", ["/rpatel"]),
        ],
    })
    ms.commit_and_push(str(work), "seed")
    return str(bare)


def _seed_git(bare, name):
    """a bare origin for a demo repo, holding one commit on main."""
    from git import Actor
    from git import Repo as GitRepo

    work = Path(f"{bare}-work")
    source = GitRepo.init(work, initial_branch="main")
    (work / "README.md").write_text(f"# {name}\n")
    source.index.add(["README.md"])
    who = Actor("gh-class-sak demo", "demo@example.invalid")
    source.index.commit("starter", author=who, committer=who)
    GitRepo.clone_from(str(work), str(bare), bare=True).close()
    source.close()


def demo_github(meta_origin=None, git_root=None):
    """the demo org. with git_root, every repo gets a real local bare origin
    there (and repos the tool creates do too), so cloning works offline."""
    prof = _instructor()
    repos = [
        FakeRepo(DEMO_ORG, "project-team-1", collaborators=[
            _member("jdoe", "Jane Doe"),
            _member("msmith", "Marcus Smith"),
            prof,
        ], commits=[
            FakeCommit("jdoe", "Jane Doe", "jane.doe@cs101.edu"),
            FakeCommit("msmith", "Marcus Smith", "msmith@users.noreply.github.com"),
        ]),
        FakeRepo(DEMO_ORG, "project-nightowls", collaborators=[
            _member("rpatel", "Riya Patel"),
            _member("tk-codes", None),
            prof,
        ], commits=[
            FakeCommit("rpatel", "Riya Patel", "riya@cs101.edu"),
        ]),
        FakeRepo(DEMO_ORG, "project-team-3", collaborators=[
            _member("lchen", "Lin Chen"),
            prof,
        ], commits_raise=True),
        FakeRepo(DEMO_ORG, "hw1-jdoe", collaborators=[_member("jdoe", "Jane Doe")]),
        FakeRepo(DEMO_ORG, "hw1-rpatel", collaborators=[_member("rpatel", "Riya Patel")]),
        FakeRepo(DEMO_ORG, "course-notes"),
    ]
    if git_root is not None:
        for repo in repos:
            bare = Path(git_root) / f"{repo.name}.git"
            _seed_git(bare, repo.name)
            repo.clone_url = str(bare)
    if meta_origin is not None:
        repos.append(FakeRepo(DEMO_ORG, "classroom-meta", clone_url=str(meta_origin)))
    return FakeGithub(orgs=[FakeOrg(DEMO_ORG, repos,
                                    local_git_root=None if git_root is None
                                    else str(git_root))])


@contextmanager
def demo_world(root, with_config=False, with_git=False):
    """run the CLI against the demo course, offline, with all state in root.

    every module's github and token lookups answer from the demo org, the
    classroom-meta checkouts land in root, and the config file is root's —
    listing the demo org when with_config, absent otherwise (as a first-time
    reader has it). with_git gives the demo repos real local origins.
    """
    from gh_class_sak import core
    from gh_class_sak import meta_store as ms
    from gh_class_sak.commands import (
        canvas,
        classrooms,
        completion,
        course,
        meta,
        repos,
        setup,
    )

    root = Path(root)
    origins = root / "origins"
    gh = demo_github(seed_demo_meta(origins), git_root=origins if with_git else None)
    config = root / "gh-class-sak.ini"
    if with_config:
        config.write_text(f"[ORGS]\n{DEMO_ORG}\n")
    patches = [
        mock.patch.object(ms, "meta_checkout_dir",
                          lambda org: str(root / "checkouts" / org)),
        mock.patch.object(core, "config_ini", str(config)),
        mock.patch.object(setup, "probe_token",
                          lambda: ("ghp_faketoken", "the demo's made-up token")),
    ]
    for mod in (core, canvas, classrooms, completion, course, meta, repos, setup):
        patches.append(mock.patch.object(mod, "get_github", lambda: gh, create=True))
        patches.append(mock.patch.object(mod, "get_token", lambda: "ghp_faketoken",
                                         create=True))
    for patch in patches:
        patch.start()
    try:
        yield gh
    finally:
        for patch in reversed(patches):
            patch.stop()
