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


class FakeRepo:
    def __init__(self, org, name, collaborators=(), commits=(), commits_raise=False):
        self.name = name
        self.full_name = f"{org}/{name}"
        self.clone_url = f"https://github.com/{org}/{name}.git"
        self._collaborators = list(collaborators)
        self._commits = list(commits)
        self._commits_raise = commits_raise

    def get_collaborators(self):
        return list(self._collaborators)

    def get_commits(self):
        if self._commits_raise:
            raise GithubException(409, {"message": "Git Repository is empty."}, None)
        return list(self._commits)


class FakeOrg:
    def __init__(self, login, repos=()):
        self.login = login
        self._repos = list(repos)

    def get_repos(self):
        return list(self._repos)


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
