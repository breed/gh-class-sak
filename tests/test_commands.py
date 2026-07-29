import os
import re

import pytest

from gh_class_sak.commands import repos as repos_cmd
from tests.conftest import ORG, run


def lines(result):
    assert result.exit_code == 0, result.output
    # stdout only: progress messages go to stderr and are not part of the
    # output contract
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def columns(line):
    """split a padded table row back into its cells."""
    return re.split(r"\s{2,}", line.strip())


class TestClassrooms:
    def test_lists_org_and_inferred_assignments(self, cli, config_file):
        out = lines(run(cli, "classrooms"))
        assert out == [f"{ORG}: hw1", f"{ORG}: project"]

    def test_errors_when_no_config_and_no_argument(self, cli, no_config):
        result = run(cli, "classrooms")
        assert result.exit_code == 2
        assert "no classroom" in result.stderr

    def test_takes_org_argument_verbatim_with_no_config(self, cli, no_config):
        out = lines(run(cli, "classrooms", ORG))
        assert out == [f"{ORG}: hw1", f"{ORG}: project"]

    def test_resolves_classroom_argument_through_config(self, cli, config_file):
        out = lines(run(cli, "classrooms", "195A"))
        assert out == [f"{ORG}: hw1", f"{ORG}: project"]


class TestReposList:
    def test_teams_only_by_default(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project"))
        assert out[0] == "TEAM"
        assert out[1:] == ["team-12", "red-team", "empty"]

    def test_resolves_classroom_through_the_config(self, cli, config_file):
        out = lines(run(cli, "repos", "list", "195A", "project"))
        assert out[1:] == ["team-12", "red-team", "empty"]

    def test_repo_column_shows_full_name(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project", "--repo"))
        assert columns(out[0]) == ["TEAM", "REPO"]
        assert columns(out[1]) == ["team-12", f"{ORG}/project-team-12"]

    def test_members_excludes_admins(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members"))
        assert columns(out[1])[1] == "alice,bob"
        assert "profbeth" not in run(cli, "repos", "list", ORG, "project", "--members").output

    def test_empty_teams_hidden_unless_requested(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members"))
        assert [columns(ln)[0] for ln in out[1:]] == ["team-12", "red-team"]

        out = lines(run(cli, "repos", "list", ORG, "project", "--members", "--show-empty"))
        assert [columns(ln)[0] for ln in out[1:]] == ["team-12", "red-team", "empty"]

    def test_name_annotation(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members", "--name"))
        assert columns(out[1])[1] == "alice(Alice Adams),bob(Bob Baker)"

    def test_name_annotation_skips_users_without_a_name(self, cli, no_config):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members", "--name"))
        assert columns(out[2])[1] == "carol(Carol Chen),dave"

    def test_group_matching_against_canvas(self, cli, config_file):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members", "--group", "Project"))
        assert columns(out[0]) == ["TEAM", "MEMBERS", "GROUP"]
        assert columns(out[1])[2] == "Project Group 1"
        assert columns(out[2])[2] == "Project Group 2"

    def test_instructors_column_uses_shared_section(self, cli, config_file):
        out = lines(run(cli, "repos", "list", ORG, "project",
                        "--members", "--instructors"))
        assert columns(out[0]) == ["TEAM", "MEMBERS", "INSTRUCTORS"]
        # alice and bob are in section s1 with Beth; carol is in s2 with nobody
        assert columns(out[1])[2] == "profbeth"
        assert len(columns(out[2])) == 2

    def test_email_prefers_commit_email_and_skips_noreply(self, cli, config_file):
        out = lines(run(cli, "repos", "list", ORG, "project", "--members", "--email"))
        # alice's commit email is real; bob's is noreply so canvas wins
        assert columns(out[1])[1] == "alice(alice@sjsu.edu),bob(bob@sjsu.edu)"

    def test_errors_when_no_repo_matches_the_assignment(self, cli, no_config):
        result = run(cli, "repos", "list", ORG, "final")
        assert result.exit_code == 2
        assert "no repos" in result.output


class TestReposMembers:
    def test_extracts_authors_from_commit_history(self, cli, no_config):
        out = lines(run(cli, "repos", "members", ORG, "project"))
        assert columns(out[0]) == ["REPO", "GITHUB_ID", "NAME", "EMAIL"]
        rows = [columns(ln) for ln in out[1:]]
        assert ["team-12", "alice", "Alice Adams", "alice@sjsu.edu"] in rows
        assert ["red-team", "carol", "Carol Chen", "carol@sjsu.edu"] in rows

    def test_deduplicates_repeated_authors(self, cli, no_config):
        rows = [columns(ln) for ln in lines(run(cli, "repos", "members", ORG, "project"))[1:]]
        assert sum(1 for r in rows if r[1] == "alice") == 1

    def test_skips_noreply_addresses(self, cli, no_config):
        assert "noreply" not in run(cli, "repos", "members", ORG, "project").output

    def test_reports_commits_with_no_github_account(self, cli, no_config):
        rows = [columns(ln) for ln in lines(run(cli, "repos", "members", ORG, "project"))[1:]]
        assert ["team-12", "?", "Unknown", "drive-by@example.com"] in rows

    def test_survives_an_empty_repo(self, cli, no_config):
        # project-empty answers 409 from the commits endpoint
        result = run(cli, "repos", "members", ORG, "project")
        assert result.exit_code == 0


class TestReposMissing:
    def test_reports_canvas_groups_with_no_repo(self, cli, config_file):
        out = lines(run(cli, "repos", "missing", ORG, "project", "--group", "Project"))
        assert len(out) == 1
        assert out[0].startswith("Project Group 3")
        assert "Erin Evans" in out[0]

    def test_reports_students_with_no_repo(self, cli, config_file):
        out = lines(run(cli, "repos", "missing", ORG, "project"))
        assert columns(out[0]) == ["NAME", "EMAIL", "GITHUB_ID"]
        rows = [columns(ln) for ln in out[1:]]
        assert [r[0] for r in rows] == ["Erin Evans"]

    def test_unresolvable_students_show_a_question_mark(self, cli, config_file):
        rows = [columns(ln) for ln in lines(run(cli, "repos", "missing", ORG, "project"))[1:]]
        assert rows[0][2] == "?"


class TestReposClone:
    def test_previews_by_default_and_touches_nothing(self, cli, no_config, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr("gh_class_sak.git_ops.clone_or_update",
                            lambda *a, **k: calls.append(a) or "cloned")

        dest = tmp_path / "work"
        out = lines(run(cli, "repos", "clone", ORG, "project", "--dest", str(dest)))

        assert calls == []
        assert not dest.exists()
        assert len(out) == 3
        assert all(ln.startswith("\N{WARNING SIGN}") for ln in out)
        assert str(dest / "team-12") in out[0]

    def test_no_dryrun_clones_each_repo(self, cli, no_config, tmp_path, monkeypatch):
        calls = []

        def fake_clone(clone_url, target, token=None):
            calls.append((clone_url, target, token))
            return "cloned"

        monkeypatch.setattr("gh_class_sak.git_ops.clone_or_update", fake_clone)

        dest = tmp_path / "work"
        out = lines(run(cli, "repos", "clone", ORG, "project",
                        "--dest", str(dest), "--no-dryrun"))

        assert [c[0] for c in calls] == [
            f"https://github.com/{ORG}/project-team-12.git",
            f"https://github.com/{ORG}/project-red-team.git",
            f"https://github.com/{ORG}/project-empty.git",
        ]
        assert calls[0][1] == str(dest / "team-12")
        assert columns(out[0]) == ["REPO", "PATH", "STATUS"]
        assert columns(out[1])[2] == "cloned"

    def test_never_prints_the_token(self, cli, no_config, tmp_path, monkeypatch):
        monkeypatch.setattr("gh_class_sak.git_ops.clone_or_update", lambda *a, **k: "cloned")
        result = run(cli, "repos", "clone", ORG, "project",
                     "--dest", str(tmp_path / "w"), "--no-dryrun")
        assert "ghp_faketoken" not in result.output


class TestGitOps:
    def test_auth_env_keeps_the_token_out_of_argv(self):
        from gh_class_sak.git_ops import auth_env
        env = auth_env("ghp_secret")
        # the token is base64'd inside a header value, never a bare argument
        assert env["GIT_CONFIG_COUNT"] == "1"
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
        assert "ghp_secret" not in env["GIT_CONFIG_VALUE_0"]

    def test_auth_env_is_empty_without_a_token(self):
        from gh_class_sak.git_ops import auth_env
        assert auth_env(None) == {}

    def test_clone_or_update_reports_not_a_repo(self, tmp_path):
        from gh_class_sak.git_ops import clone_or_update
        plain = tmp_path / "plain"
        plain.mkdir()
        assert clone_or_update("https://github.com/x/y.git", str(plain)) == "not-a-repo"

    def test_clone_and_then_fast_forward_a_real_repo(self, tmp_path):
        from git import Repo

        from gh_class_sak.git_ops import clone_or_update

        origin = tmp_path / "origin"
        source = Repo.init(origin)
        (origin / "README").write_text("v1\n")
        source.index.add(["README"])
        source.index.commit("first")

        dest = str(tmp_path / "clone")
        assert clone_or_update(str(origin), dest) == "cloned"
        assert os.path.exists(os.path.join(dest, "README"))

        assert clone_or_update(str(origin), dest) == "up-to-date"

        (origin / "README").write_text("v2\n")
        source.index.add(["README"])
        source.index.commit("second")
        assert clone_or_update(str(origin), dest) == "updated"

    def test_an_empty_remote_reports_empty_not_diverged(self, tmp_path):
        # empty student repos are routine; a second clone pass must not
        # mislabel them as diverged
        from git import Repo

        from gh_class_sak.git_ops import clone_or_update

        origin = tmp_path / "origin"
        Repo.init(origin)

        dest = str(tmp_path / "clone")
        assert clone_or_update(str(origin), dest) == "cloned"
        assert clone_or_update(str(origin), dest) == "empty"

    def test_diverged_checkout_is_reported_not_raised(self, tmp_path):
        from git import Repo

        from gh_class_sak.git_ops import clone_or_update

        origin = tmp_path / "origin"
        source = Repo.init(origin)
        (origin / "README").write_text("v1\n")
        source.index.add(["README"])
        source.index.commit("first")

        dest = str(tmp_path / "clone")
        clone_or_update(str(origin), dest)

        # commit on both sides so a fast-forward is impossible
        (origin / "README").write_text("origin\n")
        source.index.add(["README"])
        source.index.commit("origin side")

        local = Repo(dest)
        (tmp_path / "clone" / "OTHER").write_text("local\n")
        local.index.add(["OTHER"])
        local.index.commit("local side")

        assert clone_or_update(str(origin), dest) == "diverged"


@pytest.mark.parametrize("command", ["list", "members", "missing", "clone"])
def test_every_repos_subcommand_reports_an_unknown_org(cli, no_config, command):
    result = run(cli, "repos", command, "no-such-org", "project")
    assert result.exit_code == 2
    assert "no-such-org" in result.output


def test_print_table_never_pads_the_last_column(capsys):
    repos_cmd.print_table(["A", "B"], [["x", "y"], ["longer", "z"]])
    out = capsys.readouterr().out.splitlines()
    assert out == ["A       B", "x       y", "longer  z"]
