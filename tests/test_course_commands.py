"""course, assignment create, and sync: the course-centered command tree."""
import pytest

from gh_class_sak import core
from gh_class_sak import meta_store as ms
from gh_class_sak.commands import course as course_cmd
from tests.conftest import ORG, run
from tests.fakes import FakeNamedUser, FakeRepo, FakeTeam
from tests.test_meta_commands import (  # noqa: F401  - env is a fixture
    ASSIGNMENT,
    COURSE,
    PREFIX,
    REPO_PREFIX,
    env,
    meta_state,
    seed_meta,
)


@pytest.fixture
def course_env(env, monkeypatch):
    monkeypatch.setattr(course_cmd, "get_github", lambda: env.gh)
    return env


@pytest.fixture
def configured(course_env, tmp_path, monkeypatch):
    """the same env with ORG listed in the config's [ORGS]."""
    path = tmp_path / "gh-class-sak.ini"
    path.write_text(f"[ORGS]\n{ORG}\n")
    monkeypatch.setattr(core, "config_ini", str(path))
    return course_env


def team_row(assignment=ASSIGNMENT, name="team-1", students=("/msmith",)):
    return {assignment: [{"name": name, "students": list(students),
                          "repo": None, "repo_id": None}]}


class TestResolveCourse:
    def test_no_config_and_no_org_asks_for_org(self, course_env):
        result = run(course_env.runner, "course", "show", COURSE)
        assert result.exit_code == 2
        assert f'which org hosts course "{COURSE}"? pass --org ORG' in result.output

    def test_a_partial_course_name_is_found_in_the_configured_orgs(self, configured):
        seed_meta(configured)
        result = run(configured.runner, "course", "show", "195a")
        assert result.exit_code == 0, result.output
        assert f"PREFIX    {PREFIX}" in result.output

    def test_an_org_name_is_not_a_course(self, configured):
        seed_meta(configured)
        result = run(configured.runner, "course", "show", ORG)
        assert result.exit_code == 2
        assert f'no course "{ORG}" recorded in {ORG}' in result.output
        assert f"looks like an org: pass it as --org {ORG}" in result.output

    def test_an_exact_name_beats_a_partial_one(self, configured):
        seed_meta(configured)
        seed_meta(configured, course=f"{COURSE}_lab", prefix="lab")
        result = run(configured.runner, "course", "show", COURSE)
        assert result.exit_code == 0, result.output
        assert f"PREFIX    {PREFIX}" in result.output

    def test_an_org_without_a_meta_repo_is_reported(self, course_env):
        result = run(course_env.runner, "course", "show", COURSE, "--org", ORG)
        assert result.exit_code == 2
        assert f'no classroom-meta repo visible in "{ORG}"' in result.output


class TestCourse:
    def test_init_records_the_course(self, course_env):
        result = run(course_env.runner, "course", "init", "CS-101", "--org", ORG,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env, "cs_101")["prefix"] == "CS-101"

    def test_list_every_course_in_the_org(self, course_env):
        seed_meta(course_env, assignments=team_row())
        seed_meta(course_env, course="cs_101", prefix="cs101")
        result = run(course_env.runner, "course", "list", "--org", ORG)
        assert result.exit_code == 0, result.output
        assert COURSE in result.output and "cs_101" in result.output
        assert f"{ASSIGNMENT}(1)" in result.output

    def test_list_one_course(self, course_env):
        seed_meta(course_env)
        seed_meta(course_env, course="cs_101", prefix="cs101")
        result = run(course_env.runner, "course", "list", "cs_101", "--org", ORG)
        assert result.exit_code == 0, result.output
        assert "cs_101" in result.output and COURSE not in result.output

    def test_list_without_orgs_asks_for_one(self, course_env):
        result = run(course_env.runner, "course", "list")
        assert result.exit_code == 2
        assert "pass --org ORG" in result.output

    def test_delete_an_empty_course(self, course_env):
        seed_meta(course_env)
        result = run(course_env.runner, "course", "delete", COURSE, "--org", ORG,
                     "--no-dryrun", input="y\n")
        assert result.exit_code == 0, result.output
        assert ms.load_meta_classrooms(course_env.gh, ORG) == {}


