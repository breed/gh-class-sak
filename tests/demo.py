"""The invented course used for the documentation's example output.

Kept here, rather than written by hand into the docs, so `test_readme.py` can
assert the documented output still matches what the CLI actually prints. A
sample that drifts from reality is worse than no sample.

Everyone here is made up. Never put real student data in a fixture.
"""

from pathlib import Path

from tests.fakes import FakeCommit, FakeGithub, FakeNamedUser, FakeOrg, FakeRepo

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


def demo_github(meta_origin=None):
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
    if meta_origin is not None:
        repos.append(FakeRepo(DEMO_ORG, "classroom-meta", clone_url=str(meta_origin)))
    return FakeGithub(orgs=[FakeOrg(DEMO_ORG, repos)])
