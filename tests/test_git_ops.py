import os

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
