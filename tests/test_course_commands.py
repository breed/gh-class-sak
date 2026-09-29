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
    monkeypatch.setattr(course_cmd, "get_token", lambda: None)
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
                  " add --apply to make these changes")


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


class TestCourseTas:
    def ta_team(self, env, *members):
        team = FakeTeam(env.org, f"{COURSE}-tas")
        for login in members:
            team._members[login] = FakeNamedUser(login)
        env.org._teams[team.slug] = team
        return team

    def test_add_records_the_ta_and_invites_them_to_the_team(self, course_env):
        team = self.ta_team(course_env, "ta-one")
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "course", "ta", "add", COURSE, "ta-two",
                     "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env)["tas"] == ["/ta-one", "/ta-two"]
        assert team.log == [("add-member", "ta-two")]
        assert "summary: 1 record updated, 1 TA team change" in result.output

    def test_add_is_a_dry_run_by_default(self, course_env):
        team = self.ta_team(course_env, "ta-one")
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "course", "ta", "add", COURSE, "/ta-two",
                     "--org", ORG)
        assert result.exit_code == 0, result.output
        assert f"would record {COURSE} tas: /ta-one, /ta-two" in result.output
        assert f'would add ta-two to team "{COURSE}-TAs"' in result.output
        assert meta_state(course_env)["tas"] == ["/ta-one"]
        assert team.log == []

    def test_adding_a_current_ta_changes_nothing(self, course_env):
        self.ta_team(course_env, "ta-one")
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "course", "ta", "add", COURSE, "TA-One",
                     "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "/TA-One is already a TA" in result.output
        assert "nothing to do" in result.output

    def test_remove_drops_the_ta_from_record_and_team(self, course_env):
        team = self.ta_team(course_env, "ta-one", "ta-two")
        seed_meta(course_env, tas=["/ta-one", "ta2@sjsu.edu/ta-two"])
        result = run(course_env.runner, "course", "ta", "remove", COURSE, "ta-two",
                     "--org", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env)["tas"] == ["/ta-one"]
        assert team.log == [("remove-member", "ta-two")]

    def test_removing_someone_who_is_not_a_ta_is_an_error(self, course_env):
        seed_meta(course_env, tas=["/ta-one"])
        result = run(course_env.runner, "course", "ta", "remove", COURSE, "nobody",
                     "--org", ORG, "--no-dryrun")
        assert result.exit_code == 2
        assert '"nobody" is not a TA of' in result.output
        assert meta_state(course_env)["tas"] == ["/ta-one"]


