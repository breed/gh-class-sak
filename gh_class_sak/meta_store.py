"""the classroom-meta repo: versioned classroom state in a private org repo.

an org hosts a set of classrooms; each is a directory (named by the
normalized canvas course partial) whose classroom.ini marks it as one.
every *.tsv file in the directory is an assignment, named by its stem:

    sp26_cmpe_195a/classroom.ini   [CLASSROOM] prefix / settings, [TAS] one
                                   identity per line, [TEMPLATE] and
                                   [GROUP_SETS] one ASSIGNMENT = VALUE each
    sp26_cmpe_195a/hw1.tsv         NAME  STUDENTS  REPO  REPO_ID
    sp26_cmpe_195a/project.tsv

a row's default repo name joins the non-empty parts prefix, assignment,
NAME with "-"; the recorded REPO/REPO_ID always wins once set.

parsing and serialization are pure functions over text so they test without
git; the git plumbing at the bottom reuses git_ops.
"""

import os
from configparser import ConfigParser
from configparser import Error as ConfigParserError

import click

from gh_class_sak.core import warn
from gh_class_sak.github_api import get_org_repo

META_REPO_NAME = "classroom-meta"
STUDENTS_HEADERS = ("NAME", "STUDENTS", "REPO", "REPO_ID")
EMPTY = "-"
PROTECTION_VALUES = ("none", "pr-review")


# --- classroom.ini ---------------------------------------------------

def parse_classroom_ini(text):
    """{prefix, template, protection, linear_history, force_push}; unset keys are None.

    raises ValueError on a protection value outside PROTECTION_VALUES or a
    boolean that isn't true/false.
    """
    # interpolation off: a % in a value (a url-encoded template REPO_URL,
    # say) is data, or every later load of the file raises
    config = ConfigParser(allow_no_value=True, interpolation=None)
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
        "canvas_course": config.get("CLASSROOM", "canvas_course", fallback=None),
        "protection": protection,
        "linear_history": _bool("linear_history"),
        "force_push": _bool("force_push"),
        "tas": list(config.options("TAS")) if "TAS" in config else [],
        "templates": dict(config.items("TEMPLATE"))
        if "TEMPLATE" in config else {},
        "group_sets": dict(config.items("GROUP_SETS"))
        if "GROUP_SETS" in config else {},
    }


def serialize_classroom_ini(prefix=None, template=None, protection=None,
                            linear_history=None, force_push=None,
                            canvas_course=None, tas=None, templates=None,
                            group_sets=None):
    lines = ["[CLASSROOM]"]
    if prefix:
        lines.append(f"prefix = {prefix}")
    if template:
        lines.append(f"template = {template}")
    if canvas_course:
        lines.append(f"canvas_course = {canvas_course}")
    if protection is not None:
        lines.append(f"protection = {protection}")
    if linear_history is not None:
        lines.append(f"linear_history = {str(linear_history).lower()}")
    if force_push is not None:
        lines.append(f"force_push = {str(force_push).lower()}")
    if tas:
        lines.append("")
        lines.append("[TAS]")
        lines.extend(tas)
    if templates:
        lines.append("")
        lines.append("[TEMPLATE]")
        for assignment, repo_url in templates.items():
            lines.append(f"{assignment} = {repo_url}")
    if group_sets:
        lines.append("")
        lines.append("[GROUP_SETS]")
        for assignment, group_set in group_sets.items():
            lines.append(f"{assignment} = {group_set}")
    return "\n".join(lines) + "\n"


def effective_repo_settings(data):
    """(protection, linear_history, force_push) with defaults none/true/false."""
    protection = data["protection"] if data["protection"] is not None else "none"
    linear = data["linear_history"] if data["linear_history"] is not None else True
    force = data["force_push"] if data["force_push"] is not None else False
    return protection, linear, force


def parse_identity(entry):
    """(email, github) from the EMAIL/GITHUBID identity syntax.

    joe@example.com/JoeDev carries both halves, joe@example.com/ only the
    email, /JoeDev only the github id. entries without a slash are legacy:
    an @ means an email, anything else a github id.
    """
    if "/" in entry:
        email, _, github = entry.partition("/")
        return email or None, github or None
    if "@" in entry:
        return entry, None
    return None, entry


def format_identity(email, github):
    """the EMAIL/GITHUBID identity syntax; empty halves stay empty."""
    return f"{email or ''}/{github or ''}"


def join_repo_name(*parts):
    """join the non-empty repo-name parts with "-": the default-repo-name rule.

    an unset classroom prefix simply drops its segment, so a repo made for
    row team-1 of assignment hw1 is prefix-hw1-team-1, or hw1-team-1.
    """
    return "-".join(part for part in parts if part)


