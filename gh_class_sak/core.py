import os
import subprocess
import sys
from configparser import ConfigParser

import click
import requests
from importlib.metadata import version


config_ini = click.get_app_dir("gh-class-sak.ini")


def get_token():
    token = os.environ.get("GH_TOKEN")
    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
        token = result.stdout.strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    error("no github token found. either:")
    error("  - set GH_TOKEN environment variable")
    error("  - install gh CLI and run: gh auth login")
    sys.exit(1)


def get_session():
    token = get_token()
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return session


GITHUB_API = "https://api.github.com"


def paginate(session, url, params=None):
    if params is None:
        params = {}
    params.setdefault("per_page", 100)
    results = []
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        results.extend(resp.json())
        # only use params on the first request; Link URLs include them
        params = {}
        url = resp.links.get("next", {}).get("url")
    return results


def error(message):
    click.echo(click.style(message, fg='red'), err=True)


def info(message):
    click.echo(click.style(message, fg='blue'), err=True)


def warn(message):
    click.echo(click.style(message, fg='yellow'), err=True)


def output(message):
    click.echo(message)


def resolve_name(items, name, label):
    """find one item by partial name match, error on 0 or ambiguous matches."""
    matches = [i for i in items if name.lower() in i["name"].lower()]
    if len(matches) == 0:
        error(f'no {label} found matching "{name}". options are:')
        for i in items:
            error(f"    {i['name']}")
        sys.exit(2)
    if len(matches) > 1:
        # check for exact match
        exact = [i for i in matches if i["name"].lower() == name.lower()]
        if len(exact) == 1:
            return exact[0]
        error(f'multiple {label}s found matching "{name}":')
        for i in matches:
            error(f"    {i['name']}")
        sys.exit(2)
    return matches[0]


def normalize_course_name(name):
    return name.replace(":", "").replace(" ", "_").replace("-", "_").lower()


def get_config():
    config = ConfigParser()
    config.optionxform = str  # preserve key case
    if not os.path.exists(config_ini):
        error(f"config file not found: {config_ini}")
        error("create it with [CANVAS] and [COURSES] sections")
        sys.exit(1)
    config.read(config_ini)
    if "CANVAS" not in config:
        error(f"missing [CANVAS] section in {config_ini}")
        sys.exit(1)
    if "COURSES" not in config:
        error(f"missing [COURSES] section in {config_ini}")
        sys.exit(1)
    return config


def get_canvas_session():
    config = get_config()
    url = config.get("CANVAS", "url", fallback=None)
    token = config.get("CANVAS", "token", fallback=None)
    if not url or not token:
        error("missing url or token in [CANVAS] section")
        sys.exit(1)
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
    })
    return session, url


def resolve_course_mapping(config, classroom_name):
    matches = []
    norm_classroom = normalize_course_name(classroom_name)
    for canvas_partial, github_partial in config.items("COURSES"):
        norm_github = normalize_course_name(github_partial)
        if norm_github in norm_classroom or norm_classroom in norm_github:
            matches.append((canvas_partial, github_partial))
    if len(matches) == 0:
        error(f'no course mapping found for classroom "{classroom_name}" in {config_ini}')
        error("configured mappings:")
        for k, v in config.items("COURSES"):
            error(f"    {k} = {v}")
        sys.exit(2)
    if len(matches) > 1:
        error(f'ambiguous course mapping for classroom "{classroom_name}":')
        for k, v in matches:
            error(f"    {k} = {v}")
        sys.exit(2)
    return matches[0][0]


@click.group()
@click.version_option(version=version("gh-class-sak"), prog_name="gh-class-sak")
def gh_class_sak():
    pass
