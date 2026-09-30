from gh_class_sak.commands.repos import (
    extract_github_username,
    format_label,
    match_groups,
    names_match,
    normalize_name,
)


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

    # a link into someone else's repo names that repo's owner, not the
    # student: read as an account, it invited a stranger to a team repo

    def test_a_link_into_someone_elses_repo_is_not_the_account(self):
        profile = {"links": [
            {"url": "https://github.com/some-maintainer/some-tool/releases",
             "title": "linkedin"},
            {"url": "https://github.com/student-login", "title": "github"}]}
        assert extract_github_username(profile) == "student-login"

    def test_a_repo_link_alone_names_no_account(self):
        profile = {"links": [{"url": "https://github.com/some-maintainer/some-tool"}]}
        assert extract_github_username(profile) is None

    def test_a_repo_mentioned_in_the_bio_names_no_account(self):
        bio = "I contribute to github.com/some-maintainer/some-tool"
        assert extract_github_username({"bio": bio}) is None
        bio += " and I am github.com/student-login."
        assert extract_github_username({"bio": bio}) == "student-login"

    def test_a_link_titled_github_beats_other_account_links(self):
        profile = {"links": [
            {"url": "https://github.com/some-class-org", "title": "team"},
            {"url": "https://github.com/student-login", "title": "GitHub"}]}
        assert extract_github_username(profile) == "student-login"

    def test_a_lookalike_host_is_not_github(self):
        for url in ("https://notgithub.com/stranger",
                    "https://evil-github.com/stranger",
                    "https://github.com.example.net/stranger",
                    "https://gist.github.com/stranger"):
            assert extract_github_username({"links": [{"url": url}]}) is None, url
        assert extract_github_username({"bio": "see notgithub.com/stranger"}) is None

    def test_an_account_link_may_end_in_a_slash_or_query(self):
        for url in ("https://github.com/student-login/",
                    "https://www.github.com/student-login?tab=repositories",
                    "http://github.com/student-login#top"):
            assert extract_github_username({"links": [{"url": url}]}) == "student-login"


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
