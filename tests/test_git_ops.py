import os
from datetime import datetime

import pytest
from git import GitCommandError
from git import Repo as GitRepo

from gh_class_sak import git_ops
from gh_class_sak.git_ops import push_template


def make_template(tmp_path):
    origin = tmp_path / "starter"
    origin.mkdir()
    source = GitRepo.init(origin)
    (origin / "README.md").write_text("starter\n")
    source.index.add(["README.md"])
    source.index.commit("starter")
    return str(origin)


class TestPushTemplate:
    def test_pushes_to_the_named_branch(self, tmp_path):
        dest = tmp_path / "dest.git"
        GitRepo.init(dest, bare=True)
        push_template(make_template(tmp_path), str(dest), branch="trunk")
        pushed = GitRepo(str(dest))
        assert "README.md" in pushed.git.ls_tree("trunk", name_only=True)
        assert len(list(pushed.iter_commits("trunk"))) == 1

    def test_unreachable_template_cleans_its_workdir(self, tmp_path, monkeypatch):
        made = []
        real = git_ops.tempfile.mkdtemp

        def recording(**kwargs):
            made.append(real(**kwargs))
            return made[-1]

        monkeypatch.setattr(git_ops.tempfile, "mkdtemp", recording)
        with pytest.raises(GitCommandError):
            push_template(str(tmp_path / "no-such-template"),
                          str(tmp_path / "dest.git"))
        assert made and not os.path.exists(made[0])


def dated_origin(tmp_path, *dates):
    """a repo with one commit per date (committer and author dates both)."""
    origin = tmp_path / "origin"
    origin.mkdir(exist_ok=True)
    repo = GitRepo.init(origin)
    shas = []
    for n, date in enumerate(dates):
        (origin / "work.txt").write_text(f"version {n}\n")
        repo.index.add(["work.txt"])
        raw = f"{int(datetime.fromisoformat(date).timestamp())} +0000"
        shas.append(repo.index.commit(f"v{n}", author_date=raw,
                                      commit_date=raw).hexsha)
    return repo, shas


class TestCheckoutBefore:
    DEADLINE = "2026-10-01T23:59:59+00:00"

    def deadline(self):
        return datetime.fromisoformat(self.DEADLINE)

    def test_detaches_at_the_last_commit_before_the_deadline(self, tmp_path):
        _origin, shas = dated_origin(tmp_path, "2026-09-28T10:00:00+00:00",
                                     "2026-10-01T22:00:00+00:00",
                                     "2026-10-02T09:00:00+00:00")
        dest = str(tmp_path / "clone")
        assert git_ops.clone_or_update(str(tmp_path / "origin"), dest) == "cloned"
        # the commit's date is reported in local time
        local = datetime.fromisoformat("2026-10-01T22:00:00+00:00").astimezone()
        assert git_ops.checkout_before(dest, self.deadline()) == (
            shas[1][:7], local.strftime("%Y-%m-%d %H:%M"))
        assert GitRepo(dest).head.commit.hexsha == shas[1]

    def test_no_commit_that_old_leaves_the_checkout_alone(self, tmp_path):
        _origin, shas = dated_origin(tmp_path, "2026-10-05T10:00:00+00:00")
        dest = str(tmp_path / "clone")
        git_ops.clone_or_update(str(tmp_path / "origin"), dest)
        assert git_ops.checkout_before(dest, self.deadline()) is None
        assert GitRepo(dest).head.commit.hexsha == shas[0]

    def test_a_detached_checkout_still_updates(self, tmp_path):
        origin, _shas = dated_origin(tmp_path, "2026-09-28T10:00:00+00:00",
                                     "2026-10-02T09:00:00+00:00")
        dest = str(tmp_path / "clone")
        git_ops.clone_or_update(str(tmp_path / "origin"), dest)
        git_ops.checkout_before(dest, self.deadline())
        (tmp_path / "origin" / "work.txt").write_text("late\n")
        origin.index.add(["work.txt"])
        late = origin.index.commit("late").hexsha
        assert git_ops.clone_or_update(str(tmp_path / "origin"), dest) == "updated"
        assert GitRepo(dest).head.commit.hexsha == late