# --- tas ------------------------------------------------------------------

def parse_tas(text):
    """logins/emails, one per line; blank lines and # comments ignored."""
    entries = []
    for line in text.splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            entries.append(entry)
    return entries


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
    """the parse_classroom_ini dict plus tas and assignments, or None if absent.

    every *.tsv file in the directory is an assignment named by its stem;
    data["assignments"] maps name -> rows in sorted-filename order, so
    iteration is deterministic everywhere downstream.
    """
    path = classroom_dir(checkout, classroom)
    ini = os.path.join(path, "classroom.ini")
    if not os.path.exists(ini):
        return None
    with open(ini) as f:
        data = parse_classroom_ini(f.read())
    if not data["tas"]:
        # pre-[TAS] classrooms kept the tas in their own file; the next
        # save moves them into classroom.ini and removes the file
        tas_path = os.path.join(path, "tas")
        if os.path.exists(tas_path):
            with open(tas_path) as f:
                data["tas"] = parse_tas(f.read())
    data["assignments"] = {}
    for entry in sorted(os.listdir(path)):
        if entry.startswith(".") or not entry.endswith(".tsv"):
            continue
        with open(os.path.join(path, entry)) as f:
            data["assignments"][entry[:-len(".tsv")]] = parse_students_tsv(f.read())
    return data


def list_classrooms(checkout):
    """classroom dir names present in the meta checkout."""
    if not os.path.isdir(checkout):
        return []
    return sorted(
        entry for entry in os.listdir(checkout)
        if os.path.exists(os.path.join(checkout, entry, "classroom.ini"))
    )


def save_classroom(checkout, classroom, prefix=None, template=None, *, protection=None,
                   linear_history=None, force_push=None, canvas_course=None,
                   tas=None, templates=None, group_sets=None, assignments=None):
    """write the classroom files; classroom.ini carries everything but the
    assignment tsvs.

    assignments maps name -> rows; only the named <name>.tsv files are
    written, and none are ever deleted — removing an assignment is a hand
    `git rm` in the checkout. a legacy standalone `tas` file is removed:
    the tas live in classroom.ini's [TAS] section now.
    """
    path = classroom_dir(checkout, classroom)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "classroom.ini"), "w") as f:
        f.write(serialize_classroom_ini(prefix, template, protection=protection,
                                        linear_history=linear_history,
                                        force_push=force_push,
                                        canvas_course=canvas_course,
                                        tas=tas, templates=templates,
                                        group_sets=group_sets))
    legacy_tas = os.path.join(path, "tas")
    if os.path.exists(legacy_tas):
        os.remove(legacy_tas)
    for name, rows in (assignments or {}).items():
        with open(os.path.join(path, f"{name}.tsv"), "w") as f:
            f.write(serialize_students_tsv(rows))


# --- git plumbing ---------------------------------------------------------

def meta_checkout_dir(org):
    return os.path.join(click.get_app_dir("gh-class-sak"), META_REPO_NAME, org)


def checkout_meta(clone_url, org, token=None):
    """clone or fast-forward the org's classroom-meta repo; returns its path.

    raises RuntimeError with the status when the checkout can't be brought
    up to date ("diverged" means local hand edits — commit or discard them).
    """
    from gh_class_sak.git_ops import clone_or_update

    dest = meta_checkout_dir(org)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    status = clone_or_update(clone_url, dest, token)
    if status in ("failed", "not-a-repo", "diverged", "pull-failed"):
        raise RuntimeError(f"classroom-meta checkout at {dest}: {status}")
    return dest


def load_meta_classrooms(gh, org, token=None):
    """{classroom: data} from the classroom-meta repo; {} when none or unusable.

    a broken checkout degrades to a warning rather than an error, because
    read-only commands must keep working from prefixes alone.
    """
    repo = get_org_repo(gh, org, META_REPO_NAME)
    if repo is None:
        return {}
    try:
        checkout = checkout_meta(repo.clone_url, org, token)
    except RuntimeError as exc:
        warn(f"ignoring classroom-meta repo: {exc}")
        return {}
    classrooms = {}
    for classroom in list_classrooms(checkout):
        try:
            classrooms[classroom] = load_classroom(checkout, classroom)
        except (ValueError, ConfigParserError) as exc:
            warn(f"ignoring classroom {classroom} in the classroom-meta repo: {exc}")
    return classrooms


def commit_and_push(checkout, message, token=None):
    """commit every change in the checkout and push; no-op when clean."""
    from git import Actor, Repo

    from gh_class_sak.git_ops import auth_env

    # the context manager closes the repo's handles deterministically — an
    # open Repo pins files on windows and blocks temp-dir cleanup
    with Repo(checkout) as repo:
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
