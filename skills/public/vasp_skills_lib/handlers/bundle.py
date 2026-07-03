"""Handler bundle: combines custodian handlers + extended patterns + new handlers."""

from __future__ import annotations

from pathlib import Path

try:
    from custodian.vasp.handlers import (
        FrozenJobErrorHandler,
        NonConvergingErrorHandler,
        PositiveEnergyErrorHandler,
        UnconvergedErrorHandler,
        VaspErrorHandler,
    )

    _CUSTODIAN_AVAILABLE = True
except ImportError:
    _CUSTODIAN_AVAILABLE = False


class VaspErrorHandlerBundle:
    """Collects handlers that scan a work_dir for errors and mutate INCAR in-place."""

    def __init__(self, work_dir: Path, extended: bool = True, job_running: bool = False):
        self.work_dir = Path(work_dir).resolve()
        self._handlers: list = []
        if _CUSTODIAN_AVAILABLE:
            self._handlers = [
                VaspErrorHandler(output_filename=str(self.work_dir / "vasp.out")),
                UnconvergedErrorHandler(output_filename=str(self.work_dir / "vasprun.xml")),
                NonConvergingErrorHandler(),
                PositiveEnergyErrorHandler(),
            ]
            # FrozenJobErrorHandler only makes sense while the job is actively running
            if job_running:
                self._handlers.append(
                    FrozenJobErrorHandler(output_filename=str(self.work_dir / "vasp.out"))
                )
        if extended:
            try:
                from .vasp_errors import ExtendedVaspErrorHandler

                # When custodian is available it already covers zbrent/brmix/eddrmm/edddav;
                # pass skip_custodian_errors=True to avoid double-patching INCAR.
                self._handlers.append(
                    ExtendedVaspErrorHandler(
                        self.work_dir,
                        skip_custodian_errors=_CUSTODIAN_AVAILABLE,
                    )
                )
            except ImportError:
                pass
            # FrozenJobHandler uses mtime — only valid while job is running
            if job_running:
                try:
                    from .frozen_job import FrozenJobHandler

                    self._handlers.append(FrozenJobHandler(self.work_dir))
                except ImportError:
                    pass
            try:
                from .unconverged import UnconvergedHandler

                self._handlers.append(UnconvergedHandler(self.work_dir))
            except ImportError:
                pass

    def check_and_correct(self) -> tuple[bool, list[str]]:
        """Returns (anything_corrected, messages)."""
        corrected = False
        messages: list[str] = []
        for h in self._handlers:
            try:
                if hasattr(h, "check") and h.check():
                    out = h.correct() if hasattr(h, "correct") else {}
                    corrected = True
                    messages.append(f"{h.__class__.__name__}: {out}")
            except Exception as e:
                messages.append(f"{h.__class__.__name__} failed: {e}")
        return corrected, messages


def default_bundle(work_dir: Path, job_running: bool = False) -> VaspErrorHandlerBundle:
    return VaspErrorHandlerBundle(work_dir, extended=True, job_running=job_running)
