import atexit
import base64
import os
import shutil
import tempfile

from git import Actor, Git, GitCommandError, Repo


def auth_env(token):
    """git environment that authenticates github over https.

    uses GIT_CONFIG_COUNT (git >= 2.31) to inject an Authorization header for
    the duration of the command. the token never reaches argv, the clone url,
    or .git/config, so it cannot leak through `ps` or a checked-out worktree.
    """
    if not token:
        return {}
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    }


def remote_exists(url, token=None):
    """whether url is a reachable git repo, checked with ls-remote."""
    git = Git()
    try:
        with git.custom_environment(**auth_env(token)):
            git.ls_remote(url)
        return True
    except GitCommandError:
        return False


_template_sources = {}


def push_template(template_url, dest_url, token=None, branch="main"):
    """populate an empty repo with a template's current content.

    the template is shallow-cloned once per session, and its files become a
    single fresh commit — repos get the content, not the history — pushed as
    BRANCH to dest_url.
    """
    source = _template_sources.get(template_url)
    if source is None:
        workdir = tempfile.mkdtemp(prefix="gh-class-sak-template-")
        atexit.register(shutil.rmtree, workdir, ignore_errors=True)
        checkout = os.path.join(workdir, "content")
        try:
            Repo.clone_from(template_url, checkout, depth=1,
                            env=auth_env(token)).close()
            shutil.rmtree(os.path.join(checkout, ".git"))
            source = Repo.init(checkout)
            source.git.add("-A")
            actor = Actor("gh-class-sak", "gh-class-sak@localhost")
            source.index.commit(f"template from {template_url}",
                                author=actor, committer=actor)
        except BaseException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        _template_sources[template_url] = source
    with source.git.custom_environment(**auth_env(token)):
        source.git.push(dest_url, f"HEAD:refs/heads/{branch}")


def clone_or_update(clone_url, dest, token=None):
    """clone into dest, or fast-forward it if it already exists.

    returns one of:
      "cloned"       fresh clone
      "updated"      fast-forwarded to new commits
      "up-to-date"   nothing to pull
      "empty"        cloned while the repo had no commits, and it still has none
      "diverged"     local commits the remote doesn't have; not touched
      "pull-failed"  network, auth, or other pull error
      "not-a-repo"   dest exists but isn't a git checkout
      "failed"       clone error

    errors are reduced to a status rather than raised, because git's messages
    can echo back the url and we handle repos in bulk.
    """
    env = auth_env(token)

    if not os.path.exists(dest):
        try:
            # close the handle right away: an open Repo pins files on
            # windows, blocking later cleanup of the checkout
            Repo.clone_from(clone_url, dest, env=env).close()
        except GitCommandError:
            return "failed"
        return "cloned"

    try:
        repo = Repo(dest)
    except Exception:
        return "not-a-repo"

    with repo:
        before = repo.head.commit.hexsha if repo.head.is_valid() else None
        try:
            with repo.git.custom_environment(**env):
                repo.git.pull("--ff-only")
        except GitCommandError as exc:
            text = str(exc).lower()
            if "fast-forward" in text or "divergent" in text:
                return "diverged"
            if before is None:
                # an empty repo has no tracking branch to pull yet
                return "empty"
            return "pull-failed"
        after = repo.head.commit.hexsha if repo.head.is_valid() else None
        return "up-to-date" if before == after else "updated"
