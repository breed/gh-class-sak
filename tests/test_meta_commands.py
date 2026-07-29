from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from git import Repo as GitRepo

from gh_class_sak import core
from gh_class_sak import meta_store as ms
from gh_class_sak.commands import classrooms as classrooms_cmd
from gh_class_sak.commands import meta as meta_cmd
from gh_class_sak.commands import repos as repos_cmd
from tests.conftest import ORG, run
from tests.fakes import FakeGithub, FakeNamedUser, FakeOrg, FakeRepo

PREFIX = "sp26-cmpe-195a-project"
COURSE = "cmpe_195a"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """a fake org whose created repos and meta repo are real local bare gits."""
    root = tmp_path / "origins"
    root.mkdir()
    checkouts = tmp_path / "checkouts"
    monkeypatch.setattr(ms, "meta_checkout_dir", lambda name: str(checkouts / name))

    template = FakeRepo(ORG, "Template")
    org = FakeOrg(ORG, [template], local_git_root=str(root))
    gh = FakeGithub(orgs=[org], search_results={
        "jane@sjsu.edu in:email": ["jdoe"],
    })
    for mod in (core, repos_cmd, classrooms_cmd, meta_cmd):
        monkeypatch.setattr(mod, "get_github", lambda: gh, raising=False)
        monkeypatch.setattr(mod, "get_token", lambda: None, raising=False)
    monkeypatch.setattr(core, "config_ini", str(tmp_path / "absent.ini"))
    return SimpleNamespace(gh=gh, org=org, root=root, checkouts=checkouts,
                           template=template, runner=CliRunner())


def seed_meta(env, course=COURSE, prefix=PREFIX, template=None, tas=(), rows=()):
    """put a meta repo with recorded state into the fake org."""
    bare = env.root / "meta.git"
    GitRepo.init(bare, bare=True)
    work = ms.checkout_meta(str(bare), "seed-work")
    ms.save_course(work, course, prefix, template, tas=list(tas), rows=list(rows))
    ms.commit_and_push(work, "seed")
    env.org._repos.append(FakeRepo(ORG, "meta", clone_url=str(bare)))


def meta_state(env, course=COURSE):
    """the course state as the commands see it, from a fresh checkout."""
    return ms.load_meta_courses(env.gh, ORG)[course]


