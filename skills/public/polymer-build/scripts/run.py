#!/usr/bin/env python3
"""Workflow worker entry (run_skill requires scripts/run.py). Delegates to run_pipeline.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Same directory as run_pipeline.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
