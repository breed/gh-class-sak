import os
import re
import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from gh_class_sak.commands import repos as repos_cmd
from tests.conftest import ORG, run


def lines(result):
    assert result.exit_code == 0, result.output
    # CliRunner mixes stderr into output by default; strip progress lines.
    return [ln for ln in result.output.splitlines()
            if ln.strip() and not ln.startswith("scanning ")]


def columns(line):
    """split a padded table row back into its cells."""
    return re.split(r"\s{2,}", line.strip())


class TestClassrooms:
    EXPECTED = ["cmpe_195a: hw1", "cmpe_195a: project", "cmpe_195a: quiz"]

    def test_lists_classroom_dirs_and_assignments(self, cli, config_file):
        out = lines(run(cli, "classrooms"))
        assert out == self.EXPECTED

    def test_errors_when_no_config_and_no_argument(self, cli, no_config):
        result = run(cli, "classrooms")
        assert result.exit_code == 2
        assert "no classroom" in result.output

    def test_takes_org_argument_verbatim_with_no_config(self, cli, no_config):
        out = lines(run(cli, "classrooms", ORG))
        assert out == self.EXPECTED

    def test_resolves_classroom_argument_through_config(self, cli, config_file):
        out = lines(run(cli, "classrooms", "195A"))
        assert out == self.EXPECTED

    def test_errors_without_a_classroom_meta_repo(self, cli, no_config, fake_github):
        org = fake_github.get_organization(ORG)
        org._repos[:] = [r for r in org._repos if r.name != "classroom-meta"]
        result = run(cli, "classrooms", ORG)
        assert result.exit_code == 2
        assert "no classroom-meta repo" in result.output
        assert "course init" in result.output


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

    def test_email_degrades_on_an_orgs_only_config(self, cli, tmp_path,
                                                   monkeypatch):
        # an [ORGS]-only config — exactly what migrate creates — must behave
        # like no config at all: emails come from commit history, no exit 1
        from gh_class_sak import core
        path = tmp_path / "gh-class-sak.ini"
        path.write_text(f"[ORGS]\n{ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        # without a [CANVAS] section the canvas client must never be built
        # (live, it would exit 1 on the missing credentials)
        def boom():
            raise AssertionError("canvas consulted without a [CANVAS] section")
        monkeypatch.setattr(repos_cmd, "get_canvas", boom)
        out = lines(run(cli, "repos", "list", ORG, "project",
                        "--members", "--email"))
        assert "alice(alice@sjsu.edu)" in out[1]

    def test_errors_when_no_assignment_matches(self, cli, no_config):
        result = run(cli, "repos", "list", ORG, "final")
        assert result.exit_code == 2
        assert 'no assignment matching "final"' in result.output
        assert "cmpe_195a: project" in result.output

    def test_errors_when_the_assignment_has_no_repos(self, cli, no_config):
        # quiz is recorded in the classroom-meta but no repo carries its prefix
        result = run(cli, "repos", "list", ORG, "quiz")
        assert result.exit_code == 2
        assert "no repos" in result.output

    def test_errors_without_a_classroom_meta_repo(self, cli, no_config, fake_github):
        org = fake_github.get_organization(ORG)
        org._repos[:] = [r for r in org._repos if r.name != "classroom-meta"]
        result = run(cli, "repos", "list", ORG, "project")
        assert result.exit_code == 2
        assert "no classroom-meta repo" in result.output



class TestMissingMetaRepoBlamesTheToken:
    """github answers "no such repo" and "not yours to see" with the same 404,
    so the error names the token as the other suspect: a TA whose token has no
    private-repo access reads today's message as "the course isn't set up"."""

    @pytest.fixture
    def no_meta(self, fake_github):
        org = fake_github.get_organization(ORG)
        org._repos[:] = [r for r in org._repos if r.name != "classroom-meta"]
        return fake_github

    def test_names_a_token_without_the_repo_scope(self, cli, no_config, no_meta):
        no_meta.oauth_scopes = ["gist", "read:org"]
        result = run(cli, "classrooms", ORG)
        assert result.exit_code == 2
        assert "no classroom-meta repo" in result.output
        assert "course init" in result.output  # still says how to create one
        assert 'acts as "profbeth"' in result.output
        assert "scopes: gist, read:org" in result.output
        assert '"repo" scope' in result.output
        assert "gh auth refresh -h github.com -s repo" in result.output

    def test_names_a_fine_grained_token(self, cli, no_config, no_meta):
        # github sends no X-OAuth-Scopes header for fine-grained tokens
        no_meta.oauth_scopes = None
        result = run(cli, "classrooms", ORG)
        assert result.exit_code == 2
        assert "fine-grained" in result.output
        assert "resource owner" in result.output
        assert "gh auth refresh" not in result.output

    def test_points_a_repo_scoped_token_at_access_and_sso(self, cli, no_config,
                                                          no_meta):
        result = run(cli, "classrooms", ORG)  # the fake token carries "repo"
        assert result.exit_code == 2
        assert f"member of {ORG}" in result.output
        assert "SSO" in result.output

    def test_repos_list_explains_it_too(self, cli, no_config, no_meta):
        no_meta.oauth_scopes = ["gist"]
        result = run(cli, "repos", "list", ORG, "project")
        assert result.exit_code == 2
        assert "gh auth refresh -h github.com -s repo" in result.output

    def test_meta_list_explains_it_too(self, cli, no_config, no_meta):
        no_meta.oauth_scopes = ["gist"]
        result = run(cli, "meta", "list", ORG)
        assert result.exit_code == 2
        assert "gh auth refresh -h github.com -s repo" in result.output

    def test_meta_show_explains_it_too(self, cli, no_config, no_meta):
        no_meta.oauth_scopes = ["gist"]
        result = run(cli, "meta", "show", ORG)
        assert result.exit_code == 2
        assert "gh auth refresh -h github.com -s repo" in result.output

    def test_a_readable_but_empty_meta_repo_is_not_blamed_on_the_token(
            self, cli, no_config, fake_github):
        # the repo is right there and readable — it just records nothing yet,
        # which no token change would fix
        from gh_class_sak import meta_store as ms
        shutil.rmtree(os.path.join(ms.meta_checkout_dir(ORG), "cmpe_195a"))
        result = run(cli, "classrooms", ORG)
        assert result.exit_code == 2
        assert "records no courses" in result.output
        assert "token" not in result.output


class TestReposMembers:
    def test_extracts_authors_from_commit_history(self, cli, no_config):
        out = lines(run(cli, "repos", "members", ORG, "project"))
        assert columns(out[0]) == ["TEAM", "GITHUB_ID", "NAME", "EMAIL"]
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

        # the only clone traffic is the classroom-meta checkout itself
        assert [c for c in calls if "classroom-meta" not in str(c[0])] == []
        assert not dest.exists()
        # the dry-run banner leads, then one would-line per repo, then the
        # footer saying nothing changed
        assert len(out) == 5
        assert out[0].startswith("\N{WARNING SIGN}\N{VARIATION SELECTOR-16}  dry run")
        assert out[-1].endswith("that was a preview: nothing changed."
                                " add --apply to make these changes")
        assert all(ln.startswith("\N{WARNING SIGN}") for ln in out)
        assert str(dest / "team-12") in out[1]

    def test_no_dryrun_clones_each_repo(self, cli, no_config, tmp_path, monkeypatch):
        calls = []

        def fake_clone(clone_url, target, token=None):
            calls.append((clone_url, target, token))
            return "cloned"

        monkeypatch.setattr("gh_class_sak.git_ops.clone_or_update", fake_clone)

        dest = tmp_path / "work"
        out = lines(run(cli, "repos", "clone", ORG, "project",
                        "--dest", str(dest), "--no-dryrun"))

        cloned = [c for c in calls if "classroom-meta" not in str(c[0])]
        assert [c[0] for c in cloned] == [
            f"https://github.com/{ORG}/project-team-12.git",
            f"https://github.com/{ORG}/project-red-team.git",
            f"https://github.com/{ORG}/project-empty.git",
        ]
        assert cloned[0][1] == str(dest / "team-12")
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


class TestStartupWarnings:
    def test_beta_banner_shows_at_a_terminal(self, cli, config_file, monkeypatch):
        from gh_class_sak import core
        monkeypatch.setattr(core, "_interactive", lambda: True)
        result = run(cli, "classrooms", ORG)
        assert "beta code to replace github classroom" in result.output
        # orgs are configured, so the replaces-not-works-with warning stays quiet
        assert "pre-1.0" not in result.output

    def test_missing_orgs_adds_the_replacement_warning(self, cli, no_config,
                                                       monkeypatch):
        from gh_class_sak import core
        monkeypatch.setattr(core, "_interactive", lambda: True)
        result = run(cli, "classrooms", ORG)
        assert "beta code to replace github classroom" in result.output
        assert ("unlike the pre-1.0 versions, this program replaces github classroom"
                in result.output)
        assert "help-me-setup" in result.output

    def test_warnings_stay_out_of_piped_output(self, cli, no_config):
        # CliRunner's streams are not ttys, like any pipe — the drift-tested
        # docs fences depend on this staying true
        result = run(cli, "classrooms", ORG)
        assert "beta code" not in result.output


@pytest.mark.parametrize("command", ["list", "members", "missing", "clone"])
def test_every_repos_subcommand_reports_an_unknown_org(cli, no_config, command):
    result = run(cli, "repos", command, "no-such-org", "project")
    assert result.exit_code == 2
    assert "no-such-org" in result.output


def test_print_table_never_pads_the_last_column(capsys):
    repos_cmd.print_table(["A", "B"], [["x", "y"], ["longer", "z"]])
    out = capsys.readouterr().out.splitlines()
    assert out == ["A       B", "x       y", "longer  z"]


class TestReposCloneBefore:
    def test_a_date_alone_means_the_end_of_that_day(self):
        from gh_class_sak.commands.repos import _parse_deadline
        when = _parse_deadline(None, None, "2026-10-01")
        assert (when.hour, when.minute, when.second) == (23, 59, 59)
        assert when.tzinfo is not None
        assert _parse_deadline(None, None, "2026-10-01 17:00").hour == 17

    def test_a_bad_deadline_is_a_usage_error(self, cli, no_config):
        result = run(cli, "repos", "clone", ORG, "project", "--before", "friday")
        assert result.exit_code == 2
        assert "YYYY-MM-DD" in result.output

    def test_each_repo_is_left_at_its_last_push_before_the_deadline(
            self, cli, no_config, tmp_path, monkeypatch):
        # github's push record, not commit dates, decides: team-12 pushed in
        # time, red-team only after, and github has no record for empty
        from gh_class_sak import git_ops, github_api
        pushed = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
        records = {"project-team-12": ("a" * 40, pushed),
                   "project-red-team": ("", None),
                   "project-empty": None}
        monkeypatch.setattr(github_api, "pushed_before",
                            lambda repo, when: records[repo.name])
        monkeypatch.setattr(git_ops, "clone_or_update", lambda *a, **k: "cloned")
        checked_out = []
        monkeypatch.setattr(git_ops, "checkout_commit",
                            lambda dest, sha, token=None: checked_out.append(sha)
                            or sha[:7])
        monkeypatch.setattr(git_ops, "checkout_before",
                            lambda dest, when: ("1b2c3d4", "2026-10-01 22:00"))
        result = run(cli, "repos", "clone", ORG, "project", "--dest",
                     str(tmp_path / "grading"), "--before", "2026-10-01", "--apply")
        assert result.exit_code == 0, result.output
        assert checked_out == ["a" * 40]
        local = pushed.astimezone().strftime("%Y-%m-%d %H:%M")
        assert f"aaaaaaa (pushed {local})" in result.output
        assert (f"{ORG}/project-red-team: no push before 2026-10-01 23:59;"
                " left at its latest commit") in result.output
        # no push record at all: commit dates, said out loud
        assert (f"{ORG}/project-empty: github has no push record for main;"
                " used commit dates, which students' machines set") in result.output
        assert "1b2c3d4 (committed 2026-10-01 22:00)" in result.output

    def test_a_pushed_commit_that_cant_be_had_is_an_error(self, cli, no_config,
                                                           tmp_path, monkeypatch):
        from gh_class_sak import git_ops, github_api
        pushed = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(github_api, "pushed_before",
                            lambda repo, when: ("a" * 40, pushed))
        monkeypatch.setattr(git_ops, "clone_or_update", lambda *a, **k: "cloned")

        def unfetchable(dest, sha, token=None):
            raise RuntimeError("cannot fetch it")
        monkeypatch.setattr(git_ops, "checkout_commit", unfetchable)
        result = run(cli, "repos", "clone", ORG, "project", "--dest",
                     str(tmp_path / "grading"), "--before", "2026-10-01", "--apply")
        assert f"{ORG}/project-team-12: cannot fetch it" in result.output
        assert "checkout failed" in result.output

    def test_an_unreadable_push_record_is_an_error_not_a_fallback(
            self, cli, no_config, tmp_path, monkeypatch):
        from gh_class_sak import git_ops, github_api

        def outage(repo, when):
            raise RuntimeError("couldn't read github's push record (502)")
        monkeypatch.setattr(github_api, "pushed_before", outage)
        monkeypatch.setattr(git_ops, "clone_or_update", lambda *a, **k: "cloned")
        fell_back = []
        monkeypatch.setattr(git_ops, "checkout_before",
                            lambda dest, when: fell_back.append(dest))
        result = run(cli, "repos", "clone", ORG, "project", "--dest",
                     str(tmp_path / "grading"), "--before", "2026-10-01", "--apply")
        assert fell_back == []
        assert f"{ORG}/project-team-12: couldn't read github's push record" \
            in result.output
        assert "checkout failed" in result.output

    def test_the_preview_names_the_deadline(self, cli, no_config, tmp_path):
        result = run(cli, "repos", "clone", ORG, "project", "--dest",
                     str(tmp_path / "grading"), "--before", "2026-10-01")
        assert "at its last push before 2026-10-01 23:59" in result.output


def _push(timestamp, after, kind="push"):
    return SimpleNamespace(timestamp=datetime.fromisoformat(timestamp),
                           after=after, activity_type=kind)


class TestPushedBefore:
    """the branch's commit at the deadline, from github's push record: server
    time, which no student's clock can move."""

    DEADLINE = datetime.fromisoformat("2026-10-01T23:59:59+00:00")

    def lookup(self, monkeypatch, pushes):
        from gh_class_sak import github_api
        seen = []

        def branch_pushes(repo, branch):
            seen.append(branch)
            if isinstance(pushes, Exception):
                raise pushes
            return iter(pushes)  # newest first, like the api
        monkeypatch.setattr(github_api, "branch_pushes", branch_pushes)
        got = github_api.pushed_before(SimpleNamespace(default_branch="main"),
                                       self.DEADLINE)
        assert seen == ["main"]
        return got

    def test_the_last_push_before_the_deadline_wins_over_a_later_force_push(
            self, monkeypatch):
        got = self.lookup(monkeypatch, [
            _push("2026-10-03T08:00:00+00:00", "c" * 40, "force_push"),
            _push("2026-10-01T20:00:00+00:00", "b" * 40),
            _push("2026-09-28T10:00:00+00:00", "a" * 40)])
        assert got == ("b" * 40, datetime.fromisoformat("2026-10-01T20:00:00+00:00"))

    def test_a_force_push_before_the_deadline_counts(self, monkeypatch):
        got = self.lookup(monkeypatch, [
            _push("2026-10-01T10:00:00+00:00", "f" * 40, "force_push"),
            _push("2026-09-28T10:00:00+00:00", "a" * 40)])
        assert got[0] == "f" * 40

    def test_a_branch_deleted_before_the_deadline_had_no_commit(self, monkeypatch):
        got = self.lookup(monkeypatch, [
            _push("2026-10-01T10:00:00+00:00", "0" * 40, "branch_deletion"),
            _push("2026-09-28T10:00:00+00:00", "a" * 40)])
        assert got == ("", datetime.fromisoformat("2026-10-01T10:00:00+00:00"))

    def test_only_pushes_after_the_deadline(self, monkeypatch):
        got = self.lookup(monkeypatch, [_push("2026-10-02T10:00:00+00:00", "b" * 40)])
        assert got == ("", None)

    def test_no_push_record_at_all(self, monkeypatch):
        assert self.lookup(monkeypatch, []) is None

    def test_github_refusing_the_record_is_no_record(self, monkeypatch):
        from github import GithubException
        refused = GithubException(403, {"message": "Forbidden"}, None)
        assert self.lookup(monkeypatch, refused) is None

    def test_no_record_endpoint_is_no_record(self, monkeypatch):
        from github import GithubException
        missing = GithubException(404, {"message": "Not Found"}, None)
        assert self.lookup(monkeypatch, missing) is None

    @pytest.mark.parametrize("failure", ["server", "rate limit", "credentials"])
    def test_a_transient_failure_is_an_error_never_a_fallback(self, monkeypatch,
                                                              failure):
        # falling back would quietly grade by student-set commit dates
        from github import BadCredentialsException, GithubException, RateLimitExceededException
        exc = {"server": GithubException(502, {"message": "Bad Gateway"}, None),
               "rate limit": RateLimitExceededException(
                   403, {"message": "API rate limit exceeded"}, None),
               "credentials": BadCredentialsException(
                   401, {"message": "Bad credentials"}, None)}[failure]
        with pytest.raises(RuntimeError, match="couldn't read github's push record"):
            self.lookup(monkeypatch, exc)


class FakeRequester:
    """PyGithub's http layer, serving canned /activity pages the way github
    does: a JSON list per page, the next page's url in a Link header."""

    per_page = 30

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def requestJsonAndCheck(self, verb, url, parameters=None, headers=None,
                            input=None, **_kwargs):
        self.calls.append((verb, url, parameters))
        return self.pages.pop(0)

    def check_me(self, obj):
        pass


class TestBranchPushesOverTheRealAdapter:
    """branch_pushes and BranchPush against github-shaped responses, through
    PyGithub's own PaginatedList — nothing monkeypatched."""

    URL = "https://api.github.com/repos/cs101-fall/hw1-jdoe"
    NEXT = "https://api.github.com/repositories/42/activity?ref=refs%2Fheads%2Fmain&after=CUR"

    def payload(self, when, after, kind="push", before="0" * 40):
        return {"id": 1, "node_id": "RA_x", "before": before, "after": after,
                "ref": "refs/heads/main", "timestamp": when,
                "activity_type": kind, "actor": {"login": "jdoe", "id": 7}}

    def repo(self):
        pages = [
            ({"link": f'<{self.NEXT}>; rel="next"'},
             [self.payload("2026-10-03T08:00:00Z", "c" * 40, "force_push"),
              self.payload("2026-10-01T20:00:00Z", "b" * 40)]),
            ({}, [self.payload("2026-09-28T10:00:00Z", "a" * 40,
                               "branch_creation")]),
        ]
        return SimpleNamespace(_requester=FakeRequester(pages), url=self.URL,
                               default_branch="main")

    def test_reads_every_page_of_the_branchs_record(self):
        from gh_class_sak.github_api import branch_pushes
        repo = self.repo()
        pushes = list(branch_pushes(repo, "main"))
        assert [(p.activity_type, p.after[:1]) for p in pushes] == [
            ("force_push", "c"), ("push", "b"), ("branch_creation", "a")]
        assert pushes[1].timestamp == datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
        assert pushes[0].before == "0" * 40
        (verb, url, params), (_, next_url, next_params) = repo._requester.calls
        assert (verb, url) == ("GET", f"{self.URL}/activity")
        assert params == {"ref": "refs/heads/main", "direction": "desc",
                          "per_page": 100}
        assert next_url == self.NEXT and not next_params

    def test_pushed_before_on_real_payloads(self):
        from gh_class_sak.github_api import pushed_before
        deadline = datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
        assert pushed_before(self.repo(), deadline) == (
            "b" * 40, datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc))
