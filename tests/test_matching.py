from gh_class_sak.commands.repos import (
    _github_from_search,
    extract_github_username,
    format_label,
    match_groups,
    names_match,
    normalize_name,
)
from tests.fakes import FakeSearchResult


class TestGithubFromSearch:
    def test_display_name_never_resolves_a_github_id(self):
        # two people can share a display name; resolving an id from one
        # could hand repo access to a stranger. email search only.
        queried = []

        class GH:
            def search_users(self, query):
                queried.append(query)
                return FakeSearchResult(
                    ["a-stranger"] if query.startswith("fullname:") else [])

        people = {"1": {"name": "Erin Evans", "email": "erin@nowhere.edu",
                        "github": None}}
        _github_from_search(GH(), people)
        assert people["1"]["github"] is None
        assert not [q for q in queried if q.startswith("fullname:")]

    def test_email_search_still_resolves(self):
        class GH:
            def search_users(self, query):
                return FakeSearchResult(
                    ["erin-dev"] if query == "erin@sjsu.edu in:email" else [])

        people = {"1": {"name": "Erin Evans", "email": "erin@sjsu.edu",
                        "github": None}}
        _github_from_search(GH(), people)
        assert people["1"]["github"] == "erin-dev"


class TestNormalizeName:
    def test_lowercases_and_trims(self):
        assert normalize_name("  Alice Adams ") == "alice adams"

    def test_flips_last_comma_first(self):
        assert normalize_name("Adams, Alice") == "alice adams"

    def test_leaves_a_lone_comma_alone(self):
        assert normalize_name("Adams,Alice") == "adams,alice"


class TestNamesMatch:
    def test_exact(self):
        assert names_match("Alice Adams", "alice adams")

    def test_across_comma_format(self):
        assert names_match("Adams, Alice", "Alice Adams")

    def test_near_miss_within_threshold(self):
        assert names_match("Jon Smith", "John Smith")

    def test_different_people_do_not_match(self):
        assert not names_match("Alice Adams", "Bob Baker")

    def test_threshold_is_configurable(self):
        assert not names_match("Jon Smith", "John Smith", threshold=0.99)


class TestMatchGroups:
    def test_assigns_by_highest_score(self):
        repos = [(0, ["Alice Adams", "Bob Baker"]), (1, ["Carol Chen"])]
        groups = [
            {"name": "G1", "members": ["Adams, Alice", "Baker, Bob"]},
            {"name": "G2", "members": ["Chen, Carol"]},
        ]
        assert match_groups(repos, groups) == {0: "G1", 1: "G2"}

    def test_each_group_is_used_at_most_once(self):
        # both repos contain Alice; only the stronger match may claim G1
        repos = [(0, ["Alice Adams", "Bob Baker"]), (1, ["Alice Adams"])]
        groups = [{"name": "G1", "members": ["Alice Adams", "Bob Baker"]}]
        result = match_groups(repos, groups)
        assert result == {0: "G1"}

    def test_each_repo_is_used_at_most_once(self):
        repos = [(0, ["Alice Adams"])]
        groups = [
            {"name": "G1", "members": ["Alice Adams"]},
            {"name": "G2", "members": ["Alice Adams"]},
        ]
        assert len(match_groups(repos, groups)) == 1

    def test_unmatched_repos_are_absent(self):
        repos = [(0, ["Zoe Zhang"])]
        groups = [{"name": "G1", "members": ["Alice Adams"]}]
        assert match_groups(repos, groups) == {}


class TestExtractGithubUsername:
    def test_from_profile_link(self):
        profile = {"links": [{"url": "https://github.com/alice"}]}
        assert extract_github_username(profile) == "alice"

    def test_from_bio_when_no_link(self):
        assert extract_github_username({"bio": "find me at github.com/bob"}) == "bob"

    def test_link_wins_over_bio(self):
        profile = {"links": [{"url": "https://github.com/alice"}], "bio": "github.com/bob"}
        assert extract_github_username(profile) == "alice"

    def test_handles_plain_string_links(self):
        assert extract_github_username({"links": ["https://github.com/carol"]}) == "carol"

    def test_returns_none_when_absent(self):
        assert extract_github_username({"links": [{"url": "https://sjsu.edu"}]}) is None

    def test_returns_none_for_an_empty_profile(self):
        assert extract_github_username({}) is None


class TestFormatLabel:
    def test_bare_login(self):
        assert format_label("alice") == "alice"

    def test_name_annotation(self):
        assert format_label("alice", name="Alice Adams", show_name=True) == \
            "alice(Alice Adams)"

    def test_email_annotation(self):
        assert format_label("alice", email="a@sjsu.edu", show_email=True) == \
            "alice(a@sjsu.edu)"

    def test_both_annotations(self):
        assert format_label("alice", name="Alice Adams", email="a@sjsu.edu",
                            show_name=True, show_email=True) == \
            "alice(Alice Adams,a@sjsu.edu)"

    def test_missing_values_are_skipped(self):
        assert format_label("dave", name=None, show_name=True) == "dave"
