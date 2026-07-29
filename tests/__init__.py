# makes tests a package so `from tests.fakes import ...` resolves under a bare
# `pytest` invocation, not only `python -m pytest` (which adds the cwd to sys.path)
