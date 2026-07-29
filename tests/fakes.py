"""Minimal stand-ins for the PyGithub and canvasapi objects the CLI touches.

Only the attributes gh_class_sak actually reads are implemented, so a missing
attribute here is a signal that production code started depending on something
new rather than a gap in the fake.
"""
from github import GithubException


class FakePermissions:
    def __init__(self, admin=False):
        self.admin = admin
        self.push = not admin
        self.pull = True


class FakeNamedUser:
    def __init__(self, login, name=None, email=None, role_name=None, admin=False):
        self.login = login
        self.name = name
        self.email = email
        self.role_name = role_name
        self.permissions = FakePermissions(admin=admin)


class FakeGitAuthor:
    def __init__(self, name, email):
        self.name = name
        self.email = email


class FakeCommitDetail:
    def __init__(self, name, email):
        self.author = FakeGitAuthor(name, email)


class FakeCommit:
    def __init__(self, login, name, email):
        self.author = FakeNamedUser(login) if login else None
        self.commit = FakeCommitDetail(name, email)


_repo_id_counter = [1000]


class FakeRepo:
    def __init__(self, org, name, collaborators=(), commits=(), commits_raise=False,
                 repo_id=None, clone_url=None):
        _repo_id_counter[0] += 1
        self.id = repo_id if repo_id is not None else _repo_id_counter[0]
        self.name = name
        self.full_name = f"{org}/{name}"
        self.html_url = f"https://github.com/{org}/{name}"
        self.clone_url = clone_url or f"https://github.com/{org}/{name}.git"
        self._collaborators = list(collaborators)
        self._commits = list(commits)
        self._commits_raise = commits_raise
        self.collab_log = []

    def get_collaborators(self):
        return list(self._collaborators)

    def add_to_collaborators(self, collaborator, permission="push"):
        login = getattr(collaborator, "login", collaborator)
        self.collab_log.append(("add", login, permission))
        role = "admin" if permission == "admin" else \
            ("read" if permission == "pull" else "write")
        self._collaborators = [c for c in self._collaborators if c.login != login]
        self._collaborators.append(
            FakeNamedUser(login, role_name=role, admin=permission == "admin"))

    def remove_from_collaborators(self, collaborator):
        login = getattr(collaborator, "login", collaborator)
        self.collab_log.append(("remove", login, None))
        self._collaborators = [c for c in self._collaborators if c.login != login]

    def get_commits(self):
        if self._commits_raise:
            raise GithubException(409, {"message": "Git Repository is empty."}, None)
        return list(self._commits)


class FakeTeam:
    def __init__(self, org, name):
        self.name = name
        self.slug = name.lower().replace(" ", "-")
        self._org = org
        self._members = {}
        self._repos = {}
        self.log = []

    def get_members(self):
        return list(self._members.values())

    def add_membership(self, member, role=None):
        self.log.append(("add-member", member.login))
        self._members[member.login] = member

    def remove_membership(self, member):
        self.log.append(("remove-member", member.login))
        self._members.pop(member.login, None)

    def get_repos(self):
        return [repo for repo, _perm in self._repos.values()]

    def update_team_repository(self, repo, permission):
        self.log.append(("grant", repo.full_name, permission))
        self._repos[repo.full_name] = (repo, permission)
        return True

    def remove_from_repos(self, repo):
        self.log.append(("revoke", repo.full_name))
        self._repos.pop(repo.full_name, None)


class FakeOrg:
    def __init__(self, login, repos=(), teams=(), local_git_root=None):
        self.login = login
        self._repos = list(repos)
        self._teams = {t.slug: t for t in teams}
        self.created_repos = []
        # when set, created repos get a real bare git origin under this dir,
        # so code that clones them works offline
        self.local_git_root = local_git_root

    def get_repos(self):
        return list(self._repos)

    def _new_repo(self, name, private):
        import os

        repo = FakeRepo(self.login, name)
        repo.private = private
        if self.local_git_root:
            from git import Repo as GitRepo

            bare = os.path.join(self.local_git_root, f"{name}.git")
            GitRepo.init(bare, bare=True)
            repo.clone_url = bare
        self._repos.append(repo)
        return repo

    def create_repo(self, name, private=False, auto_init=False, **_kwargs):
        repo = self._new_repo(name, private)
        self.created_repos.append((name, None))
        return repo

    def create_repo_from_template(self, name, repo, private=False, **_kwargs):
        created = self._new_repo(name, private)
        self.created_repos.append((name, repo.full_name))
        return created

    def get_team_by_slug(self, slug):
        if slug not in self._teams:
            raise GithubException(404, {"message": "Not Found"}, None)
        return self._teams[slug]

    def create_team(self, name, privacy=None, **_kwargs):
        team = FakeTeam(self, name)
        self._teams[team.slug] = team
        return team


class FakeSearchResult:
    def __init__(self, logins):
        self._users = [FakeNamedUser(login) for login in logins]

    @property
    def totalCount(self):
        return len(self._users)

    def __getitem__(self, index):
        return self._users[index]


class FakeAuthenticatedUser:
    def __init__(self, orgs):
        self._orgs = orgs

    def get_orgs(self):
        return list(self._orgs)


class FakeGithub:
    def __init__(self, orgs, users=None, search_results=None):
        self._orgs = {o.login: o for o in orgs}
        self._users = users or {}
        self._search_results = search_results or {}

    def get_organization(self, name):
        if name not in self._orgs:
            raise GithubException(404, {"message": "Not Found"}, None)
        return self._orgs[name]

    def get_repo(self, full_name_or_id):
        for org in self._orgs.values():
            for repo in org.get_repos():
                if full_name_or_id in (repo.full_name, repo.id):
                    return repo
        raise GithubException(404, {"message": "Not Found"}, None)

    def get_user(self, login=None):
        if login is None:
            return FakeAuthenticatedUser(list(self._orgs.values()))
        return self._users.get(login, FakeNamedUser(login))

    def search_users(self, query):
        return FakeSearchResult(self._search_results.get(query, []))


# --- canvas ---------------------------------------------------------------

class FakeCanvasUser:
    def __init__(self, name):
        self.name = name


class FakeCanvasGroup:
    def __init__(self, name, members):
        self.name = name
        self._members = [FakeCanvasUser(m) for m in members]

    def get_users(self):
        return list(self._members)


class FakeGroupCategory:
    def __init__(self, name, groups):
        self.name = name
        self._groups = groups

    def get_groups(self):
        return list(self._groups)


class FakeCourse:
    def __init__(self, id, name, categories=()):
        self.id = id
        self.name = name
        self._categories = list(categories)

    def get_group_categories(self):
        return list(self._categories)


class FakeProfile(dict):
    """canvasapi Profile behaves dict-like for the fields we read."""


class FakeCanvas:
    def __init__(self, courses=(), enrollments=(), profiles=None):
        self._courses = list(courses)
        self._enrollments = list(enrollments)
        self._profiles = profiles or {}

    def get_courses(self, enrollment_type=None):
        return list(self._courses) if enrollment_type == "teacher" else []

    def graphql(self, query, variables):
        return {
            "data": {
                "course": {
                    "enrollmentsConnection": {
                        "nodes": self._enrollments,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }

    def get_user(self, user_id):
        return _FakeCanvasProfileHolder(self._profiles.get(str(user_id), {}))


class _FakeCanvasProfileHolder:
    def __init__(self, profile):
        self._profile = profile

    def get_profile(self, include=None):
        return FakeProfile(self._profile)
