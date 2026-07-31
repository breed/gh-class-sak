import sys
import unicodedata
from collections import Counter

from github import GithubException

from gh_class_sak.core import error, warn


def _exc_message(exc):
    """the human-readable message out of a GithubException, whatever its shape."""
    data = getattr(exc, "data", None)
    if isinstance(data, dict) and data.get("message"):
        return data["message"]
    return str(data or exc)


def get_org(gh, org_name):
    return gh.get_organization(org_name)


def list_org_repos(gh, org_name):
    """all repos in an org. iterates the PaginatedList so every page is fetched."""
    try:
        return list(get_org(gh, org_name).get_repos())
    except GithubException as exc:
        error(f'cannot list repos for org "{org_name}": {_exc_message(exc)}')
        sys.exit(2)


def github_safe_name(name):
    """a person's or group's name as a valid github repo-name fragment.

    accented letters lose their accents, anything github won't take in a
    repo name becomes "-", runs collapse, and the edges are trimmed.
    """
    ascii_name = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(ch for ch in ascii_name if not unicodedata.combining(ch))
    safe = "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "._-" else "-"
                   for ch in ascii_name)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-._") or "x"


def team_name(repo_name, prefix):
    """the team is the repo name with the assignment prefix stripped off."""
    if prefix and repo_name.lower().startswith(prefix.lower()):
        team = repo_name[len(prefix):].lstrip("-")
        if team:
            return team
    return repo_name


def find_assignment_repos(repos, prefix):
    """select the repos whose names carry an assignment's prefix, as
    [(team, repo)].

    a leading-prefix match only: the caller resolved the assignment against
    the classroom-meta first, so the prefix is exact — a looser match would
    drag in other classrooms' repos. repos named differently are still found
    through their recorded ids.
    """
    lowered = prefix.lower()
    matched = [r for r in repos if r.name.lower().startswith(lowered)]
    return [(team_name(r.name, prefix), r) for r in matched]


def infer_assignment_prefixes(repo_names):
    """guess assignment prefixes from repo names shaped as PREFIX-TEAM.

    the migration path for orgs left behind by GitHub Classroom, which named
    repos this way. a candidate is any leading run of '-' separated parts
    shared by at least two repos. two rules then cut the candidates down to
    plausible assignments:

    - if a longer candidate covers exactly the same repos, it is more specific
      and wins ("hw1" loses to "hw1-part2" when every hw1 repo is hw1-part2)
    - once a prefix is accepted, anything extending it is a team naming pattern
      rather than a separate assignment ("group-project-team" under
      "group-project"), so it is suppressed
    """
    counts = Counter()
    for name in repo_names:
        parts = name.split("-")
        for k in range(1, len(parts)):
            counts["-".join(parts[:k])] += 1

    shared = {p: c for p, c in counts.items() if c >= 2}

    # keep the most specific prefix of each equal-coverage chain
    specific = {p: c for p, c in shared.items()
                if not any(o != p and o.startswith(p + "-") and shared[o] == c
                           for o in shared)}

    # broadest first, so an assignment claims its own sub-patterns
    accepted = []
    for prefix, count in sorted(specific.items(), key=lambda pc: (-pc[1], len(pc[0]), pc[0])):
        if any(prefix.startswith(a + "-") for a, _ in accepted):
            continue
        accepted.append((prefix, count))

    accepted.sort(key=lambda pc: pc[0])
    return accepted


def split_collaborators(repo):
    """return (members, admins) as lists of NamedUser, admins excluded from members."""
    members = []
    admins = []
    for c in repo.get_collaborators():
        if _is_admin(c):
            admins.append(c)
        else:
            members.append(c)
    return members, admins


def _is_admin(collaborator):
    # role_name is only populated by the collaborators endpoint and reads None
    # otherwise, so fall through to permissions rather than firing a fetch.
    if collaborator.role_name == "admin":
        return True
    permissions = collaborator.permissions
    return bool(permissions and permissions.admin)


def list_commit_authors(repo):
    """(login, name, email) per commit, newest first as the API returns them.

    empty repos answer 409 from the commits endpoint; that is normal and yields
    no authors. any other failure — rate limiting, permissions — is warned
    about, so a truncated listing is never mistaken for a complete one.
    """
    authors = []
    try:
        for commit in repo.get_commits():
            author = commit.author
            login = author.login if author else None
            git_author = commit.commit.author if commit.commit else None
            name = git_author.name if git_author else ""
            email = git_author.email if git_author else ""
            authors.append((login, name or "", email or ""))
    except GithubException as exc:
        if exc.status != 409:
            warn(f"commit listing for {repo.full_name} failed: {_exc_message(exc)}")
    return authors


