# What

<!-- What does this change? One or two sentences. -->

# Why

<!-- REQUIRED. What problem does this solve, and why this approach?

     This is the field maintainers care about most. A diff shows what changed;
     only you can explain why it should change. If this closes an issue, link it —
     but still say why, because the issue may describe a symptom rather than a cause. -->

Closes #

# How to verify

<!-- How should a reviewer convince themselves this works?
     The commands to run, and what the output should look like. If this touches the
     GitHub or Canvas code paths, say whether you tried it against a real org. -->

```
pytest -q
```

# Checklist

- [ ] Tests added or updated (a bug fix should come with a test that fails without it)
- [ ] `ruff check gh_class_sak tests` passes
- [ ] Documentation updated, if this changes behaviour or a command's output
- [ ] No network access added to the test suite — GitHub and Canvas are stubbed in `tests/fakes.py`
- [ ] Breaking changes called out below, with a migration note

## Breaking changes

<!-- None, or: what breaks and exactly how a user migrates.
     Table output and flag names count — people pipe these tables into scripts. -->

None.

---

## AI assistance

<!-- We welcome AI-assisted contributions — please just tell us, so review can focus
     in the right place. See CONTRIBUTING.md for the full policy. -->

- [ ] This PR was written or substantially assisted by an LLM

If checked, please confirm:

- [ ] I can explain the rationale behind every change here, and I'm not proposing a
      redesign I don't understand
- [ ] The diff is scoped to the change — no whole-file rewrites, reformatting, or
      unrelated refactoring bundled in
- [ ] I ran the tests and reviewed the output myself
