"""Allow ``python -m deerflow.vasp_skills_lib``. Delegates to :mod:`deerflow.vasp_skills_lib.cli`."""

from deerflow.vasp_skills_lib.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
