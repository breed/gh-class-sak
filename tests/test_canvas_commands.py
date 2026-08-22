from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from git import Repo as GitRepo

from gh_class_sak import core
from gh_class_sak import meta_store as ms
from gh_class_sak.commands import canvas as canvas_cmd
from gh_class_sak.commands import repos as repos_cmd
from tests.conftest import ORG, run
from tests.fakes import (
    FakeCanvas,
    FakeCourse,
    FakeGithub,
    FakeNamedUser,
    FakeOrg,
    FakeRepo,
)


def _student(user_id, name, email):
    return {"role": {"name": "StudentEnrollment"},
            "user": {"_id": user_id, "name": name, "email": email},
            "courseSectionId": "s1"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """one collaborator plus one student in each stranded category.

    alice collaborates on the project repo (no message). bob holds an
    unaccepted invitation to it. dana's canvas profile links to a github
    account that doesn't exist. erin's profile has no github link at all.
    """
    monkeypatch.setattr(ms, "meta_checkout_dir",
                        lambda org: str(tmp_path / "checkouts" / org))
    bare = tmp_path / "origins" / "classroom-meta.git"
    bare.parent.mkdir(parents=True)
    GitRepo.init(bare, bare=True).close()
    work = tmp_path / "origins" / "seed-work"
    GitRepo.clone_from(str(bare), str(work)).close()
    ms.save_classroom(str(work), "cmpe_195a", assignments={"project": []})
    ms.commit_and_push(str(work), "seed")
    meta = FakeRepo(ORG, "classroom-meta", clone_url=str(bare))

    team1 = FakeRepo(ORG, "project-team-1",
                     collaborators=[FakeNamedUser("alice", name="Alice Adams",
                                                  role_name="write")],
                     invitations=["bob"])
    gh = FakeGithub(orgs=[FakeOrg(ORG, [team1, meta])],
                    missing_users=["ghost"])

    course = FakeCourse(101, "CMPE-195A")
    canvas = FakeCanvas(
        courses=[course],
        enrollments=[
            _student("1", "Alice Adams", "alice@sjsu.edu"),
            _student("2", "Bob Baker", "bob@sjsu.edu"),
            _student("3", "Dana Diaz", "dana@sjsu.edu"),
            _student("4", "Erin Evans", "erin@sjsu.edu"),
        ],
        profiles={
            "1": {"links": [{"url": "https://github.com/alice"}]},
            "2": {"links": [{"url": "https://github.com/bob"}]},
            "3": {"links": [{"url": "https://github.com/ghost"}]},
            "4": {},
        })

    config = tmp_path / "gh-class-sak.ini"
    config.write_text("[CANVAS]\nurl = https://canvas.example.edu\n"
                      f"token = xyz\n\n[ORGS]\n{ORG}\n")
    monkeypatch.setattr(core, "config_ini", str(config))
    for mod in (core, repos_cmd, canvas_cmd):
        monkeypatch.setattr(mod, "get_github", lambda: gh, raising=False)
        monkeypatch.setattr(mod, "get_token", lambda: None, raising=False)
    monkeypatch.setattr(core, "get_canvas", lambda: canvas)
    monkeypatch.setattr(repos_cmd, "get_canvas", lambda: canvas)
    return SimpleNamespace(gh=gh, canvas=canvas, repo=team1,
                           runner=CliRunner())


class TestMessageMissing:
    def test_dryrun_previews_each_category_and_sends_nothing(self, env):
        result = run(env.runner, "canvas", "message-missing", ORG, "project")
        assert result.exit_code == 0, result.output
        assert "would message Erin Evans <erin@sjsu.edu> (no-link)" in result.output
        assert "would message Dana Diaz <dana@sjsu.edu> (bad-link)" in result.output
        assert "would message Bob Baker <bob@sjsu.edu> (invited)" in result.output
        assert "Alice Adams" not in result.output
        assert env.canvas.conversations == []

    def test_dryrun_prints_the_message_texts(self, env):
        result = run(env.runner, "canvas", "message-missing", ORG, "project")
        assert "--- no-link:" in result.output
        assert "--- bad-link:" in result.output
        assert "--- invited:" in result.output
        assert "name (Title) is exactly" in result.output
        assert "URL is your GitHub profile" in result.output

    def test_no_dryrun_sends_one_message_per_stranded_student(self, env):
        result = run(env.runner, "canvas", "message-missing", ORG, "project",
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        by_recipient = {c["recipients"][0]: c for c in env.canvas.conversations}
        assert set(by_recipient) == {"2", "3", "4"}  # bob, dana, erin
        invited = by_recipient["2"]
        assert "Bob Baker" in invited["body"]
        assert env.repo.html_url in invited["body"]
        assert '"bob"' in invited["body"]
        # the 404-means-log-in note survives edits to the template
        assert "404" in invited["body"]
        assert "logged in" in invited["body"]
        # every message ends with the do-not-respond footer
        for conversation in env.canvas.conversations:
            assert conversation["body"].endswith(
                "**You DO NOT need to respond to this email."
                " It is for your information.**")
        assert '"ghost"' in by_recipient["3"]["body"]
        assert "add it now" in by_recipient["4"]["body"]
        # the link-must-be-named-github instruction survives template edits
        assert "name (Title) is exactly" in by_recipient["4"]["body"]

    def test_bad_link_message_shows_the_url_form(self, env):
        run(env.runner, "canvas", "message-missing", ORG, "project",
            "--no-dryrun")
        body = next(c["body"] for c in env.canvas.conversations
                    if c["recipients"] == ["3"])
        assert "https://github.com/ghost" in body
        assert "https://github.com/YOUR-USERNAME" in body

    def test_messaging_never_touches_github_invitations(self, env):
        run(env.runner, "canvas", "message-missing", ORG, "project",
            "--no-dryrun")
        assert env.repo.collab_log == []

    def test_a_reserved_route_link_is_a_bad_link_without_an_api_check(self, env):
        # github.com/settings is github's own page, never an account — the
        # classification must not depend on a user-existence lookup
        env.canvas._enrollments.append(
            _student("6", "Gina Cruz", "gina@sjsu.edu"))
        env.canvas._profiles["6"] = {"links": [{"url": "https://github.com/settings"}]}
        result = run(env.runner, "canvas", "message-missing", ORG, "project")
        assert "would message Gina Cruz <gina@sjsu.edu> (bad-link)" in result.output

    def test_no_access_and_no_invite_is_a_loud_error(self, env):
        env.canvas._enrollments.append(
            _student("5", "Frank Field", "frank@sjsu.edu"))
        env.canvas._profiles["5"] = {"links": [{"url": "https://github.com/frank"}]}
        result = run(env.runner, "canvas", "message-missing", ORG, "project",
                     "--no-dryrun")
        assert result.exit_code == 1
        assert "Frank Field (frank) is not a collaborator" in result.output
        assert "meta apply" in result.output
        # frank gets no canvas message: only the instructor can fix this
        recipients = [c["recipients"][0] for c in env.canvas.conversations]
        assert "5" not in recipients

    def test_errors_print_after_the_messages(self, env):
        # held to the end so they aren't torn apart by the progress bars
        env.canvas._enrollments.append(
            _student("5", "Frank Field", "frank@sjsu.edu"))
        env.canvas._profiles["5"] = {"links": [{"url": "https://github.com/frank"}]}
        result = run(env.runner, "canvas", "message-missing", ORG, "project",
                     "--no-dryrun")
        lines = result.output.splitlines()
        last_message = max(i for i, line in enumerate(lines)
                           if line.startswith("message "))
        frank = next(i for i, line in enumerate(lines)
                     if "Frank Field" in line)
        assert frank > last_message

    def test_collaborators_are_never_messaged(self, env):
        run(env.runner, "canvas", "message-missing", ORG, "project",
            "--no-dryrun")
        recipients = [c["recipients"][0] for c in env.canvas.conversations]
        assert "1" not in recipients  # alice already collaborates

    def test_nothing_to_do_when_everyone_collaborates(self, env):
        env.canvas._enrollments = [_student("1", "Alice Adams", "alice@sjsu.edu")]
        result = run(env.runner, "canvas", "message-missing", ORG, "project",
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output
        assert env.canvas.conversations == []

    def test_canvas_test_student_is_ignored(self, env):
        # canvas's "Student View" test student enrolls with role
        # StudentEnrollment but type StudentViewEnrollment; it is not a
        # person and canvas refuses to message it
        env.canvas._enrollments.append(
            {"type": "StudentViewEnrollment",
             "role": {"name": "StudentEnrollment"},
             "user": {"_id": "99", "name": "Test Student", "email": None},
             "courseSectionId": "s1"})
        result = run(env.runner, "canvas", "message-missing", ORG, "project")
        assert result.exit_code == 0, result.output
        assert "Test Student" not in result.output

    def test_a_failed_send_errors_at_the_end_and_continues(self, env):
        env.canvas.reject_recipients = {"2"}  # bob
        result = run(env.runner, "canvas", "message-missing", ORG, "project",
                     "--no-dryrun")
        assert result.exit_code == 1, result.output
        assert "cannot message Bob Baker" in result.output
        # the other stranded students were still messaged
        recipients = [c["recipients"][0] for c in env.canvas.conversations]
        assert set(recipients) == {"3", "4"}
        # and the failure prints after the message lines, like every held error
        lines = result.output.splitlines()
        last_sent = max(i for i, line in enumerate(lines)
                        if line.startswith("message "))
        failed = next(i for i, line in enumerate(lines)
                      if "cannot message" in line)
        assert failed > last_sent

    def test_errors_without_canvas_config(self, env, tmp_path, monkeypatch):
        config = tmp_path / "orgs-only.ini"
        config.write_text(f"[ORGS]\n{ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(config))
        result = run(env.runner, "canvas", "message-missing", ORG, "project")
        assert result.exit_code == 2
        assert "[CANVAS]" in result.output
