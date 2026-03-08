from gh_class_sak.core import GITHUB_API, paginate


def list_classrooms(session):
    url = f"{GITHUB_API}/classrooms"
    return paginate(session, url)


def list_assignments(session, classroom_id):
    url = f"{GITHUB_API}/classrooms/{classroom_id}/assignments"
    return paginate(session, url)


def list_accepted_assignments(session, assignment_id):
    url = f"{GITHUB_API}/assignments/{assignment_id}/accepted_assignments"
    return paginate(session, url)


def list_collaborators(session, owner, repo):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/collaborators"
    return paginate(session, url)


def add_collaborator(session, owner, repo, username, permission="push"):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}"
    resp = session.put(url, json={"permission": permission})
    resp.raise_for_status()
    return resp


def remove_collaborator(session, owner, repo, username):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}"
    resp = session.delete(url)
    resp.raise_for_status()
    return resp


def get_user(session, username):
    url = f"{GITHUB_API}/users/{username}"
    resp = session.get(url)
    resp.raise_for_status()
    return resp.json()


def resolve_email_to_username(session, email):
    url = f"{GITHUB_API}/search/users"
    resp = session.get(url, params={"q": f"{email} in:email"})
    resp.raise_for_status()
    data = resp.json()
    if data.get("total_count", 0) == 1:
        return data["items"][0]["login"]
    return None
