"""Error handlers.

Combines custodian defaults, extended VASP error patterns, and custom
frozen-job / unconverged detectors.
"""

from .bundle import VaspErrorHandlerBundle, default_bundle  # noqa: F401
