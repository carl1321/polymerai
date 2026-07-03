"""gaussian_skills_lib — shared helpers for the gaussian-skills ecosystem.

Built on upstream mainstream libraries (cclib, paramiko, basis_set_exchange, ASE).
Does not import the legacy `gaussian_agent` package.
"""

from .runner import run_with_retries

__version__ = "0.1.0"
__all__ = ["run_with_retries"]
