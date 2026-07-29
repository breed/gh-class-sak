import pytest

from gh_class_sak import core
from gh_class_sak.github_api import (
    find_assignment_repos,
    infer_assignment_prefixes,
    team_name,
)
from tests.fakes import FakeRepo

ORG = "SJSU-CMPE-195"


def repo(name):
    return FakeRepo(ORG, name)


class TestInferAssignmentPrefixes:
    def test_groups_repos_by_shared_prefix(self):
        names = ["project-team-12", "project-red-team", "hw1-a", "hw1-b", "hw1-c"]
        assert infer_assignment_prefixes(names) == [("hw1", 3), ("project", 2)]

    def test_ignores_repos_with_no_prefix(self):
        assert infer_assignment_prefixes(["sandbox", "hw1-a", "hw1-b"]) == [("hw1", 2)]

    def test_ignores_prefixes_used_by_one_repo(self):
        # project-team appears once, so only the shared "project" survives
        names = ["project-team-12", "project-red-team"]
        assert infer_assignment_prefixes(names) == [("project", 2)]

    def test_prefers_the_most_specific_prefix_with_equal_coverage(self):
        # every repo is hw1-part2-*, so "hw1" and "hw1-part2" cover the same
        # repos and only the longer one should be reported
        names = ["hw1-part2-a", "hw1-part2-b"]
        assert infer_assignment_prefixes(names) == [("hw1-part2", 2)]

    def test_suppresses_sub_patterns_of_an_accepted_prefix(self):
        # hw1-part2 is how two of the teams are named, not a second assignment
        names = ["hw1-part2-a", "hw1-part2-b", "hw1-solo"]
        assert infer_assignment_prefixes(names) == [("hw1", 3)]

    def test_reports_unrelated_assignments_separately(self):
        names = ["group-project-team-1", "group-project-team-2", "group-project-red",
                 "sp26-cmpe-195a-template", "sp26-cmpe-195b-template"]
        assert infer_assignment_prefixes(names) == [("group-project", 3), ("sp26-cmpe", 2)]

    def test_empty_input(self):
        assert infer_assignment_prefixes([]) == []


class TestTeamName:
    def test_strips_prefix_and_separator(self):
        assert team_name("project-team-12", "project") == "team-12"

    def test_is_case_insensitive(self):
        assert team_name("Project-Team-12", "project") == "Team-12"

    def test_falls_back_to_repo_name_when_prefix_absent(self):
        assert team_name("sandbox", "project") == "sandbox"

    def test_falls_back_when_stripping_would_empty_the_name(self):
        assert team_name("project", "project") == "project"


class TestFindAssignmentRepos:
    def test_matches_by_leading_prefix(self):
        repos = [repo("project-team-12"), repo("project-red-team"), repo("hw1-a")]
        assert [t for t, _ in find_assignment_repos(repos, "project")] == \
            ["team-12", "red-team"]

    def test_falls_back_to_substring_match(self):
        repos = [repo("sp26-project-team-12"), repo("hw1-a")]
        found = find_assignment_repos(repos, "project")
        assert [r.name for _, r in found] == ["sp26-project-team-12"]

    def test_returns_empty_when_nothing_matches(self):
        assert find_assignment_repos([repo("hw1-a")], "final") == []


class TestSharedOrg:
    """Two Canvas courses can live in one GitHub org, as SJSU-CMPE-195 does."""

    @pytest.fixture
    def shared(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text(
            "[CANVAS]\nurl = u\ntoken = t\n\n"
            f"[COURSES]\nSP26_CMPE_195A = {ORG}\nSP26_CMPE_195B = {ORG}\n"
        )
        monkeypatch.setattr(core, "config_ini", str(path))
        return str(path)

    def test_course_partial_selects_one_of_the_courses(self, shared):
        assert core.resolve_classroom("195A") == (ORG, "SP26_CMPE_195A")
        assert core.resolve_classroom("195B") == (ORG, "SP26_CMPE_195B")

    def test_naming_the_org_resolves_it_but_leaves_the_course_open(self, shared):
        # the org is unambiguous, the canvas course is not
        assert core.resolve_classroom(ORG) == (ORG, None)

    def test_org_lookup_still_succeeds(self, shared):
        assert core.resolve_org("195B") == ORG

    def test_course_mapping_reports_the_ambiguity(self, shared):
        config = core.load_config()
        with pytest.raises(SystemExit) as exc:
            core.resolve_course_mapping(config, ORG)
        assert exc.value.code == 2


class TestResolveOrg:
    def test_matches_the_org_value(self, config_file):
        assert core.resolve_org("CMPE-195") == ORG

    def test_matches_the_canvas_key(self, config_file):
        # users type the course name they know, not the org
        assert core.resolve_org("195A") == ORG

    def test_falls_through_to_a_literal_org_with_no_config(self, no_config):
        assert core.resolve_org("some-other-org") == "some-other-org"

    def test_falls_through_when_config_has_no_match(self, config_file):
        assert core.resolve_org("unrelated-org") == "unrelated-org"

    def test_exits_2_on_ambiguity(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text(
            "[CANVAS]\nurl = u\ntoken = t\n\n"
            "[COURSES]\nCMPE-195A = cmpe-195-a\nCMPE-195B = cmpe-195-b\n"
        )
        monkeypatch.setattr(core, "config_ini", str(path))
        with pytest.raises(SystemExit) as exc:
            core.resolve_org("cmpe-195")
        assert exc.value.code == 2


class TestLoadConfig:
    def test_returns_none_when_absent_and_not_required(self, no_config):
        assert core.load_config(required=False) is None

    def test_exits_1_when_absent_and_required(self, no_config):
        with pytest.raises(SystemExit) as exc:
            core.load_config(required=True)
        assert exc.value.code == 1

    def test_reads_sections(self, config_file):
        config = core.load_config()
        assert config.get("CANVAS", "url") == "https://canvas.example.edu"
        assert core.configured_orgs(config) == [ORG]

    def test_warns_on_a_malformed_config_instead_of_ignoring_it(
            self, tmp_path, monkeypatch, capsys):
        # a typo'd section header must not silently read as "no config"
        path = tmp_path / "cfg.ini"
        path.write_text("[CANVAS]\nurl = u\ntoken = t\n\n[COURSE]\nX = org\n")
        monkeypatch.setattr(core, "config_ini", str(path))

        assert core.load_config(required=False) is None
        assert "missing [COURSES] section" in capsys.readouterr().err

        with pytest.raises(SystemExit) as exc:
            core.load_config(required=True)
        assert exc.value.code == 1

    def test_unparseable_config_warns_when_not_required(
            self, tmp_path, monkeypatch, capsys):
        path = tmp_path / "cfg.ini"
        path.write_text("not an ini file at all\n")
        monkeypatch.setattr(core, "config_ini", str(path))

        assert core.load_config(required=False) is None
        assert "ignoring config" in capsys.readouterr().err


class TestResolveCourseMapping:
    def test_maps_org_back_to_canvas_partial(self, config_file):
        config = core.load_config()
        assert core.resolve_course_mapping(config, ORG) == "CMPE-195A"

    def test_exits_2_when_unmapped(self, config_file):
        config = core.load_config()
        with pytest.raises(SystemExit) as exc:
            core.resolve_course_mapping(config, "unknown-org")
        assert exc.value.code == 2