class TestCourseSettings:
    def test_without_options_it_shows_the_settings(self, course_env):
        seed_meta(course_env, template=f"{ORG}/Template")
        result = run(course_env.runner, "course", "settings", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert "protection=none linear_history=true force_push=false" \
            in result.output
        assert f"template={ORG}/Template" in result.output
        assert "dry run" not in result.output

    def test_protection_is_recorded_and_applied(self, course_env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1")
        course_env.org._repos.append(repo)
        seed_meta(course_env, assignments={ASSIGNMENT: [
            {"name": "team-1", "students": ["/msmith"],
             "repo": repo.html_url, "repo_id": repo.id}]})
        result = run(course_env.runner, "course", "settings", COURSE, "--org", ORG,
                     "--protection", "pr-review", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env)["protection"] == "pr-review"
        assert len(repo.protection_log) == 1
        assert "summary: 1 record updated, 1 branch protected" in result.output

    def test_a_template_is_recorded(self, course_env):
        seed_meta(course_env)
        result = run(course_env.runner, "course", "settings", COURSE, "--org", ORG,
                     "--template", f"{ORG}/Template", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env)["template"] == f"{ORG}/Template"

    def test_an_unchanged_setting_is_nothing_to_do(self, course_env):
        seed_meta(course_env, protection="pr-review")
        result = run(course_env.runner, "course", "settings", COURSE, "--org", ORG,
                     "--protection", "pr-review", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output


class TestHelpOrder:
    """--help lists commands in the order they're used, not alphabetically."""

    def listed(self, runner, *group):
        result = run(runner, *group, "--help")
        assert result.exit_code == 0, result.output
        section = result.output.split("Commands:")[1]
        return [line.split()[0] for line in section.splitlines() if line.strip()]

    def test_top_level_starts_with_setup(self, course_env):
        assert self.listed(course_env.runner) == [
            "help-me-setup", "demo", "course", "assignment", "sync", "repos",
            "canvas", "migrate-github-classroom", "completion"]

    def test_course_starts_with_init(self, course_env):
        assert self.listed(course_env.runner, "course") == [
            "init", "list", "status", "show", "ta", "settings", "delete"]

    def test_course_ta(self, course_env):
        assert self.listed(course_env.runner, "course", "ta") == ["add", "remove"]

    def test_repos(self, course_env):
        assert self.listed(course_env.runner, "repos") == [
            "list", "clone", "members", "missing"]


class TestApply:
    def test_apply_is_the_same_as_no_dryrun(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "sync", COURSE, "--org", ORG, "--apply")
        assert result.exit_code == 0, result.output
        assert "dry run" not in result.output
        course_env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")

    def test_the_preview_suggests_apply(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "sync", COURSE, "--org", ORG)
        assert result.output.startswith(
            "⚠️  dry run: no changes will be made. add --apply to make them")

    def test_the_renamed_commands_keep_their_banner(self, course_env):
        seed_meta(course_env, assignments=team_row())
        result = run(course_env.runner, "meta", "apply", ORG)
        assert result.output.startswith(
            "⚠️  dry run: no changes will be made. add --no-dryrun to apply")

    def test_course_settings_takes_apply(self, course_env):
        seed_meta(course_env)
        result = run(course_env.runner, "course", "settings", COURSE, "--org", ORG,
                     "--template", f"{ORG}/Template", "--apply")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env)["template"] == f"{ORG}/Template"


def _visible_leaves(group, path=()):
    for name in group.list_commands(None):
        cmd = group.get_command(None, name)
        if cmd.hidden:
            continue
        if hasattr(cmd, "list_commands"):
            yield from _visible_leaves(cmd, path + (name,))
        else:
            yield path + (name,)


@pytest.mark.parametrize("path", list(_visible_leaves(core.gh_class_sak)),
                         ids=lambda path: " ".join(path))
def test_every_command_shows_examples_in_its_help(course_env, path):
    result = run(course_env.runner, *path, "--help")
    assert result.exit_code == 0, result.output
    assert "Examples:" in result.output
    assert f"  gh-class-sak {' '.join(path)}" in result.output


class TestRosterInput:
    def test_a_plain_list_roster_creates_one_repo_per_person(self, course_env,
                                                               tmp_path):
        seed_meta(course_env)
        roster = tmp_path / "people.txt"
        roster.write_text("/msmith\n/jdoe\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster), "--apply")
        assert result.exit_code == 0, result.output
        course_env.gh.get_repo(f"{ORG}/{PREFIX}-hw1-msmith")
        course_env.gh.get_repo(f"{ORG}/{PREFIX}-hw1-jdoe")

    def test_a_bad_roster_shows_both_formats(self, course_env, tmp_path):
        seed_meta(course_env)
        roster = tmp_path / "roster.tsv"
        roster.write_text("team-1 /jdoe - oops\n")
        result = run(course_env.runner, "assignment", "create", COURSE, "hw1",
                     "--org", ORG, "--roster", str(roster))
        assert result.exit_code == 2
        assert "cannot read the roster: line 1: REPO_ID" in result.output
        assert "one person per line" in result.output
        assert "NAME       STUDENTS" in result.output


class TestCourseStatus:
    def test_counts_repos_and_invitations_and_says_what_to_do(self, course_env):
        done = FakeRepo(ORG, f"{PREFIX}-hw1-msmith", collaborators=[
            FakeNamedUser("msmith", role_name="write")])
        waiting = FakeRepo(ORG, f"{PREFIX}-hw1-jdoe", invitations=["jdoe"])
        course_env.org._repos += [done, waiting]
        team = FakeTeam(course_env.org, f"{COURSE}-tas")
        course_env.org._teams[team.slug] = team
        seed_meta(course_env, assignments={"hw1": [
            {"name": "msmith", "students": ["/msmith"],
             "repo": done.html_url, "repo_id": done.id},
            {"name": "jdoe", "students": ["/jdoe"],
             "repo": waiting.html_url, "repo_id": waiting.id},
            {"name": "late", "students": ["/late"], "repo": None, "repo_id": None}]})
        result = run(course_env.runner, "course", "status", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert "ASSIGNMENT  REPOS  ACCEPTED  INVITED  NOT INVITED" in result.output
        assert "hw1         2/3    1         1        0" in result.output
        assert f"TAS TEAM  {COURSE}-TAs (matches tas)" in result.output
        assert (f"  hw1: 1 row without a recorded repo → gh-class-sak sync {COURSE} --apply"
                in result.output)
        assert (f"  hw1: 1 invitation not accepted yet → gh-class-sak course show"
                f" {COURSE} lists who" in result.output)

    def test_a_course_with_nothing_left_says_so(self, course_env):
        done = FakeRepo(ORG, f"{PREFIX}-hw1-msmith", collaborators=[
            FakeNamedUser("msmith", role_name="write")])
        course_env.org._repos.append(done)
        course_env.org._teams[f"{COURSE}-tas"] = FakeTeam(course_env.org,
                                                          f"{COURSE}-tas")
        seed_meta(course_env, assignments={"hw1": [
            {"name": "msmith", "students": ["/msmith"],
             "repo": done.html_url, "repo_id": done.id}]})
        result = run(course_env.runner, "course", "status", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert "all set: every repo exists and every student has accepted" \
            in result.output

    def test_a_new_course_points_at_assignment_create(self, course_env):
        seed_meta(course_env)
        result = run(course_env.runner, "course", "status", COURSE, "--org", ORG)
        assert result.exit_code == 0, result.output
        assert (f"no assignments yet → gh-class-sak assignment create {COURSE}"
                " NAME --from-canvas" in result.output)
        assert f"TAS TEAM  {COURSE}-TAs (not created" in result.output
        assert f"TAs team → gh-class-sak sync {COURSE} --apply" in result.output


class TestInitLike:
    STARTER = "https://github.com/example/hw1-starter"

    def seed_last_term(self, env):
        seed_meta(env, course="cs_101", prefix="cs101-spring",
                  template=f"{ORG}/Template", tas=["/ta-one", "ta2@sjsu.edu/ta-two"],
                  templates={"hw1": self.STARTER}, protection="pr-review",
                  assignments=team_row("hw1", "solo"))

    def test_copies_tas_templates_and_settings_but_not_prefix_or_rows(
            self, course_env):
        self.seed_last_term(course_env)
        result = run(course_env.runner, "course", "init", "CS-102", "--org", ORG,
                     "--like", "cs_101", "--apply")
        assert result.exit_code == 0, result.output
        new = meta_state(course_env, "cs_102")
        assert new["tas"] == ["/ta-one", "ta2@sjsu.edu/ta-two"]
        assert new["template"] == f"{ORG}/Template"
        assert new["templates"] == {"hw1": self.STARTER}
        assert new["protection"] == "pr-review"
        assert new["prefix"] == "CS-102"
        assert new["assignments"] == {}
        assert "copying from cs_101: TAs, template, repo settings" in result.output

    def test_an_explicit_flag_beats_the_copy(self, course_env):
        self.seed_last_term(course_env)
        result = run(course_env.runner, "course", "init", "CS-102", "--org", ORG,
                     "--like", "cs_101", "--template", f"{ORG}/Other", "--apply")
        assert result.exit_code == 0, result.output
        assert meta_state(course_env, "cs_102")["template"] == f"{ORG}/Other"

    def test_like_only_seeds_a_new_course(self, course_env):
        self.seed_last_term(course_env)
        result = run(course_env.runner, "course", "init", "cs_101", "--org", ORG,
                     "--like", "cs_101")
        assert result.exit_code == 2
        assert '"cs_101" already exists; --like only seeds a new course' \
            in result.output


class TestCompletion:
    def test_zsh(self, course_env):
        result = run(course_env.runner, "completion", "zsh")
        assert result.exit_code == 0, result.output
        assert "_GH_CLASS_SAK_COMPLETE" in result.output
        assert "compdef" in result.output

    def test_the_shell_defaults_to_the_login_shell(self, course_env, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/bash")
        result = run(course_env.runner, "completion")
        assert result.exit_code == 0, result.output
        assert "complete -o nosort -F" in result.output

    def test_an_unknown_shell_is_an_error(self, course_env, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/tcsh")
        result = run(course_env.runner, "completion")
        assert result.exit_code == 2
        assert "bash, zsh, or fish" in result.output


class TestDemo:
    def test_without_a_command_it_introduces_the_demo_course(self, course_env):
        result = run(course_env.runner, "demo")
        assert result.exit_code == 0, result.output
        assert "org cs101-fall, course cs101_fall" in result.output
        assert "gh-class-sak demo course status cs101_fall" in result.output

    def test_runs_a_command_against_the_demo_course(self, course_env):
        result = run(course_env.runner, "demo", "course", "status", "cs101_fall")
        assert result.exit_code == 0, result.output
        assert "COURSE    cs101_fall  (org cs101-fall)" in result.output

    def test_changes_happen_offline_and_are_not_kept(self, course_env, tmp_path):
        config_before = core.config_ini
        result = run(course_env.runner, "demo", "sync", "cs101_fall", "--apply")
        assert result.exit_code == 0, result.output
        assert "summary: 5 repos adopted" in result.output
        # the real config and github were never touched
        assert core.config_ini == config_before
        assert core.configured_orgs() == []
        # and a second run starts over from the same made-up course
        again = run(course_env.runner, "demo", "sync", "cs101_fall", "--apply")
        assert "summary: 5 repos adopted" in again.output

    def test_clone_really_clones(self, course_env, tmp_path):
        dest = tmp_path / "grading"
        result = run(course_env.runner, "demo", "repos", "clone", "cs101_fall",
                     "project", "--dest", str(dest), "--apply")
        assert result.exit_code == 0, result.output
        assert (dest / "team-1" / "README.md").exists()

    def test_help_after_a_command_is_that_commands_help(self, course_env):
        result = run(course_env.runner, "demo", "sync", "--help")
        assert result.exit_code == 0, result.output
        assert "Usage: gh-class-sak sync" in result.output


class TestRosterNamesakes:
    def create(self, env, tmp_path, text):
        roster = tmp_path / "people.txt"
        roster.write_text(text)
        return run(env.runner, "assignment", "create", COURSE, "hw1", "--org", ORG,
                   "--roster", str(roster), "--apply")

    def test_namesakes_in_a_plain_list_keep_their_rows_when_reordered(
            self, course_env, tmp_path):
        seed_meta(course_env)
        self.create(course_env, tmp_path, "jane@a.edu/janea\njane@b.edu/janeb\n")
        result = self.create(course_env, tmp_path, "jane@b.edu/janeb\njane@a.edu/janea\n")
        assert result.exit_code == 0, result.output
        rows = {r["name"]: r["students"]
                for r in meta_state(course_env)["assignments"]["hw1"]}
        assert rows == {"janea": ["jane@a.edu/janea"], "janeb": ["jane@b.edu/janeb"]}

    def test_email_only_namesakes_are_numbered_and_stay_put(self, course_env,
                                                            tmp_path):
        seed_meta(course_env)
        self.create(course_env, tmp_path, "jane@a.edu\njane@b.edu\n")
        self.create(course_env, tmp_path, "jane@b.edu\njane@a.edu\n")
        rows = {r["name"]: r["students"]
                for r in meta_state(course_env)["assignments"]["hw1"]}
        assert rows == {"jane": ["jane@a.edu/"], "jane-2": ["jane@b.edu/"]}
