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
from tests.fakes import FakeBranchProtection, FakeGithub, FakeNamedUser, FakeOrg, FakeRepo

PREFIX = "sp26-cmpe-195a"
ASSIGNMENT = "project"
REPO_PREFIX = f"{PREFIX}-{ASSIGNMENT}"  # prefix + assignment: the repo-name stem
COURSE = "cmpe_195a"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """a fake org whose created repos and classroom-meta repo are real local bare gits."""
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


def seed_meta(env, course=COURSE, prefix=PREFIX, template=None, tas=(),
              assignments=None, **settings):
    """put a classroom-meta repo with recorded state into the fake org.

    call it again with another course to seed a second classroom directory.
    """
    bare = env.root / "classroom-meta.git"
    GitRepo.init(bare, bare=True)
    work = ms.checkout_meta(str(bare), "seed-work")
    ms.save_classroom(work, course, prefix, template, tas=list(tas),
                      assignments=assignments, **settings)
    ms.commit_and_push(work, "seed")
    if not any(r.name == "classroom-meta" for r in env.org.get_repos()):
        env.org._repos.append(FakeRepo(ORG, "classroom-meta", clone_url=str(bare)))


def meta_state(env, course=COURSE):
    """the course state as the commands see it, from a fresh checkout."""
    return ms.load_meta_classrooms(env.gh, ORG)[course]


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
        assert ("classroom-meta", None) in env.org.created_repos

        course = normalize_org_course(env)
        assert course["prefix"] == PREFIX
        assert course["template"] == f"{ORG}/Template"

    def test_rerun_is_idempotent(self, env):
        run(env.runner, "meta", "init", ORG, "--prefix", PREFIX, "--no-dryrun")
        result = run(env.runner, "meta", "init", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert env.org.created_repos.count(("classroom-meta", None)) == 1
        assert normalize_org_course(env)["prefix"] == PREFIX

    def test_init_without_prefix_records_none(self, env):
        result = run(env.runner, "meta", "init", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "prefix=-" in result.output
        assert normalize_org_course(env)["prefix"] is None

    def test_init_never_infers_a_prefix_from_repo_names(self, env):
        # the old model inferred a shared prefix from org repos; the prefix is
        # now only ever what --prefix or an existing classroom.ini says
        env.org._repos += [FakeRepo(ORG, "x-a"), FakeRepo(ORG, "x-b")]
        result = run(env.runner, "meta", "init", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert normalize_org_course(env)["prefix"] is None

    def test_init_creates_no_assignment_files(self, env):
        run(env.runner, "meta", "init", ORG, "--prefix", PREFIX, "--no-dryrun")
        assert normalize_org_course(env)["assignments"] == {}

    def test_seeds_tas_from_canvas(self, env, config_file, fake_canvas, monkeypatch):
        monkeypatch.setattr(core, "get_canvas", lambda: fake_canvas)
        monkeypatch.setattr(repos_cmd, "get_canvas", lambda: fake_canvas)
        result = run(env.runner, "meta", "init", "195A", "--prefix", PREFIX,
                     "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(env)["tas"] == ["profbeth"]

    def test_rerun_preserves_repo_settings(self, env):
        seed_meta(env, course=core.normalize_course_name(ORG), protection="pr-review")
        result = run(env.runner, "meta", "init", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert normalize_org_course(env)["protection"] == "pr-review"


def normalize_org_course(env):
    """course state for the no-config case, where the org names the course dir."""
    course = core.normalize_course_name(ORG)
    return ms.load_meta_classrooms(env.gh, ORG)[course]


class TestMetaShow:
    def test_shows_recorded_state(self, env):
        seed_meta(env, tas=["ta-one"],
                  assignments={ASSIGNMENT: [{"name": "team-1", "students": ["jdoe"],
                                             "repo": None, "repo_id": None}]})
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert f"PREFIX    {PREFIX}" in result.output
        assert "TAS       ta-one" in result.output
        assert f"ASSIGNMENT {ASSIGNMENT}" in result.output
        assert "team-1" in result.output

    def test_shows_one_table_per_assignment(self, env):
        seed_meta(env, assignments={
            "project": [{"name": "team-1", "students": [],
                         "repo": None, "repo_id": None}],
            "hw1": [{"name": "solo", "students": [],
                     "repo": None, "repo_id": None}],
        })
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert result.output.index("ASSIGNMENT hw1") \
            < result.output.index("ASSIGNMENT project")
        assert "solo" in result.output
        assert "team-1" in result.output

    def test_unset_prefix_shows_a_dash(self, env):
        seed_meta(env, prefix=None)
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert "PREFIX    -" in result.output
        assert "(no assignments)" in result.output

    def test_shows_effective_settings(self, env):
        seed_meta(env, protection="pr-review")
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 0, result.output
        assert ("SETTINGS  protection=pr-review linear_history=true force_push=false"
                in result.output)

    def test_errors_without_a_meta_repo(self, env):
        result = run(env.runner, "meta", "show", ORG)
        assert result.exit_code == 2
        assert "no classroom-meta repo" in result.output


class TestMetaAssign:
    def table(self, tmp_path, text, name=f"{ASSIGNMENT}.tsv"):
        path = tmp_path / name
        path.write_text(text)
        return str(path)

    def test_dryrun_previews_and_touches_nothing(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "NAME STUDENTS\nteam-1 jane@sjsu.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table)
        assert result.exit_code == 0, result.output
        assert f"would create private {ORG}/{REPO_PREFIX}-team-1" in result.output
        assert "would grant push to jdoe" in result.output
        assert "would grant push to msmith" in result.output
        assert env.org.created_repos == []
        assert meta_state(env)["assignments"] == {}

    def test_creates_records_and_grants(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template")
        table = self.table(tmp_path, "team-1 jane@sjsu.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output

        # created privately from the template
        assert (f"{REPO_PREFIX}-team-1", f"{ORG}/Template") in env.org.created_repos
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert ("add", "jdoe", "push") in created.collab_log
        assert ("add", "msmith", "push") in created.collab_log

        # recorded with url and permanent id
        row = meta_state(env)["assignments"][ASSIGNMENT][0]
        assert row["repo"] == created.html_url
        assert row["repo_id"] == created.id

    def test_assignment_defaults_to_the_table_basename(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "solo msmith\n", name="hw1.tsv")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert env.gh.get_repo(f"{ORG}/{PREFIX}-hw1-solo") is not None
        assert list(meta_state(env)["assignments"]) == ["hw1"]

    def test_assignment_flag_overrides_the_basename(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "solo msmith\n", name="teams.tsv")
        result = run(env.runner, "meta", "assign", ORG, table,
                     "--assignment", "hw2", "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert env.gh.get_repo(f"{ORG}/{PREFIX}-hw2-solo") is not None
        assert list(meta_state(env)["assignments"]) == ["hw2"]

    def test_rejects_an_assignment_name_with_spaces(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "solo msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table,
                     "--assignment", "bad name")
        assert result.exit_code == 2
        assert 'assignment name "bad name"' in result.output

    def test_empty_prefix_drops_its_segment(self, env, tmp_path):
        seed_meta(env, prefix=None)
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert env.gh.get_repo(f"{ORG}/{ASSIGNMENT}-team-1") is not None

    def test_unresolvable_email_is_a_noticeable_error(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 nobody@nowhere.edu,msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 1
        assert 'cannot resolve "nobody@nowhere.edu"' in result.output
        # the repo still exists and the resolvable student still got access
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert ("add", "msmith", "push") in created.collab_log

    def test_reimport_never_clobbers_the_recorded_repo(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 msmith\n")
        run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        recorded = meta_state(env)["assignments"][ASSIGNMENT][0]["repo_id"]

        table2 = self.table(tmp_path, "team-1 msmith,jdoe\n")
        result = run(env.runner, "meta", "assign", ORG, table2, "--no-dryrun")
        assert result.exit_code == 0, result.output
        row = meta_state(env)["assignments"][ASSIGNMENT][0]
        assert row["repo_id"] == recorded
        assert row["students"] == ["msmith", "jdoe"]

    def test_identical_reimport_does_nothing(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 msmith\n")
        run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output

    def test_created_template_repo_gets_default_protection(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template")
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert created.protection_log == [
            ("main", {"required_linear_history": True, "allow_force_pushes": False})]

    def test_pr_review_setting_requires_one_approval(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template", protection="pr-review")
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        _branch, kwargs = created.protection_log[0]
        assert kwargs["required_approving_review_count"] == 1

    def test_noop_settings_skip_protection_entirely(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template", protection="none",
                  linear_history=False, force_push=True)
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert created.protection_log == []
        assert "protect" not in result.output

    def test_bare_created_repo_warns_protection_pending(self, env, tmp_path):
        seed_meta(env)
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "starts with no branch" in result.output
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-team-1")
        assert created.protection_log == []

    def test_dryrun_previews_protection(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template")
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table)
        assert result.exit_code == 0, result.output
        assert "would protect default branch on" in result.output
        assert env.org.created_repos == []

    def test_settings_survive_a_rewrite(self, env, tmp_path):
        seed_meta(env, template=f"{ORG}/Template", protection="pr-review")
        table = self.table(tmp_path, "team-1 msmith\n")
        result = run(env.runner, "meta", "assign", ORG, table, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert meta_state(env)["protection"] == "pr-review"


class TestMetaApply:
    def setup_realized(self, env):
        """a realized row whose repo has drifted from the recorded state."""
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[
            FakeNamedUser("jdoe", role_name="write"),
            FakeNamedUser("intruder", role_name="write"),
            FakeNamedUser("prof", role_name="admin", admin=True),
        ])
        env.org._repos.append(repo)
        seed_meta(env, tas=["ta-one"],
                  assignments={ASSIGNMENT: [
                      {"name": "team-1", "students": ["jdoe", "msmith"],
                       "repo": repo.html_url, "repo_id": repo.id}]})
        return repo

    def test_dryrun_previews_the_full_reconcile(self, env):
        repo = self.setup_realized(env)
        result = run(env.runner, "meta", "apply", ORG)
        assert result.exit_code == 0, result.output
        assert "would grant push to msmith" in result.output
        assert "would revoke intruder" in result.output
        assert 'would create team "cmpe_195a-tas"' in result.output
        assert 'would add ta-one to team "cmpe_195a-tas"' in result.output
        assert f'would grant team "cmpe_195a-tas" pull on {repo.full_name}' in result.output
        assert repo.collab_log == []

    def test_reconciles_and_never_touches_admins(self, env):
        repo = self.setup_realized(env)
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output

        assert ("add", "msmith", "push") in repo.collab_log
        assert ("remove", "intruder", None) in repo.collab_log
        assert not any(login == "prof" for _op, login, _p in repo.collab_log)

        team = env.org.get_team_by_slug("cmpe_195a-tas")
        assert [m.login for m in team.get_members()] == ["ta-one"]
        assert ("grant", repo.full_name, "pull") in team.log

    def test_second_apply_has_nothing_to_do(self, env):
        self.setup_realized(env)
        run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output

    def test_realizes_hand_added_rows(self, env):
        seed_meta(env, assignments={ASSIGNMENT: [
            {"name": "late-team", "students": ["msmith"],
             "repo": None, "repo_id": None}]})
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        created = env.gh.get_repo(f"{ORG}/{REPO_PREFIX}-late-team")
        assert ("add", "msmith", "push") in created.collab_log
        assert meta_state(env)["assignments"][ASSIGNMENT][0]["repo_id"] == created.id

    def test_two_assignments_realize_union_and_span_the_tas_team(self, env):
        recorded = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[])
        env.org._repos.append(recorded)
        seed_meta(env, tas=["ta-one"], assignments={
            "hw1": [{"name": "solo", "students": ["msmith"],
                     "repo": None, "repo_id": None}],
            ASSIGNMENT: [{"name": "team-1", "students": [],
                          "repo": recorded.html_url, "repo_id": recorded.id}],
        })
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output

        created = env.gh.get_repo(f"{ORG}/{PREFIX}-hw1-solo")
        assert created is not None
        team = env.org.get_team_by_slug("cmpe_195a-tas")
        assert ("grant", created.full_name, "pull") in team.log
        assert ("grant", recorded.full_name, "pull") in team.log

    def test_universe_dedups_a_repo_recorded_twice(self, env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[])
        env.org._repos.append(repo)
        row = {"name": "team-1", "students": [],
               "repo": repo.html_url, "repo_id": repo.id}
        seed_meta(env, assignments={"hw1": [dict(row)], ASSIGNMENT: [dict(row)]})
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        team = env.org.get_team_by_slug("cmpe_195a-tas")
        grants = [entry for entry in team.log
                  if entry == ("grant", repo.full_name, "pull")]
        assert len(grants) == 1

    def test_each_classroom_gets_its_own_tas_team(self, env):
        # two classrooms in one org: TAs of one never gain access to the other
        repo_a = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", collaborators=[])
        repo_b = FakeRepo(ORG, "sp26-cmpe-195b-project-team-9", collaborators=[])
        env.org._repos += [repo_a, repo_b]
        seed_meta(env, course="cmpe_195a", prefix=PREFIX,
                  tas=["ta-ana"],
                  assignments={ASSIGNMENT: [
                      {"name": "team-1", "students": [],
                       "repo": repo_a.html_url, "repo_id": repo_a.id}]})
        seed_meta(env, course="cmpe_195b", prefix="sp26-cmpe-195b",
                  tas=["ta-bob"],
                  assignments={ASSIGNMENT: [
                      {"name": "team-9", "students": [],
                       "repo": repo_b.html_url, "repo_id": repo_b.id}]})

        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output

        team_a = env.org.get_team_by_slug("cmpe_195a-tas")
        team_b = env.org.get_team_by_slug("cmpe_195b-tas")
        assert [m.login for m in team_a.get_members()] == ["ta-ana"]
        assert [m.login for m in team_b.get_members()] == ["ta-bob"]
        assert ("grant", repo_a.full_name, "pull") in team_a.log
        assert ("grant", repo_b.full_name, "pull") not in team_a.log
        assert ("grant", repo_b.full_name, "pull") in team_b.log
        assert ("grant", repo_a.full_name, "pull") not in team_b.log

    def test_team_pull_covers_renamed_recorded_repos(self, env):
        renamed = FakeRepo(ORG, "totally-renamed", collaborators=[])
        env.org._repos.append(renamed)
        seed_meta(env, assignments={ASSIGNMENT: [
            {"name": "team-r", "students": [],
             "repo": renamed.html_url, "repo_id": renamed.id}]})
        run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        team = env.org.get_team_by_slug("cmpe_195a-tas")
        assert ("grant", renamed.full_name, "pull") in team.log

    def test_apply_protects_recorded_repos(self, env):
        repo = self.setup_realized(env)
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert f"protect main on {repo.full_name}" in result.output
        assert repo.protection_log == [
            ("main", {"required_linear_history": True, "allow_force_pushes": False})]

    def test_apply_reconciles_drifted_protection(self, env):
        repo = self.setup_realized(env)
        run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        repo.protection_log.clear()
        # someone hand-tightened the branch to require reviews
        repo._protection = FakeBranchProtection(
            {"required_approving_review_count": 1}, True, False)
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert repo.protection_log == [
            ("main", {"required_linear_history": True, "allow_force_pushes": False})]

    def test_apply_heals_protection_after_first_push(self, env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", has_branch=False)
        env.org._repos.append(repo)
        seed_meta(env, assignments={ASSIGNMENT: [
            {"name": "team-1", "students": [],
             "repo": repo.html_url, "repo_id": repo.id}]})
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "no main branch to protect yet" in result.output
        assert repo.protection_log == []

        repo._has_branch = True  # a student pushed
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert repo.protection_log == [
            ("main", {"required_linear_history": True, "allow_force_pushes": False})]

    def test_plan_403_warns_and_stays_idempotent(self, env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1", protection_403=True)
        env.org._repos.append(repo)
        seed_meta(env, assignments={ASSIGNMENT: [
            {"name": "team-1", "students": [],
             "repo": repo.html_url, "repo_id": repo.id}]})
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "paid plan" in result.output
        assert repo.protection_log == []

        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert "nothing to do" in result.output

    def test_noop_settings_never_delete_hand_protection(self, env):
        repo = FakeRepo(ORG, f"{REPO_PREFIX}-team-1")
        repo._protection = FakeBranchProtection(
            {"required_approving_review_count": 1}, True, False)
        env.org._repos.append(repo)
        seed_meta(env, protection="none", linear_history=False, force_push=True,
                  assignments={ASSIGNMENT: [
                      {"name": "team-1", "students": [],
                       "repo": repo.html_url, "repo_id": repo.id}]})
        result = run(env.runner, "meta", "apply", ORG, "--no-dryrun")
        assert result.exit_code == 0, result.output
        assert repo.protection_log == []
        assert repo._protection is not None


class TestMetaDiscovery:
    def test_repos_list_recovers_renamed_repos(self, env):
        env.org._repos.append(FakeRepo(ORG, f"{REPO_PREFIX}-team-1"))
        renamed = FakeRepo(ORG, "totally-renamed")
        env.org._repos.append(renamed)
        seed_meta(env, assignments={ASSIGNMENT: [
            {"name": "team-r", "students": [],
             "repo": renamed.html_url, "repo_id": renamed.id}]})

        result = run(env.runner, "repos", "list", ORG, "project")
        assert result.exit_code == 0, result.output
        teams = [line.strip() for line in result.output.splitlines()[1:]]
        assert "team-1" in teams
        assert "team-r" in teams

    def test_assignment_arg_matches_a_tsv_name(self, env):
        # "proj" appears in no repo name segment, but it substring-matches the
        # project tsv, whose joined prefix anchors the repos; teams strip it all
        env.org._repos.append(FakeRepo(ORG, f"{REPO_PREFIX}-red-team"))
        seed_meta(env, assignments={ASSIGNMENT: []})
        result = run(env.runner, "repos", "list", ORG, "proj")
        assert result.exit_code == 0, result.output
        assert "red-team" in result.output

    def test_repos_list_selects_among_multiple_tsvs(self, env):
        env.org._repos += [FakeRepo(ORG, f"{PREFIX}-hw1-alice"),
                           FakeRepo(ORG, f"{REPO_PREFIX}-team-1")]
        seed_meta(env, assignments={"hw1": [], ASSIGNMENT: []})
        result = run(env.runner, "repos", "list", ORG, "hw1")
        assert result.exit_code == 0, result.output
        assert "alice" in result.output
        assert "team-1" not in result.output

    def test_exact_match_beats_substring(self, env):
        env.org._repos.append(FakeRepo(ORG, f"{PREFIX}-hw1-alice"))
        seed_meta(env, assignments={"hw1": [], "hw1-bonus": []})
        result = run(env.runner, "repos", "list", ORG, "hw1")
        assert result.exit_code == 0, result.output
        assert "alice" in result.output

    def test_ambiguous_assignment_across_classrooms_exits_2(self, env):
        seed_meta(env, course="cmpe_195a", assignments={ASSIGNMENT: []})
        seed_meta(env, course="cmpe_195b", prefix="sp26-cmpe-195b",
                  assignments={ASSIGNMENT: []})
        result = run(env.runner, "repos", "list", ORG, "project")
        assert result.exit_code == 2
        assert 'assignment "project" is ambiguous' in result.output
        assert "cmpe_195a: project" in result.output
        assert "cmpe_195b: project" in result.output

    def test_naming_the_classroom_disambiguates(self, env, tmp_path, monkeypatch):
        env.org._repos.append(FakeRepo(ORG, f"{REPO_PREFIX}-team-1"))
        seed_meta(env, course="cmpe_195a", assignments={ASSIGNMENT: []})
        seed_meta(env, course="cmpe_195b", prefix="sp26-cmpe-195b",
                  assignments={ASSIGNMENT: []})
        path = tmp_path / "cfg.ini"
        path.write_text(f"[CANVAS]\nurl = u\ntoken = t\n\n[COURSES]\nCMPE-195A = {ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(env.runner, "repos", "list", "195A", "project")
        assert result.exit_code == 0, result.output
        assert "team-1" in result.output

    def test_classrooms_lists_meta_classroom_dirs(self, env, tmp_path, monkeypatch):
        # with a classroom-meta repo, each classroom directory is a classroom —
        # not the org — and each of its assignment tsvs gets a line
        seed_meta(env, assignments={ASSIGNMENT: []})
        path = tmp_path / "cfg.ini"
        path.write_text(f"[CANVAS]\nurl = u\ntoken = t\n\n[COURSES]\nCMPE-195A = {ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(env.runner, "classrooms")
        assert result.exit_code == 0, result.output
        assert f"{COURSE}: {ASSIGNMENT}" in result.output
        assert f"{ORG}: {ASSIGNMENT}" not in result.output

    def test_classrooms_prints_no_assignments_for_an_empty_classroom(
            self, env, tmp_path, monkeypatch):
        seed_meta(env)
        path = tmp_path / "cfg.ini"
        path.write_text(f"[CANVAS]\nurl = u\ntoken = t\n\n[COURSES]\nCMPE-195A = {ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(env.runner, "classrooms")
        assert result.exit_code == 0, result.output
        assert f"{COURSE}: (no assignments)" in result.output
