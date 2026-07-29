"""the meta repo: versioned classroom state kept in a private repo in the org.

an org can host several classrooms; each is a directory (named by the
normalized canvas course partial):

    sp26_cmpe_195a/classroom.ini   [CLASSROOM] prefix = ... / template = ...
    sp26_cmpe_195a/tas             one github login or email per line
    sp26_cmpe_195a/students.tsv    NAME  STUDENTS  REPO  REPO_ID

parsing and serialization are pure functions over text so they test without
git; the git plumbing at the bottom reuses git_ops.
"""

import os
from configparser import ConfigParser

import click

from gh_class_sak.core import warn
from gh_class_sak.github_api import get_org_repo

META_REPO_NAME = "meta"
STUDENTS_HEADERS = ("NAME", "STUDENTS", "REPO", "REPO_ID")
EMPTY = "-"
PROTECTION_VALUES = ("none", "pr-review")


# --- classroom.ini ---------------------------------------------------

def parse_classroom_ini(text):
    """{prefix, template, protection, linear_history, force_push}; unset keys are None.

    raises ValueError on a protection value outside PROTECTION_VALUES or a
    boolean that isn't true/false.
    """
    config = ConfigParser()
    config.optionxform = str
    config.read_string(text)

    def _bool(key):
        try:
            return config.getboolean("CLASSROOM", key, fallback=None)
        except ValueError:
            raise ValueError(f'{key} must be true or false,'
                             f' got "{config.get("CLASSROOM", key)}"') from None

    protection = config.get("CLASSROOM", "protection", fallback=None)
    if protection is not None and protection not in PROTECTION_VALUES:
        raise ValueError(f'protection must be one of {", ".join(PROTECTION_VALUES)},'
                         f' got "{protection}"')
    return {
        "prefix": config.get("CLASSROOM", "prefix", fallback=None),
        "template": config.get("CLASSROOM", "template", fallback=None),
        "protection": protection,
        "linear_history": _bool("linear_history"),
        "force_push": _bool("force_push"),
    }


def serialize_classroom_ini(prefix, template=None, protection=None,
                            linear_history=None, force_push=None):
    lines = ["[CLASSROOM]", f"prefix = {prefix}"]
    if template:
        lines.append(f"template = {template}")
    if protection is not None:
        lines.append(f"protection = {protection}")
    if linear_history is not None:
        lines.append(f"linear_history = {str(linear_history).lower()}")
    if force_push is not None:
        lines.append(f"force_push = {str(force_push).lower()}")
    return "\n".join(lines) + "\n"


def effective_repo_settings(data):
    """(protection, linear_history, force_push) with defaults none/true/false."""
    protection = data["protection"] if data["protection"] is not None else "none"
    linear = data["linear_history"] if data["linear_history"] is not None else True
    force = data["force_push"] if data["force_push"] is not None else False
    return protection, linear, force


# --- tas ------------------------------------------------------------------

def parse_tas(text):
    """logins/emails, one per line; blank lines and # comments ignored."""
    entries = []
    for line in text.splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            entries.append(entry)
    return entries


def serialize_tas(entries):
    return "".join(f"{entry}\n" for entry in entries)


# --- students.tsv ---------------------------------------------------------

def parse_students_tsv(text):
    """rows of {name, students, repo, repo_id}; header, blanks, # ignored.

    no column may contain whitespace (students are comma-joined), so any
    whitespace run separates columns and hand-edited files parse fine.
    """
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split()
        if [c.upper() for c in cols[:2]] == ["NAME", "STUDENTS"]:
            continue
        cols += [EMPTY] * (len(STUDENTS_HEADERS) - len(cols))
        name, students, repo, repo_id = cols[:len(STUDENTS_HEADERS)]
        rows.append({
            "name": name,
            "students": [s for s in students.split(",") if s and s != EMPTY],
            "repo": None if repo == EMPTY else repo,
            "repo_id": None if repo_id == EMPTY else int(repo_id),
        })
    return rows


def serialize_students_tsv(rows):
    """space-padded columns like the CLI's tables; last column unpadded."""
    table = [STUDENTS_HEADERS] + [
        (row["name"],
         ",".join(row["students"]) or EMPTY,
         row["repo"] or EMPTY,
         EMPTY if row["repo_id"] is None else str(row["repo_id"]))
        for row in rows
    ]
    widths = [max(len(r[i]) for r in table) for i in range(len(STUDENTS_HEADERS))]
    lines = []
    for r in table:
        cells = [c.ljust(widths[i]) for i, c in enumerate(r[:-1])] + [r[-1]]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines) + "\n"


