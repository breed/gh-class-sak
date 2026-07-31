import pytest

from gh_class_sak import core
from gh_class_sak.github_api import (
    find_assignment_repos,
    github_safe_name,
    infer_assignment_prefixes,
    team_name,
)
from tests.fakes import FakeGithub, FakeOrg, FakeRepo

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


class TestGithubSafeName:
    def test_spaces_become_dashes(self):
        assert github_safe_name("Alice Adams") == "Alice-Adams"

    def test_accents_lose_their_marks(self):
        assert github_safe_name("José Núñez") == "Jose-Nunez"

    def test_invalid_runs_collapse(self):
        assert github_safe_name("Adams, Alice") == "Adams-Alice"

    def test_edges_are_trimmed(self):
        assert github_safe_name(" (Team 1) ") == "Team-1"

    def test_never_empty(self):
        assert github_safe_name("???") == "x"


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

    def test_no_substring_matching(self):
        # "project" buried mid-name belongs to some other classroom's prefix;
        # only a recorded id may claim it
        repos = [repo("sp26-project-team-12"), repo("hw1-a")]
        assert find_assignment_repos(repos, "project") == []

    def test_returns_empty_when_nothing_matches(self):
        assert find_assignment_repos([repo("hw1-a")], "final") == []


class TestMatchOrg:
    ORGS = ["cmpe-195-a", "cmpe-195-b"]

    def test_partial_match(self):
        assert core.match_org("195-a", self.ORGS) == "cmpe-195-a"

    def test_exact_beats_partial(self):
        assert core.match_org("cmpe-195-a", self.ORGS + ["cmpe-195-a-old"]) \
            == "cmpe-195-a"

    def test_no_match_is_none(self):
        assert core.match_org("physics", self.ORGS) is None

    def test_ambiguity_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            core.match_org("cmpe-195", self.ORGS)
        assert exc.value.code == 2


class TestResolveClassroomOrg:
    """the org side of resolve_classroom; gh is only touched for course names,
    so these pass gh=None or an org with no classroom-meta repo."""

    def test_matches_a_configured_org(self, config_file):
        assert core.resolve_classroom(None, "CMPE-195") == (ORG, None)

    def test_org_match_leaves_the_classroom_open(self, config_file):
        assert core.resolve_classroom(None, ORG) == (ORG, None)

    def test_falls_through_to_a_literal_org_with_no_config(self, no_config):
        assert core.resolve_classroom(None, "some-other-org") == ("some-other-org", None)

    def test_falls_through_when_nothing_matches(self, config_file):
        # neither an org nor a classroom dir (the org has no classroom-meta)
        gh = FakeGithub(orgs=[FakeOrg(ORG)])
        assert core.resolve_classroom(gh, "unrelated-org") == ("unrelated-org", None)

    def test_exits_2_on_org_ambiguity(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text("[ORGS]\ncmpe-195-a\ncmpe-195-b\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        with pytest.raises(SystemExit) as exc:
            core.resolve_classroom(None, "cmpe-195")
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

    def test_orgs_keep_their_config_order(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text("[ORGS]\nzeta-org\nalpha-org\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        assert core.configured_orgs() == ["zeta-org", "alpha-org"]

    def test_a_canvas_only_config_has_no_orgs(self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text("[CANVAS]\nurl = u\ntoken = t\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        assert core.configured_orgs() == []

    def test_add_org_creates_the_config_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(core, "config_ini", str(tmp_path / "sub" / "cfg.ini"))
        core.add_org_to_config("new-org")
        assert core.configured_orgs() == ["new-org"]

    def test_add_org_preserves_comments_and_other_sections(self, tmp_path,
                                                           monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text("# my config\n[ORGS]\nfirst-org\n\n"
                        "[CANVAS]\nurl = u\ntoken = t\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        core.add_org_to_config("second-org")
        text = path.read_text()
        assert "# my config" in text
        assert "url = u" in text
        assert core.configured_orgs() == ["second-org", "first-org"]

    def test_percent_in_a_canvas_token_is_literal(self, tmp_path, monkeypatch):
        # interpolation must be off: api tokens can contain %
        path = tmp_path / "cfg.ini"
        path.write_text("[CANVAS]\nurl = u\ntoken = abc%def\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        assert core.load_config().get("CANVAS", "token") == "abc%def"

    def test_add_org_handles_an_orgs_header_with_a_comment(
            self, tmp_path, monkeypatch):
        # configparser accepts trailing text after the ], so the header
        # match must too — or a second [ORGS] section corrupts the file
        path = tmp_path / "cfg.ini"
        path.write_text("[ORGS]  # my orgs\nfirst-org\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        core.add_org_to_config("second-org")
        assert core.configured_orgs() == ["second-org", "first-org"]

    def test_add_org_appends_the_section_to_a_canvas_only_config(
            self, tmp_path, monkeypatch):
        path = tmp_path / "cfg.ini"
        path.write_text("[CANVAS]\nurl = u\ntoken = t\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        core.add_org_to_config("new-org")
        assert core.configured_orgs() == ["new-org"]
        assert core.load_config().get("CANVAS", "url") == "u"

    def test_warns_on_a_malformed_config_instead_of_ignoring_it(
            self, tmp_path, monkeypatch, capsys):
        # a typo'd section header must not silently read as "no config"
        path = tmp_path / "cfg.ini"
        path.write_text("[ORG]\nsome-org\n")
        monkeypatch.setattr(core, "config_ini", str(path))

        assert core.load_config(required=False) is None
        assert "no [CANVAS] or [ORGS] section" in capsys.readouterr().err

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


