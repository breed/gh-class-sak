"""The invented course used for the README's example output.

Kept here, rather than written by hand into the README, so `test_readme.py` can
assert the documented output still matches what the CLI actually prints. A
sample that drifts from reality is worse than no sample.

Everyone here is made up. Never put real student data in a fixture.
"""

from tests.fakes import FakeCommit, FakeGithub, FakeNamedUser, FakeOrg, FakeRepo

DEMO_ORG = "cs101-fall"
DEMO_ASSIGNMENT = "project"


def _member(login, name):
    return FakeNamedUser(login, name=name, role_name="write")


def _instructor():
    return FakeNamedUser("prof-ada", name="Ada Lovelace", role_name="admin", admin=True)


def demo_github():
    prof = _instructor()
    return FakeGithub(orgs=[FakeOrg(DEMO_ORG, [
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
    ])])
