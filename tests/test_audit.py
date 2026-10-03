"""the audit trail (what the tool changed on github, and why) and course
audit (who has access, checked against who should)."""
import os

import pytest

from gh_class_sak import meta_store as ms
from gh_class_sak.commands import course as course_cmd
from gh_class_sak.commands import meta as meta_cmd
from tests.conftest import ORG, run
from tests.fakes import FakeNamedUser, FakeRepo, FakeTeam
from tests.test_meta_commands import ASSIGNMENT, COURSE, REPO_PREFIX, seed_meta


@pytest.fixture
def course_env(env, monkeypatch):
    monkeypatch.setattr(course_cmd, "get_github", lambda: env.gh)
    monkeypatch.setattr(course_cmd, "get_token", lambda: None)
    return env


def audit_lines(env, course=COURSE):
    """the course's audit.log as pushed to the classroom-meta origin."""
    work = ms.checkout_meta(str(env.root / "classroom-meta.git"), "audit-read")
    path = os.path.join(work, course, "audit.log")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        rows = [line.split("\t") for line in f.read().splitlines()]
    assert rows[0] == ["TIME", "BY", "COMMAND", "ACTION", "REPO", "WHO", "WHY"]
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def row(name, *students, repo=None):
    return {"name": name, "students": list(students),
            "repo": repo.html_url if repo else None,
            "repo_id": repo.id if repo else None}


class TestAuditTrail:
    def test_sync_logs_each_repo_and_invitation_with_the_reason(self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [row("team-1", "/msmith")]})
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        assert result.exit_code == 0, result.output
        lines = audit_lines(course_env)
        repo = f"{ORG}/{REPO_PREFIX}-team-1"
        created = [x for x in lines if x["ACTION"] == "create repo"]
        assert created and created[0]["REPO"] == repo
        assert created[0]["WHY"] == f"{ASSIGNMENT}.tsv row team-1"
        [invite] = [x for x in lines if x["ACTION"] == "invite"]
        assert (invite["REPO"], invite["WHO"]) == (repo, "msmith")
        assert invite["WHY"] == f"{ASSIGNMENT}.tsv row team-1: /msmith"
        assert invite["BY"] == "profbeth"  # the token's login
        assert invite["COMMAND"] == "gh-class-sak sync"
        assert invite["TIME"].endswith("Z")

    def test_an_id_found_through_canvas_says_so(self, course_env, monkeypatch):
        # the way a wrong account gets in: an email-only row whose github id
        # comes from the student's canvas profile link
        monkeypatch.setattr(meta_cmd, "_make_resolver", lambda org, course: (
            lambda entry: "stranger" if entry == "jane@sjsu.edu/"
            else ms.parse_identity(entry)[1]))
        seed_meta(course_env, assignments={ASSIGNMENT: [row("team-1", "jane@sjsu.edu/")]})
        run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        [invite] = [x for x in audit_lines(course_env) if x["ACTION"] == "invite"]
        assert invite["WHO"] == "stranger"
        assert invite["WHY"] == (f"{ASSIGNMENT}.tsv row team-1: jane@sjsu.edu/"
                                 " (github id from the canvas profile link)")

    def test_a_dry_run_logs_nothing(self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [row("team-1", "/msmith")]})
        run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert audit_lines(course_env) == []

    def test_a_revoke_is_logged_with_its_reason(self, course_env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("msmith", role_name="write"),
            FakeNamedUser("stranger", role_name="write")])
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "/msmith", repo=repo)]})
        run(course_env.runner, "sync", COURSE, "--org", ORG,
            "--remove-unlisted-contributors", "--apply")
        [revoke] = [x for x in audit_lines(course_env) if x["ACTION"] == "revoke"]
        assert revoke["WHO"] == "stranger"
        assert revoke["WHY"] == f"not listed in {ASSIGNMENT}.tsv row team-1"

    def test_a_grant_that_fails_is_not_logged(self, course_env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", reject_collaborators=["typo"])
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "/typo", "/msmith", repo=repo)]})
        run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        invited = [x["WHO"] for x in audit_lines(course_env) if x["ACTION"] == "invite"]
        assert invited == ["msmith"]

    def test_ta_team_changes_are_logged(self, course_env):
        team = FakeTeam(course_env.org, f"{COURSE}-tas")
        course_env.org._teams[team.slug] = team
        seed_meta(course_env, tas=["/ta-one"])
        run(course_env.runner, "course", "ta", "add", COURSE, "/ta-two",
            "--org", ORG, "--apply")
        added = {x["WHO"]: x for x in audit_lines(course_env)
                 if x["ACTION"] == "add to TAs team"}
        assert added["ta-two"]["WHY"] == "[TAS] /ta-two"
        assert added["ta-two"]["COMMAND"] == "gh-class-sak course ta add"

    def test_a_run_that_fails_midway_still_logs_what_it_did(self, course_env,
                                                            monkeypatch):
        # the first invite happens, then github fails the second: that invite
        # is real and must be logged, but the half-done roster isn't committed
        from github import GithubException
        real = meta_cmd.add_collaborator
        calls = []

        def flaky(repo, login, permission):
            calls.append(login)
            if len(calls) > 1:
                raise GithubException(500, {"message": "Server Error"}, None)
            return real(repo, login, permission)
        monkeypatch.setattr(meta_cmd, "add_collaborator", flaky)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "/msmith", "/jdoe")]})
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        assert result.exit_code != 0
        lines = audit_lines(course_env)
        assert [x["WHO"] for x in lines if x["ACTION"] == "invite"] == ["msmith"]
        assert any(x["ACTION"] == "create repo" for x in lines)
        data = ms.load_meta_classrooms(course_env.gh, ORG)[COURSE]
        assert data["assignments"][ASSIGNMENT][0]["repo_id"] is None

    def test_the_log_is_never_read_as_an_assignment(self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [row("team-1", "/msmith")]})
        run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        assert audit_lines(course_env)
        data = ms.load_meta_classrooms(course_env.gh, ORG)[COURSE]
        assert list(data["assignments"]) == [ASSIGNMENT]