class TestMetaInit:
    def test_dryrun_previews_and_creates_nothing(self, env):
        result = run(env.runner, "meta", "init", ORG, "--prefix", PREFIX)
        assert result.exit_code == 0, result.output
        assert "would create private" in result.output
        assert "would record" in result.output
        assert env.org.created_repos == []

    def test_creates_meta_repo_and_records_the_course(self, env):
        result = run(env.runner, "meta", "init", ORG, "--prefix", PREFIX,
                     "--template", f"{ORG}/Template", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert ("meta", None) in env.org.created_repos

        course = normalize_org_course(env)
        assert course["prefix"] == PREFIX
        assert course["template"] == f"{ORG}/Template"

    def test_rerun_is_idempotent(self, env):
        run(env.runner, "meta", "init", ORG, "--prefix", PREFIX, "--no-dryrun")
        result = run(env.runner, "meta", "init", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert env.org.created_repos.count(("meta", None)) == 1
        assert normalize_org_course(env)["prefix"] == PREFIX

    def test_seeds_tas_from_canvas(self, env, config_file, fake_canvas, monkeypatch):
        monkeypatch.setattr(core, "get_canvas", lambda: fake_canvas)
        monkeypatch.setattr(repos_cmd, "get_canvas", lambda: fake_canvas)
        result = run(env.runner, "meta", "init", "195A", "--prefix", PREFIX,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(env)["tas"] == ["profbeth"]


def normalize_org_course(env):
    """course state for the no-config case, where the org names the course dir."""
    course = core.normalize_course_name(ORG)
    return ms.load_meta_courses(env.gh, ORG)[course]


class TestMetaShow:
    def test_shows_recorded_state(self, env):
        seed_meta(env, tas=["ta-one"],
                  rows=[{"name": "team-1", "students": ["jdoe"],
                         "repo": None, "repo_id": None}])
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert f"PREFIX    {PREFIX}" in result.output
        assert "TAS       ta-one" in result.output
        assert "team-1" in result.output

    def test_errors_without_a_meta_repo(self, env):
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 2
        assert "no meta repo" in result.output


class TestMetaAssign:
    def table(self, tmp_path, text):
        path = tmp_path / "teams.tsv"
        path.write_text(text)
        return str(path)

    def test_dryrun_previews_and_touches_nothing(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "NAME STUDENTS\nteam-1 jane@sjsu.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table)
        assert result.exit_code == 0, result.output
        assert f"would create private {ORG}/{PREFIX}-team-1" in result.output
        assert "would grant push to jdoe" in result.output
        assert "would grant push to msmith" in result.output
        assert env.org.created_repos == []
        assert meta_state(env)["rows"] == []

    def test_creates_records_and_grants(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template")
        table = self.table(tmp_path, "team-1 jane@sjsu.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output

        # created privately from the template
        assert (f"{PREFIX}-team-1", f"{ORG}/Template") in env.org.created_repos
        created = env.gh.get_repo(f"{ORG}/{PREFIX}-team-1")
        assert ("add", "jdoe", "push") in created.collab_log
        assert ("add", "msmith", "push") in created.collab_log

        # recorded with url and permanent id
        row = meta_state(env)["rows"][0]
        assert row["repo"] == created.html_url
        assert row["repo_id"] == created.id

    def test_unresolvable_email_is_a_noticeable_error(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 nobody@nowhere.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 1
        assert 'cannot resolve "nobody@nowhere.edu"' in result.output
        # the repo still exists and the resolvable student still got access
        created = env.gh.get_repo(f"{ORG}/{PREFIX}-team-1")
        assert ("add", "msmith", "push") in created.collab_log

    def test_reimport_never_clobbers_the_recorded_repo(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 msmith\n")
        run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        recorded = meta_state(env)["rows"][0]["repo_id"]

        table2 = self.table(tmp_path, "team-1 msmith,jdoe\n")
        result = run(env.runner, "meta", "assign", ORG, table2, "--no-dryrun")
        assert result.exit_code == 0, result.output
        row = meta_state(env)["rows"][0]
        assert row["repo_id"] == recorded
        assert row["students"] == ["msmith", "jdoe"]

    def test_identical_reimport_does_nothing(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 msmith\n")
        run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output


class TestMetaApply:
    def setup_realized(self, env):
        """a realized row whose repo has drifted from the recorded state."""
        repo = FakeRepo(ORG, f"{PREFIX}-team-1", collaborators=[
            FakeNamedUser("jdoe", role_name="write"),
            FakeNamedUser("intruder", role_name="write"),
            FakeNamedUser("prof", role_name="admin", admin=True),
        ])
        env.org._repos.append(repo)
        seed_meta(env, tas=["ta-one"],
                  rows=[{"name": "team-1", "students": ["jdoe", "msmith"],
                         "repo": repo.html_url, "repo_id": repo.id}])
        return repo

    def test_dryrun_previews_the_full_reconcile(self, env):
        repo = self.setup_realized(env)
        result = run(env.runner, "meta", "apply", ORG)
        assert result.exit_code == 0, result.output
        assert "would grant push to msmith" in result.output
        assert "would revoke intruder" in result.output
        assert 'would create team "tas"' in result.output
        assert 'would add ta-one to team "tas"' in result.output
        assert f'would grant team "tas" pull on {repo.full_name}' in result.output
        assert repo.collab_log == []

    def test_reconciles_and_never_touches_admins(self, env):
        repo = self.setup_realized(env)
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output

        assert ("add", "msmith", "push") in repo.collab_log
        assert ("remove", "intruder", None) in repo.collab_log
        assert not any(login == "prof" for _op, login, _p in repo.collab_log)

        team = env.org.get_team_by_slug("tas")
        assert [m.login for m in team.get_members()] == ["ta-one"]
        assert ("grant", repo.full_name, "pull") in team.log

    def test_second_apply_has_nothing_to_do(self, env):
        self.setup_realized(env)
        run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output

    def test_realizes_hand_added_rows(self, env):
        seed_meta(env, rows=[{"name": "late-team", "students": ["msmith"],
                              "repo": None, "repo_id": None}])
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = env.gh.get_repo(f"{ORG}/{PREFIX}-late-team")
        assert ("add", "msmith", "push") in created.collab_log
        assert meta_state(env)["rows"][0]["repo_id"] == created.id

    def test_team_pull_covers_renamed_recorded_repos(self, env):
        renamed = FakeRepo(ORG, "totally-renamed", collaborators=[])
        env.org._repos.append(renamed)
        seed_meta(env, rows=[{"name": "team-r", "students": [],
                              "repo": renamed.html_url, "repo_id": renamed.id}])
        run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        team = env.org.get_team_by_slug("tas")
        assert ("grant", renamed.full_name, "pull") in team.log


class TestMetaDiscovery:
    def test_repos_list_recovers_renamed_repos(self, env):
        env.org._repos.append(FakeRepo(ORG, f"{PREFIX}-team-1"))
        renamed = FakeRepo(ORG, "totally-renamed")
        env.org._repos.append(renamed)
        seed_meta(env, rows=[{"name": "team-r", "students": [],
                              "repo": renamed.html_url, "repo_id": renamed.id}])

        result = run(env.runner, "repos", "list", ORG, "project")
        assert result.exit_code == 0, result.output
        teams = [line.strip() for line in result.output.splitlines()[1:]]
        assert "team-1" in teams
        assert "team-r" in teams

    def test_assignment_arg_matches_the_meta_prefix(self, env):
        # "project" is nowhere in the repo names' own first segment, but the
        # meta prefix anchors it and teams strip the whole prefix
        env.org._repos.append(FakeRepo(ORG, f"{PREFIX}-red-team"))
        seed_meta(env)
        result = run(env.runner, "repos", "list", ORG, "project")
        assert result.exit_code == 0, result.output
        assert "red-team" in result.output

    def test_classrooms_prefers_meta_prefixes(self, env, tmp_path, monkeypatch):
        seed_meta(env)
        path = tmp_path / "cfg.ini"
        path.write_text(f"[CANVAS]\nurl = u\ntoken = t\n\n[COURSES]\nCMPE-195A = {ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(env.runner, "classrooms")
        assert result.exit_code == 0, result.output
        assert f"{ORG}: {PREFIX}" in result.output
