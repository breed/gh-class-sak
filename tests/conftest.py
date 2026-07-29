import pytest
from click.testing import CliRunner

from gh_class_sak import core
from gh_class_sak.commands import classrooms as classrooms_cmd
from gh_class_sak.commands import repos as repos_cmd
from tests.fakes import (
    FakeCanvas,
    FakeCanvasGroup,
    FakeCommit,
    FakeCourse,
    FakeGithub,
    FakeGroupCategory,
    FakeNamedUser,
    FakeOrg,
    FakeRepo,
)

ORG = "SJSU-CMPE-195"


def _user(login, name=None, email=None, admin=False):
    return FakeNamedUser(login, name=name, email=email,
                         role_name="admin" if admin else "write", admin=admin)


@pytest.fixture
def fake_github():
    """An org with two project repos, one hw repo, an empty repo, and a non-assignment repo."""
    instructor = _user("profbeth", name="Beth Reed", admin=True)

    team12 = FakeRepo(ORG, "project-team-12", collaborators=[
        _user("alice", name="Alice Adams"),
        _user("bob", name="Bob Baker"),
        instructor,
    ], commits=[
        FakeCommit("alice", "Alice Adams", "alice@sjsu.edu"),
        FakeCommit("alice", "Alice Adams", "alice@sjsu.edu"),
        FakeCommit("bob", "Bob Baker", "bob@users.noreply.github.com"),
        FakeCommit(None, "Unknown", "drive-by@example.com"),
    ])
    redteam = FakeRepo(ORG, "project-red-team", collaborators=[
        _user("carol", name="Carol Chen"),
        _user("dave", name=None),
        instructor,
    ], commits=[
        FakeCommit("carol", "Carol Chen", "carol@sjsu.edu"),
    ])
    empty = FakeRepo(ORG, "project-empty", collaborators=[instructor], commits_raise=True)
    hw1a = FakeRepo(ORG, "hw1-alice", collaborators=[_user("alice", name="Alice Adams")])
    hw1b = FakeRepo(ORG, "hw1-bob", collaborators=[_user("bob", name="Bob Baker")])
    sandbox = FakeRepo(ORG, "sandbox")

    return FakeGithub(orgs=[FakeOrg(ORG, [team12, redteam, empty, hw1a, hw1b, sandbox])])


@pytest.fixture
def fake_canvas():
    groups = [
        FakeCanvasGroup("Project Group 1", ["Adams, Alice", "Bob Baker"]),
        FakeCanvasGroup("Project Group 2", ["Carol Chen"]),
        FakeCanvasGroup("Project Group 3", ["Erin Evans"]),
    ]
    course = FakeCourse(101, "CMPE-195A", categories=[FakeGroupCategory("Project", groups)])
    enrollments = [
        {"role": {"name": "StudentEnrollment"},
         "user": {"_id": "1", "name": "Alice Adams", "email": "alice@sjsu.edu"},
         "courseSectionId": "s1"},
        {"role": {"name": "StudentEnrollment"},
         "user": {"_id": "2", "name": "Bob Baker", "email": "bob@sjsu.edu"},
         "courseSectionId": "s1"},
        {"role": {"name": "StudentEnrollment"},
         "user": {"_id": "3", "name": "Carol Chen", "email": "carol@sjsu.edu"},
         "courseSectionId": "s2"},
        {"role": {"name": "StudentEnrollment"},
         "user": {"_id": "4", "name": "Erin Evans", "email": "erin@sjsu.edu"},
         "courseSectionId": "s2"},
        {"role": {"name": "TeacherEnrollment"},
         "user": {"_id": "9", "name": "Beth Reed", "email": "beth@sjsu.edu"},
         "courseSectionId": "s1"},
    ]
    profiles = {
        "1": {"links": [{"url": "https://github.com/alice"}]},
        "2": {"bio": "code at github.com/bob"},
        "3": {"links": [{"url": "https://github.com/carol"}]},
        "4": {},
        "9": {"links": [{"url": "https://github.com/profbeth"}]},
    }
    return FakeCanvas(courses=[course], enrollments=enrollments, profiles=profiles)


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "gh-class-sak.ini"
    path.write_text(
        "[CANVAS]\nurl = https://canvas.example.edu\ntoken = xyz\n\n"
        f"[COURSES]\nCMPE-195A = {ORG}\n"
    )
    monkeypatch.setattr(core, "config_ini", str(path))
    return str(path)


@pytest.fixture
def no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "config_ini", str(tmp_path / "absent.ini"))
    return None


@pytest.fixture
def cli(monkeypatch, fake_github, fake_canvas):
    """A CliRunner with GitHub, Canvas, and token access stubbed out."""
    from gh_class_sak.commands import meta as meta_cmd

    for mod in (core, repos_cmd, classrooms_cmd, meta_cmd):
        monkeypatch.setattr(mod, "get_github", lambda: fake_github, raising=False)
        monkeypatch.setattr(mod, "get_token", lambda: "ghp_faketoken", raising=False)
    monkeypatch.setattr(core, "get_canvas", lambda: fake_canvas)
    monkeypatch.setattr(repos_cmd, "get_canvas", lambda: fake_canvas)
    return CliRunner()


def run(cli, *args):
    from gh_class_sak.core import gh_class_sak
    return cli.invoke(gh_class_sak, list(args))