class TestAssignmentCreate:
    def test_creates_the_repos_from_a_roster(self, course_env, tmp_path):
        seed_meta(course_env)
        roster = tmp_path / "anything.tsv"
        roster.write_text("NAME\tSTUDENTS\nteam-1\t/msmith\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster), "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = course_env.gh.get_repo(f"{ORG}/{PREFIX}-hw1-team-1")
        assert ("add", "msmith", "push") in created.collab_log
        # the NAME argument names the assignment, not the roster file
        [row] = meta_state(course_env)["assignments"]["hw1"]
        assert row["repo_id"] == created.id

    def test_needs_a_roster_source(self, course_env):
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG)
        assert result.exit_code == 2
        assert "pass --roster FILE, --from-canvas" in result.output

    def test_roster_and_canvas_are_exclusive(self, course_env, tmp_path):
        roster = tmp_path / "hw1.tsv"
        roster.write_text("NAME\tSTUDENTS\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster), "--from-canvas")
        assert result.exit_code == 2
        assert "--from-canvas replaces --roster" in result.output

    def test_canvas_group_needs_from_canvas(self, course_env, tmp_path):
        roster = tmp_path / "hw1.tsv"
        roster.write_text("NAME\tSTUDENTS\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster),
                     "--canvas-group", "Teams")
        assert result.exit_code == 2
        assert "--canvas-group only makes sense with --from-canvas" in result.output


class TestSync:
    def test_syncs_one_course(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = course_env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert meta_state(course_env)["assignments"][ASSIGNMENT][0]["repo_id"] \
            == created.id

    def test_syncs_every_course_in_the_org(self, course_env):
        seed_meta(course_env, assignments=team_row())
        seed_meta(course_env, course="cs_101", prefix="cs101",
                  assignments=team_row("hw1", "solo"))
        result = run(course_env.runner, "sync", "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        course_env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        course_env.gh.get_repo(f"{ORG}/cs101-hw1-solo")

    def test_needs_a_course_or_an_org(self, course_env):
        result = run(course_env.runner, "sync")
        assert result.exit_code == 2
        assert "pass a COURSE, or --org ORG" in result.output


class TestAssignmentCreateScope:
    """assignment create sets up its own repos; the rest of the course is
    sync's job."""

    def roster(self, tmp_path):
        path = tmp_path / "roster.tsv"
        path.write_text("NAME\tSTUDENTS\nteam-1\t/msmith\n")
        return str(path)

    def test_leaves_other_assignments_repos_alone(self, course_env, tmp_path):
        other = FakeRepo(ORG, f"{PREFIX}-hw0-solo")  # jdoe not invited yet
        course_env.org._repos.append(other)
        seed_meta(course_env, assignments={"hw0": [
            {"name": "solo", "students": ["/jdoe"],
             "repo": other.html_url, "repo_id": other.id}]})
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", self.roster(tmp_path),
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert other.collab_log == []

    def test_the_tas_team_reads_the_new_repos_and_nothing_else_changes(
            self, course_env, tmp_path):
        stray = FakeRepo(ORG, "unrelated")
        team = FakeTeam(course_env.org, f"{COURSE}-tas")
        team._members["old-ta"] = FakeNamedUser("old-ta")  # not in [TAS]
        team._repos[stray.full_name] = (stray, "pull")
        course_env.org._teams[team.slug] = team
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", self.roster(tmp_path),
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert team.log == [("grant", f"{ORG}/{PREFIX}-hw1-team-1", "pull")]

    def test_a_missing_tas_team_is_left_to_sync(self, course_env, tmp_path):
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", self.roster(tmp_path),
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert course_env.org._teams == {}
        assert f'team "{COURSE}-TAs" is missing; run: gh-class-sak sync' \
            f" {COURSE}" in result.output


class TestRenamedCommands:
    """the old names still work, hidden from --help, with a hint for humans."""

    def test_old_names_are_hidden_from_help(self, course_env):
        result = run(course_env.runner, "--help")
        commands = result.output.split("Commands:")[1].split()
        assert "meta" not in commands and "classrooms" not in commands
        assert "course" in commands and "sync" in commands

    @pytest.mark.parametrize("old, new", [
        (["meta", "show", ORG], "gh-class-sak course show COURSE"),
        (["meta", "apply", ORG], "gh-class-sak sync COURSE"),
        (["meta", "list", ORG], "gh-class-sak course list"),
        (["classrooms", ORG], "gh-class-sak course list"),
    ])
    def test_a_terminal_user_is_told_the_new_name(self, course_env, monkeypatch,
                                                  old, new):
        seed_meta(course_env)
        monkeypatch.setattr(core, "_interactive", lambda: True)
        result = run(course_env.runner, *old)
        assert result.exit_code == 0, result.output
        assert f"is renamed: use {new}" in result.output

    def test_scripts_see_no_hint(self, course_env):
        seed_meta(course_env)
        result = run(course_env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert "renamed" not in result.output


class TestInitRemembersTheOrg:
    def test_the_org_is_added_to_the_config(self, course_env):
        result = run(course_env.runner, "course", "init", "CS-101", "--org", ORG,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert f"add {ORG} to the config's [ORGS]" in result.output
        assert core.configured_orgs() == [ORG]
        # so the next command finds the course without --org
        result = run(course_env.runner, "course", "show", "CS-101")
        assert result.exit_code == 0, result.output

    def test_a_dry_run_leaves_the_config_alone(self, course_env):
        result = run(course_env.runner, "course", "init", "CS-101", "--org", ORG)
        assert result.exit_code == 0, result.output
        assert f"would add {ORG} to the config's [ORGS]" in result.output
        assert core.configured_orgs() == []

    def test_a_configured_org_is_not_added_again(self, configured):
        result = run(configured.runner, "course", "init", "CS-101", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "[ORGS]" not in result.output
        assert core.configured_orgs() == [ORG]

    def test_meta_init_is_unchanged(self, course_env):
        result = run(course_env.runner, "meta", "init", "CS-101", "--org", ORG,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert core.configured_orgs() == []


PREVIEW_FOOTER = ("that was a preview: nothing changed."
                  " add --no-dryrun to apply")


class TestNextSteps:
    def test_a_dry_run_ends_by_saying_nothing_changed(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert result.output.rstrip().endswith(PREVIEW_FOOTER)

    def test_a_dry_run_with_nothing_to_preview_has_no_footer(self, course_env):
        seed_meta(course_env)
        run(course_env.runner, "sync", COURSE, "--org", ORG, "--no-dryrun")
        result = run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output
        assert PREVIEW_FOOTER not in result.output

    def test_the_renamed_commands_print_no_footer(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "meta", "apply", ORG)
        assert result.exit_code == 0, result.output
        assert PREVIEW_FOOTER not in result.output
        assert "summary:" not in result.output

    def test_init_names_the_next_step(self, course_env):
        result = run(course_env.runner, "course", "init", "CS-101", "--org", ORG,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "next: gh-class-sak assignment create cs_101 NAME --roster FILE" \
            " (or --from-canvas)" in result.output

    def test_assignment_create_names_the_next_step(self, course_env, tmp_path):
        seed_meta(course_env)
        roster = tmp_path / "roster.tsv"
        roster.write_text("NAME\tSTUDENTS\nteam-1\t/msmith\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster), "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert f"next: students accept their invitations; gh-class-sak course" \
            f" show {COURSE} shows who hasn't" in result.output


class TestSummary:
    def test_sync_ends_with_a_summary(self, course_env):
        seed_meta(course_env, assignments={ASSIGNMENT: [
            {"name": "team-1", "students": ["/msmith"], "repo": None, "repo_id": None},
            {"name": "team-2", "students": ["/jdoe"], "repo": None, "repo_id": None}]})
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert result.output.rstrip().splitlines()[-1] == (
            "summary: 2 repos created, 2 welcome commits, 2 branches protected,"
            " 2 invitations, 3 TA team changes")

    def test_a_dry_run_summary_says_so(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert "summary (preview): 1 repo created," in result.output

    def test_warnings_are_counted(self, course_env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("msmith", role_name="write"),
            FakeNamedUser("stranger", role_name="write")])
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            {"name": "team-1", "students": ["/msmith"],
             "repo": repo.html_url, "repo_id": repo.id}]})
        run(course_env.runner, "sync", COURSE, "--org", ORG, "--no-dryrun")
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output
        assert result.output.rstrip().endswith("summary: no changes, 1 warning")