def merge_rows(existing, incoming):
    """merge an instructor-supplied table into the recorded one.

    new NAMEs are appended; an existing NAME gets its student list replaced.
    REPO and REPO_ID are never clobbered — once a repo is recorded it stays.
    returns (merged, changed_names).
    """
    by_name = {row["name"]: dict(row) for row in existing}
    order = [row["name"] for row in existing]
    changed = []
    for row in incoming:
        name = row["name"]
        if name in by_name:
            if by_name[name]["students"] != row["students"]:
                by_name[name]["students"] = list(row["students"])
                changed.append(name)
        else:
            by_name[name] = {"name": name, "students": list(row["students"]),
                             "repo": None, "repo_id": None}
            order.append(name)
            changed.append(name)
    return [by_name[name] for name in order], changed


# --- classroom state on disk ------------------------------------------

def classroom_dir(checkout, classroom):
    return os.path.join(checkout, classroom)


def load_classroom(checkout, classroom):
    """the parse_classroom_ini dict plus tas and rows, or None if absent."""
    path = classroom_dir(checkout, classroom)
    ini = os.path.join(path, "classroom.ini")
    if not os.path.exists(ini):
        return None
    with open(ini) as f:
        data = parse_classroom_ini(f.read())
    data["tas"] = []
    tas_path = os.path.join(path, "tas")
    if os.path.exists(tas_path):
        with open(tas_path) as f:
            data["tas"] = parse_tas(f.read())
    data["rows"] = []
    tsv_path = os.path.join(path, "students.tsv")
    if os.path.exists(tsv_path):
        with open(tsv_path) as f:
            data["rows"] = parse_students_tsv(f.read())
    return data


def list_classrooms(checkout):
    """classroom dir names present in the meta checkout."""
    if not os.path.isdir(checkout):
        return []
    return sorted(
        entry for entry in os.listdir(checkout)
        if os.path.exists(os.path.join(checkout, entry, "classroom.ini"))
    )


def save_classroom(checkout, classroom, prefix, template=None, *, protection=None,
                   linear_history=None, force_push=None, tas=None, rows=None):
    """write the classroom files; only the pieces passed are (re)written."""
    path = classroom_dir(checkout, classroom)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "classroom.ini"), "w") as f:
        f.write(serialize_classroom_ini(prefix, template, protection=protection,
                                        linear_history=linear_history,
                                        force_push=force_push))
    if tas is not None:
        with open(os.path.join(path, "tas"), "w") as f:
            f.write(serialize_tas(tas))
    if rows is not None:
        with open(os.path.join(path, "students.tsv"), "w") as f:
            f.write(serialize_students_tsv(rows))


# --- git plumbing ---------------------------------------------------------

def meta_checkout_dir(org):
    return os.path.join(click.get_app_dir("gh-class-sak"), "meta", org)


def checkout_meta(clone_url, org, token=None):
    """clone or fast-forward the org's meta repo; returns the checkout path.

    raises RuntimeError with the status when the checkout can't be brought
    up to date ("diverged" means local hand edits — commit or discard them).
    """
    from gh_class_sak.git_ops import clone_or_update

    dest = meta_checkout_dir(org)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    status = clone_or_update(clone_url, dest, token)
    if status in ("failed", "not-a-repo", "diverged", "pull-failed"):
        raise RuntimeError(f"meta checkout at {dest}: {status}")
    return dest


def load_meta_classrooms(gh, org, token=None):
    """{classroom: data} from the org's meta repo; {} when none or unusable.

    a broken checkout degrades to a warning rather than an error, because
    read-only commands must keep working from prefixes alone.
    """
    repo = get_org_repo(gh, org, META_REPO_NAME)
    if repo is None:
        return {}
    try:
        checkout = checkout_meta(repo.clone_url, org, token)
    except RuntimeError as exc:
        warn(f"ignoring meta repo: {exc}")
        return {}
    classrooms = {}
    for classroom in list_classrooms(checkout):
        try:
            classrooms[classroom] = load_classroom(checkout, classroom)
        except ValueError as exc:
            warn(f"ignoring classroom {classroom} in the meta repo: {exc}")
    return classrooms


def commit_and_push(checkout, message, token=None):
    """commit every change in the checkout and push; no-op when clean."""
    from git import Actor, Repo

    from gh_class_sak.git_ops import auth_env

    repo = Repo(checkout)
    repo.git.add("-A")
    if repo.head.is_valid():
        if not repo.index.diff("HEAD"):
            return False
    elif not repo.index.entries:
        return False
    actor = Actor("gh-class-sak", "gh-class-sak@localhost")
    repo.index.commit(message, author=actor, committer=actor)
    with repo.git.custom_environment(**auth_env(token)):
        # -u so a clone of an initially-empty origin gains a tracking branch
        repo.git.push("--set-upstream", "origin", "HEAD")
    return True
