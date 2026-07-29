# Contributing to gh-class-sak

Thanks for considering it. Bug reports, documentation fixes, and questions are all real
contributions — you do not need to write code to be useful here.

This tool is built by and for instructors, so the most valuable thing you can tell us is
**how your course is actually set up**. Org naming, repo naming, whether you use Canvas
groups or sections — these vary enormously between courses, and we only see our own.
There's a [Share your course setup][experience] issue template for exactly that.

## Local setup

```bash
git clone https://github.com/breed/gh-class-sak.git
cd gh-class-sak
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python 3.9 or newer and git. Nothing else — no GitHub token, no Canvas account.

## The two commands you need

```bash
.venv/bin/pytest                             # run the tests
.venv/bin/ruff check gh_class_sak tests      # lint — CI enforces this
```

**You do not need a GitHub org or a Canvas instance to contribute.** GitHub and Canvas are
both stubbed in `tests/fakes.py`, so the suite runs completely offline in well under a
second. That's deliberate: needing a live course to change one line would make this
project impossible to contribute to.

The flip side: **please don't add a test that reaches the network.** If you need new API
behaviour, extend the fakes. A missing attribute on a fake is a signal that production
code started depending on something new, which is usually worth a second look anyway.

To try it against a real org, see the [README](README.md#authentication) for token and
config setup.

## Finding something to work on

- **[Good first issues][gfi]** — scoped, with enough context to start.
- **[Documentation issues][docs]** — the fastest way to learn this codebase is to write
  the explanation you wish you'd had.

Planning something large? **Open an issue or [discussion][discussions] first.** Not
bureaucracy — we'd rather talk through the approach than have you spend a weekend on a
direction we can't merge.

## Pull requests

- **Say why.** The diff shows what changed; only you can explain why it should. This is
  the field reviewers care about most.
- **One concern per PR.** A focused change gets reviewed in a day; a sweeping one sits for
  weeks because nobody has a free hour.
- **Include a test.** For a bug fix, a test that fails before your change and passes after
  is the clearest possible argument that you fixed it.
- **Treat output format as a compatibility surface.** People pipe these tables into
  scripts. Changing a column, a separator, or a flag name is a breaking change — call it
  out and note the migration.
- **Update the docs** if you changed behaviour.
- **Don't worry about a perfect first submission.** We'll review, suggest, and help. A PR
  that needs work is far more welcome than one that never gets opened.

## A note on student data

This tool handles rosters, real names, and email addresses. Two rules:

1. **Never paste real student data into an issue, PR, or test fixture.** The fixtures in
   `tests/` use invented people; keep it that way.
2. **Never log or print a token.** `gh_class_sak/git_ops.py` passes the GitHub token to
   git through the environment specifically so it can't leak into `ps` output, a clone
   URL, or a checked-out `.git/config`. If you touch that code path, keep that property
   and add a test asserting it.

## AI-assisted contributions

**LLM-assisted contributions are welcome**, subject to the rules below. These exist
because AI-generated PRs have a characteristic failure mode — enormous, confident, and
unreviewable — not because we object to the tools.

1. **Disclose it.** Tick the box in the PR template. This is not a black mark; it just
   tells reviewers where to look. It's far better than us trying to deduce it from a diff
   that doesn't match your description.

2. **No blind refactors.** If an AI suggested a redesign, **you must be able to explain
   the rationale** and defend it in review. "The model suggested it" is not a rationale.
   If you can't explain it, don't submit it.

3. **Keep the diff proportional.** LLMs tend to rewrite whole files from scratch in a
   different style, turning a three-line fix into a 400-line diff nobody can review.
   **Disproportionately large diffs for small changes will be closed** with a request to
   resubmit scoped. Match the surrounding code's style and conventions.

4. **Verify it yourself.** Run the tests. Read the output. Check that the code does what
   you think. You are the author and you are accountable for it.

5. **Respect the primary author.** Don't replace an existing design because a model
   proposed a different one. The current design usually reflects constraints that aren't
   visible in the file — **ask about the rationale first**, in an issue.

## How we'll treat you

- We'll say thank you. Even if the report turns out to be wrong or the PR isn't mergeable
  — you spent your time on this and that counts.
- We'll explain our decisions rather than just declaring them. If we say no, you'll get a
  reason.
- We'll credit you: in [CONTRIBUTORS.md](CONTRIBUTORS.md), in the release notes for the
  version containing your work, and with `Co-authored-by:` if we build on it.
- If you contribute something substantial and it would help you, **ask us for a reference
  or a public recommendation.** We're glad to write one.

## Code of conduct

Be kind. We use "we" rather than "you" when something goes wrong, and we assume good
faith. Report problems privately to the maintainer via [@breed](https://github.com/breed).

[gfi]: https://github.com/breed/gh-class-sak/labels/good%20first%20issue
[docs]: https://github.com/breed/gh-class-sak/labels/documentation
[discussions]: https://github.com/breed/gh-class-sak/discussions
[experience]: https://github.com/breed/gh-class-sak/issues/new?template=production_experience.yml
