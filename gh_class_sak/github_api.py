import sys
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


def team_name(repo_name, prefix):
    """the team is the repo name with the assignment prefix stripped off."""
    if prefix and repo_name.lower().startswith(prefix.lower()):
        team = repo_name[len(prefix):].lstrip("-")
        if team:
            return team
    return repo_name


def find_assignment_repos(repos, prefix):
    """select the repos belonging to an assignment, as [(team, repo)].

    prefers a leading-prefix match; falls back to a substring match so a
    partial assignment name still resolves.
    """
    lowered = prefix.lower()
    matched = [r for r in repos if r.name.lower().startswith(lowered)]
    if not matched:
        matched = [r for r in repos if lowered in r.name.lower()]
    return [(team_name(r.name, prefix), r) for r in matched]


def infer_assignment_prefixes(repo_names):
    """guess assignment prefixes from repo names shaped as PREFIX-TEAM.

    a candidate is any leading run of '-' separated parts shared by at least
    two repos. two rules then cut the candidates down to plausible assignments:

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