def resolve_email_to_username(gh, email):
    try:
        results = gh.search_users(f"{email} in:email")
        if results.totalCount == 1:
            return results[0].login
    except GithubException:
        pass
    return None


def resolve_name_to_username(gh, name):
    try:
        results = gh.search_users(f"fullname:{name}")
        if results.totalCount == 1:
            return results[0].login
    except GithubException:
        pass
    return None


def add_collaborator(repo, username, permission="push"):
    return repo.add_to_collaborators(username, permission)


def remove_collaborator(repo, username):
    return repo.remove_from_collaborators(username)


def get_org_repo(gh, org_name, repo_name):
    """a repo in the org, or None when it doesn't exist."""
    try:
        return gh.get_repo(f"{org_name}/{repo_name}")
    except GithubException:
        return None


def get_repo_by_id(gh, repo_id):
    """a repo by its permanent numeric id — survives renames. None if gone."""
    try:
        return gh.get_repo(int(repo_id))
    except GithubException:
        return None


def create_org_repo(gh, org_name, repo_name, template=None, auto_init=False):
    """create a private repo in the org, from a template repo when given."""
    org = get_org(gh, org_name)
    if template is not None:
        return org.create_repo_from_template(repo_name, template, private=True)
    return org.create_repo(repo_name, private=True, auto_init=auto_init)


# a branch with no protection enforces nothing: no review, no linear history,
# force pushes allowed. also the settings trio that asks for exactly that.
UNPROTECTED = ("none", False, True)


def _warn_unprotectable(repo, exc):
    """the two expected protection failures: branch not born yet, free plan."""
    if exc.status == 404:
        warn(f"{repo.full_name}: no {repo.default_branch} branch to protect yet;"
             " meta apply will protect it after the first push")
    else:
        warn(f"{repo.full_name}: branch protection needs a public repo or a paid"
             f" plan: {_exc_message(exc)}")


def read_default_branch_protection(repo):
    """(protection, linear_history, force_push) on the default branch, or None.

    an unprotected branch reads as UNPROTECTED. warns and returns None when the
    branch doesn't exist yet or the plan can't protect private repos.
    """
    try:
        branch = repo.get_branch(repo.default_branch)
    except GithubException as exc:
        if exc.status == 404:
            _warn_unprotectable(repo, exc)
            return None
        raise
    try:
        protection = branch.get_protection()
    except GithubException as exc:
        if exc.status == 404:
            return UNPROTECTED
        if exc.status == 403:
            _warn_unprotectable(repo, exc)
            return None
        raise
    return ("pr-review" if protection.required_pull_request_reviews else "none",
            bool(protection.required_linear_history),
            bool(protection.allow_force_pushes))


def protect_default_branch(repo, protection, linear_history, force_push):
    """put branch protection on the default branch; True when it took.

    the protection API replaces the whole object, so hand-set extras (status
    checks, push restrictions, ...) are wiped by a write. warns and returns
    False when the branch doesn't exist yet or the plan can't protect it.
    """
    kwargs = {"required_linear_history": linear_history,
              "allow_force_pushes": force_push}
    if protection == "pr-review":
        kwargs["required_approving_review_count"] = 1
    try:
        repo.get_branch(repo.default_branch).edit_protection(**kwargs)
    except GithubException as exc:
        if exc.status in (403, 404):
            _warn_unprotectable(repo, exc)
            return False
        raise
    return True


def pending_invitees(repo):
    """logins holding an unaccepted invitation to the repo."""
    try:
        return [inv.invitee.login for inv in repo.get_pending_invitations()
                if inv.invitee is not None]
    except GithubException:
        return []


def team_pending_invitations(team):
    """users invited to the team who haven't accepted yet.

    github's team membership API counts them as neither member nor absent,
    so callers must treat them as present or they re-invite forever.
    """
    try:
        return list(team.invitations())
    except (GithubException, AttributeError, TypeError):
        return []


def get_team(gh, org_name, slug):
    """a team in the org by slug, or None when it doesn't exist."""
    try:
        return get_org(gh, org_name).get_team_by_slug(slug)
    except GithubException:
        return None


def create_team(gh, org_name, name):
    return get_org(gh, org_name).create_team(name, privacy="closed")
