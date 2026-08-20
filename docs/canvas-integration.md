# Canvas integration

Canvas knows who your students are; GitHub knows what they push. This page explains how
the two are connected: how GitHub ids are mapped to Canvas accounts, and how assignments
can be built straight from Canvas enrollments or group sets.

Everything here needs a `[CANVAS]` section in the config (see
[Getting started](getting-started.md#naming-your-classroom-the-org-and-the-config-file)):

```ini
[CANVAS]
url = https://your-canvas-instance.instructure.com
token = YOUR_CANVAS_API_TOKEN
```

## Which Canvas course is meant

A classroom maps to a Canvas course by name. The lookup partial is, in order: the
`canvas_course` recorded in `classroom.ini` (set it with `meta init --canvas-course`),
or the classroom directory name. Matching is normalized on both sides — case,
hyphens, underscores, and spaces are all equivalent — so the directory `cs_101`
matches the Canvas course "FA26: CS-101 Sec 01".

## Mapping GitHub ids to Canvas accounts

The link lives in the **Canvas profile**: a student adds their GitHub URL to the
*links* section of their Canvas profile (a `github.com/...` URL in the bio works too).
That's the one thing to ask students to do at the start of the term — and
`canvas message-missing` chases the stragglers for you, messaging everyone whose link
is missing or broken, or who never accepted their repo invitation.

Resolution runs in a chain, stopping at the first hit:

1. **The identity itself.** A `/githubid` half in an `EMAIL/GITHUBID` identity needs no
   lookup at all.
2. **The Canvas profile.** The enrollment's profile is fetched (through the course —
   teachers may not read profiles account-wide) and searched for a GitHub link.
That's the whole chain — deliberately. GitHub's search API is never consulted: it only
indexes the email a user *publicly* lists on their profile (which almost no student
does), its loose token matching can return strangers, and an id that ends up granting
repo access must not come from a guess. Display names are never used to resolve an id
either: two people can share one.

Anything still unresolved is a loud, red error naming the person, and the command exits
nonzero — silent gaps would surface weeks later as a student who never had access.
Profiles are cached for the run, so a roster consulted several times fetches each
profile once.

The reverse direction — which Canvas student owns a GitHub login — is done by **name**:
GitHub profile names are fuzzy-matched against Canvas names ("Adams, Alice" matches
"Alice Adams"). That powers `repos list --group`, `repos missing`, and the instructor
columns; a student whose GitHub profile has no real name can't be matched, which is
the other thing worth asking of students.

## Assignments from enrollments

```
gh-class-sak meta assign CLASSROOM --from-canvas --assignment hw1
```

builds one row per **enrolled person** — students, instructors, and TAs alike. The row
`NAME` is the person's name made GitHub-safe (`José Núñez` → `Jose-Nunez`), and the
`STUDENTS` entry is their full `EMAIL/GITHUBID` identity, both halves as far as Canvas
knows them. From there the normal machinery applies: merge, never-clobber, repos
created under dryrun control, and any `[TEMPLATE]` starter content.

## Assignments from group sets

```
gh-class-sak meta assign CLASSROOM --from-canvas --assignment project --canvas-group "Project Groups"
```

builds one row per **group** in that Canvas group set instead: the row `NAME` is the
GitHub-safe group name, and its `STUDENTS` are the group's members, mapped from the
group roster to enrollments by normalized name and then to identities. The group set's
name is recorded in `classroom.ini` under `[GROUP_SETS]` as `project = Project Groups`,
so the classroom remembers where each assignment's teams came from.

Group sets also drive the read-side commands: `repos list --group SET` annotates each
repo with the Canvas group it matches, and `repos missing --group SET` lists the groups
that have no repo yet.

## What the roster features unlock

With `[CANVAS]` configured: `--group`, `--instructors` (matched to students via shared
course sections), `--email` (preferring the address students actually commit with),
`repos missing`, TA seeding in `meta init`, and email resolution in `meta assign`.
`gh-class-sak help-me-setup` verifies the credentials and lists the courses your token
can see.