def canvas(monkeypatch, *people):
    """the canvas roster the audit checks against."""
    monkeypatch.setattr(meta_cmd, "_canvas_people", lambda org, course: list(people))


class TestCourseAudit:
    def test_someone_no_row_lists_is_flagged_with_the_fix(self, course_env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("msmith", role_name="write")], invitations=["stranger"])
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "/msmith", repo=repo)]})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 1
        assert (f"{ASSIGNMENT}/team-1: stranger is invited to {repo.full_name}"
                " but no row lists them") in result.output
        assert (f"fix: gh-class-sak sync {COURSE} --org {ORG}"
                " --remove-unlisted-contributors --apply") in result.output

    def test_one_account_on_two_rows_is_flagged(self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "a@sjsu.edu/msmith"), row("team-2", "b@sjsu.edu/msmith")]})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 1
        assert (f"{ASSIGNMENT}: msmith is on 2 rows (team-1, team-2) for"
                " different people") in result.output

    def test_an_account_whose_name_is_not_the_students_is_flagged(
            self, course_env, monkeypatch):
        course_env.gh._users["stranger"] = FakeNamedUser("stranger", name="Bob Stone")
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "jane@sjsu.edu/stranger")]})
        canvas(monkeypatch, {"name": "Jane Doe", "email": "jane@sjsu.edu",
                             "github": "stranger"})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 1
        # canvas rows can be instructors and TAs too: "person", not "student"
        assert (f'{ASSIGNMENT}/team-1: stranger is named "Bob Stone" on GitHub,'
                ' but Canvas has them as "Jane Doe" (jane@sjsu.edu)') in result.output

    def test_a_recorded_id_canvas_no_longer_links_is_flagged(
            self, course_env, monkeypatch):
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "jane@sjsu.edu/stranger")]})
        canvas(monkeypatch, {"name": "Jane Doe", "email": "jane@sjsu.edu",
                             "github": "janedoe"})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 1
        assert (f"{ASSIGNMENT}/team-1: recorded stranger for jane@sjsu.edu, but"
                " their Canvas profile now links janedoe") in result.output
        assert (f"fix: gh-class-sak assignment create {COURSE} {ASSIGNMENT}"
                f" --org {ORG} --from-canvas --apply") in result.output

    def test_a_course_where_everyone_checks_out(self, course_env, monkeypatch):
        course_env.gh._users["janedoe"] = FakeNamedUser("janedoe", name="Jane Doe")
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("janedoe", role_name="write")])
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            row("team-1", "jane@sjsu.edu/janedoe", repo=repo)]})
        canvas(monkeypatch, {"name": "Jane Doe", "email": "jane@sjsu.edu",
                             "github": "janedoe"})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert f"audit {COURSE}: no problems found" in result.output

    def test_without_canvas_the_canvas_checks_say_they_were_skipped(
            self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [row("team-1", "/msmith")]})
        result = run(course_env.runner, "course", "audit", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert ("name and Canvas-link checks skipped: no [CANVAS] section"
                " in the config") in result.output


class TestNameCheckOnlyFlagsNoOverlap:
    """github names are free-form — first names, nicknames, handles — so the
    name check flags only an account that shares no part of the student's
    name. these shapes come from a real roster, with made-up names."""

    @pytest.mark.parametrize("login, github_name, canvas_name", [
        ("codebysam", "Sam", "Sam Rivera"),              # first name only
        ("jriv2022", "Jriv2022", "Jordan Riv"),          # surname in the login
        ("lee-dev", "lee koker", "Mina Koker"),          # goes by another first name
        ("mira-ray", "Mira", "Mira Anne Ray"),           # middle name left out
        ("kwan88", "Hao Lu", "Lina Lu"),                 # a two-letter surname
        ("pkandala0103", "Px_0103", "Priya Kandala"),    # handle; name in the login
        ("Jose-Nunez", "José Núñez", "Jose Nunez"),      # accents
        ("pixel2018", "minan", "Mina Nall"),             # name run together
        ("wxm2024", "王小明", "王小明"),                     # non-latin scripts
        ("ivan-p", "Иван Петров", "Иван Петров"),
    ])
    def test_a_plausible_account_is_not_flagged(self, login, github_name,
                                                canvas_name):
        assert meta_cmd._looks_like(github_name, login, canvas_name)

    @pytest.mark.parametrize("login, github_name, canvas_name", [
        ("stranger", "Bob Stone", "Jane Doe"),
        ("unuser-null", "Unuser_", "Elias Marco Canon"),
    ])
    def test_an_account_with_nothing_in_common_is_flagged(self, login,
                                                          github_name,
                                                          canvas_name):
        assert not meta_cmd._looks_like(github_name, login, canvas_name)


class TestAuditAfterSync:
    def unlisted(self, env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("msmith", role_name="write"),
            FakeNamedUser("stranger", role_name="write")])
        env.org._repos.append(repo)
        seed_meta(env, assignments={ASSIGNMENT: [row("team-1", "/msmith", repo=repo)]})

    def test_a_real_sync_ends_with_the_audit(self, course_env):
        self.unlisted(course_env)
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        assert result.exit_code == 0, result.output  # the audit doesn't fail sync
        assert f"audit {COURSE}: 1 problem" in result.output
        assert "stranger has access to" in result.output

    def test_a_dry_run_sync_does_not_audit(self, course_env):
        self.unlisted(course_env)
        result = run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert f"audit {COURSE}" not in result.output

    def test_the_renamed_meta_apply_does_not_audit(self, course_env):
        self.unlisted(course_env)
        result = run(course_env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert f"audit {COURSE}" not in result.output
