"""Extended VASP error patterns — rewritten from scratch (not imported from vasp-agent).

Parity target: `D:/code/vasp-agent/vasp_agent/handlers/vasp_error.py` (805 lines).
This file reproduces the full 30+ pattern table with ranked correction strategies,
severity levels, and per-error correction history (so the handler won't retry a
strategy that already failed).

Integration: `handlers/bundle.py` instantiates `ExtendedVaspErrorHandler(work_dir)`
after custodian's defaults. `check()` scans vasp.out/OUTCAR/stderr; `correct()`
patches INCAR in place and returns a summary dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}


@dataclass(frozen=True)
class Correction:
    incar_updates: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    actions: tuple[str, ...] = ()
    description: str = ""
    confidence: float = 0.5

    def __hash__(self) -> int:  # make usable as history key
        return hash((tuple(sorted(self.incar_updates.items())), self.actions, self.description))


@dataclass
class DetectedError:
    name: str
    message: str
    severity: Severity
    line_number: int
    source: str


# -----------------------------------------------------------------------------
# Pattern table — (name, regex, severity, [Correction ranked by confidence])
# -----------------------------------------------------------------------------

PATTERNS: list[tuple[str, re.Pattern, Severity, list[Correction]]] = [
    # ---- Electronic structure -------------------------------------------------
    (
        "eddrmm",
        re.compile(r"WARNING.*Sub-Space-Matrix is not hermitian in DAV", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"ALGO": "Normal"}, description="ALGO Fast→Normal", confidence=0.85),
            Correction({"ALGO": "All"}, description="ALGO=All (Davidson+RMM-DIIS)", confidence=0.80),
            Correction({"ALGO": "Damped", "TIME": 0.5}, description="damped + small TIME", confidence=0.70),
            Correction({"POTIM": 0.1}, description="reduce POTIM", confidence=0.60),
        ],
    ),
    (
        "edddav",
        re.compile(r"Error EDDDAV: Call to ZHEGV failed", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ALGO": "All"}, description="switch to ALGO=All", confidence=0.85),
            Correction({"ALGO": "Exact"}, description="exact diagonalisation", confidence=0.75),
        ],
    ),
    (
        "zbrent",
        re.compile(r"ZBRENT: fatal", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"IBRION": 1, "POTIM": 0.1}, description="quasi-Newton small POTIM", confidence=0.90),
            Correction({"IBRION": 2, "POTIM": 0.05}, description="CG very small POTIM", confidence=0.80),
            Correction({"IBRION": 3, "POTIM": 0.02}, description="damped MD minimal POTIM", confidence=0.70),
        ],
    ),
    (
        "brmix",
        re.compile(r"BRMIX: very serious problems", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"AMIX": 0.1, "BMIX": 0.01, "AMIX_MAG": 0.2, "BMIX_MAG": 0.01},
                       description="reduce mixing parameters", confidence=0.80),
            Correction({"ISYM": 0}, description="disable symmetry", confidence=0.75),
            Correction({"IMIX": 1, "AMIX": 0.1, "BMIX": 0.0001},
                       description="Kerker mixing", confidence=0.70),
            Correction({"KGAMMA": True}, actions=("gamma_centered_kpoints",),
                       description="Γ-centered mesh", confidence=0.65),
        ],
    ),
    (
        "zpotrf",
        re.compile(r"LAPACK: Routine ZPOTRF failed", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ISYM": 0, "POTIM": 0.1}, description="ISYM off + small POTIM", confidence=0.80),
            Correction({"ALGO": "All"}, actions=("reduce_kpoints",),
                       description="ALGO=All + coarser k-mesh", confidence=0.75),
            Correction({"ISPIN": 1}, description="turn off spin if not required", confidence=0.50),
        ],
    ),
    (
        "pssyevx",
        re.compile(r"ERROR in subspace rotation PSSYEVX", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ALGO": "Normal"}, description="ALGO Fast→Normal", confidence=0.85),
            Correction({"ALGO": "All"}, description="ALGO=All", confidence=0.80),
        ],
    ),
    (
        "zheev",
        re.compile(r"Error EDDIAG: Call to routine ZHEEV failed", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ALGO": "Exact"}, description="exact diagonalisation", confidence=0.80),
            Correction({"ALGO": "All"}, description="ALGO=All", confidence=0.75),
        ],
    ),
    (
        "algo_ialgo",
        re.compile(r"ALGO\s*=\s*.*conflicting with\s*IALGO|IALGO.*incompatible", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"ALGO": "Normal"}, actions=("strip_ialgo",),
                    description="drop IALGO, use ALGO=Normal", confidence=0.90)],
    ),

    # ---- Ionic / relaxation ---------------------------------------------------
    (
        "brions",
        re.compile(r"BRIONS problems: POTIM should be increased", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"POTIM": 0.4}, description="POTIM up", confidence=0.85),
            Correction({"POTIM": 0.8}, description="POTIM further up", confidence=0.70),
        ],
    ),
    (
        "pricel",
        re.compile(r"internal error in subroutine PRICEL", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ISYM": 0}, description="disable symmetry", confidence=0.90),
            Correction({"SYMPREC": 1e-8}, description="tighten SYMPREC", confidence=0.80),
        ],
    ),
    (
        "edwav",
        re.compile(r"EDWAV: internal error", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"ALGO": "Normal"}, description="ALGO→Normal", confidence=0.80)],
    ),
    (
        "grad_not_orth",
        re.compile(r"EDWAV: internal error, the gradient is not orthogonal", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"ALGO": "Normal"}, description="ALGO→Normal", confidence=0.80),
            Correction({"ALGO": "VeryFast"}, description="try VeryFast", confidence=0.70),
        ],
    ),

    # ---- Symmetry -------------------------------------------------------------
    (
        "inv_rot_mat",
        re.compile(r"inverse of rotation matrix was not found", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"ISYM": 0}, description="disable symmetry", confidence=0.90),
            Correction({"SYMPREC": 1e-6}, description="relax SYMPREC", confidence=0.75),
        ],
    ),
    (
        "rot_matrix",
        re.compile(r"Found some non-integer element in rotation matrix", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"ISYM": 0}, description="disable symmetry", confidence=0.90)],
    ),
    (
        "point_group",
        re.compile(r"group operation missing|not a valid point group", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"ISYM": 0}, description="disable symmetry", confidence=0.90)],
    ),
    (
        "symprec",
        re.compile(r"SYMPREC|VERY BAD NEWS", re.M),
        Severity.MEDIUM,
        [
            Correction({"SYMPREC": 1e-6}, description="relax SYMPREC", confidence=0.80),
            Correction({"ISYM": 0}, description="disable symmetry", confidence=0.75),
        ],
    ),
    (
        "rhosyg",
        re.compile(r"RHOSYG internal error", re.I | re.M),
        Severity.HIGH,
        [
            Correction({"ISYM": 0}, description="disable symmetry", confidence=0.90),
            Correction({"SYMPREC": 1e-4}, description="loosen SYMPREC", confidence=0.75),
        ],
    ),
    (
        "posmap",
        re.compile(r"POSMAP internal error", re.I | re.M),
        Severity.HIGH,
        [Correction({"SYMPREC": 1e-6}, description="adjust SYMPREC", confidence=0.80)],
    ),

    # ---- K-points / smearing --------------------------------------------------
    (
        "tet",
        re.compile(r"Tetrahedron method fails|ISMEAR=-5 not allowed", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"ISMEAR": 0, "SIGMA": 0.05}, description="Gaussian smearing", confidence=0.95),
            Correction({"ISMEAR": 1, "SIGMA": 0.1}, description="Methfessel-Paxton", confidence=0.85),
        ],
    ),
    (
        "tetirr",
        re.compile(r"Routine TETIRR needs special values", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"ISMEAR": 0, "SIGMA": 0.05}, description="Gaussian smearing", confidence=0.95)],
    ),
    (
        "incorrect_shift",
        re.compile(r"internal error: incorrect shift", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"KGAMMA": True}, actions=("gamma_centered_kpoints",),
                    description="Γ-centered mesh", confidence=0.85)],
    ),
    (
        "dentet",
        re.compile(r"DENTET", re.M),
        Severity.MEDIUM,
        [Correction({"ISMEAR": 0, "SIGMA": 0.05}, description="Gaussian smearing", confidence=0.85)],
    ),

    # ---- Memory / resource ----------------------------------------------------
    (
        "memory",
        re.compile(r"out of memory|cannot allocate|malloc failed|OOM|bad_alloc", re.I | re.M),
        Severity.CRITICAL,
        [
            Correction({}, actions=("reduce_kpoints", "request_more_memory"),
                       description="coarser k-mesh + ask scheduler for more RAM", confidence=0.85),
            Correction({"NCORE": 4, "LREAL": "Auto"}, description="less parallel + real-space proj", confidence=0.80),
            Correction({"KPAR": 1, "NCORE": 1}, description="disable parallel levels", confidence=0.75),
            Correction({"LWAVE": False, "LCHARG": False}, description="skip WAVECAR/CHGCAR write", confidence=0.70),
        ],
    ),
    (
        "rspher",
        re.compile(r"RSPHER:", re.M),
        Severity.HIGH,
        [Correction({}, actions=("increase_encutgw",),
                    description="ENCUTGW up (GW calc)", confidence=0.70)],
    ),
    (
        "real_optlay",
        re.compile(r"REAL_OPTLAY: internal error", re.I | re.M),
        Severity.HIGH,
        [Correction({"LREAL": False}, description="disable real-space projection", confidence=0.90)],
    ),
    (
        "sgrcon",
        re.compile(r"SGRCON: ERROR", re.I | re.M),
        Severity.HIGH,
        [Correction({"ISYM": 0}, description="disable symmetry", confidence=0.85)],
    ),

    # ---- Numerical ------------------------------------------------------------
    (
        "too_few_bands",
        re.compile(r"TOO FEW BANDS", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({}, actions=("increase_nbands_50",), description="NBANDS +50%", confidence=0.95),
            Correction({}, actions=("increase_nbands_100",), description="NBANDS ×2", confidence=0.90),
        ],
    ),
    (
        "triple_product",
        re.compile(r"ERROR: the triple product", re.I | re.M),
        Severity.HIGH,
        [Correction({"ISYM": 0}, description="disable symmetry", confidence=0.75)],
    ),
    (
        "nicht_konv",
        re.compile(r"ERROR: SBESSELITER", re.I | re.M),
        Severity.HIGH,
        [Correction({"ALGO": "All"}, description="ALGO=All", confidence=0.75)],
    ),
    (
        "subspacematrix",
        re.compile(r"WARNING: Sub-Space-Matrix is not hermitian", re.I | re.M),
        Severity.MEDIUM,
        [
            Correction({"ALGO": "Normal"}, description="ALGO Fast→Normal", confidence=0.85),
            Correction({"LSUBROT": False}, description="disable subspace rotation", confidence=0.75),
        ],
    ),

    # ---- Lattice --------------------------------------------------------------
    (
        "amin",
        re.compile(r"One of the lattice vectors is very long", re.I | re.M),
        Severity.LOW,
        [Correction({"AMIN": 0.01}, description="reduce AMIN", confidence=0.85)],
    ),
    (
        "lattice_small",
        re.compile(r"lattice vectors.*too small|length of lattice vector.*too small", re.I | re.M),
        Severity.HIGH,
        [Correction({}, actions=("enlarge_cell",),
                    description="enlarge cell — not a pure INCAR fix", confidence=0.60)],
    ),

    # ---- Parallelisation ------------------------------------------------------
    (
        "elf_kpar",
        re.compile(r"ELF.*KPAR", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"KPAR": 1}, description="KPAR=1 for ELF", confidence=0.95)],
    ),
    (
        "elf_ncl",
        re.compile(r"ELF.*non-collinear", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"LELF": False}, description="disable LELF under non-collinear", confidence=0.90)],
    ),
    (
        "kpar_error",
        re.compile(r"KPAR.*not compatible|KPAR.*error", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"KPAR": 1}, description="KPAR=1", confidence=0.85)],
    ),
    (
        "ncore_error",
        re.compile(r"NCORE.*must divide|NCORE.*incompatible", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"NCORE": 1}, description="NCORE=1 (safe default)", confidence=0.85)],
    ),

    # ---- DFPT / finite-difference --------------------------------------------
    (
        "dfpt_ncore",
        re.compile(r"DFPT.*NCORE|LEPSILON.*NCORE", re.I | re.M),
        Severity.HIGH,
        [Correction({"NCORE": 1}, description="NCORE=1 required for DFPT", confidence=0.95)],
    ),
    (
        "finite_diff",
        re.compile(r"finite difference.*failed|IBRION=5.*error", re.I | re.M),
        Severity.MEDIUM,
        [Correction({"POTIM": 0.015}, description="tighten finite-difference step", confidence=0.75)],
    ),

    # ---- Job/runtime ----------------------------------------------------------
    (
        "walltime",
        re.compile(r"walltime|TIME LIMIT|DUE TO TIME LIMIT|job cancelled.*time", re.I | re.M),
        Severity.HIGH,
        [Correction({}, actions=("request_more_walltime", "continue_from_contcar"),
                    description="resubmit with longer walltime, restart from CONTCAR", confidence=0.85)],
    ),
    # NOTE: frozen_job is not a log-regex pattern — it's a wall-clock detection
    # owned by custodian's FrozenJobErrorHandler (wired in handlers/bundle.py).
    # We intentionally do NOT register a regex here to avoid matching blank lines.
]


# -----------------------------------------------------------------------------
# Action hooks — side effects beyond INCAR patches
# -----------------------------------------------------------------------------

def _apply_action(name: str, incar, work_dir: Path) -> None:
    if name.startswith("increase_nbands_"):
        pct = int(name.rsplit("_", 1)[-1])
        cur = incar.get("NBANDS")
        if cur is not None:
            incar["NBANDS"] = int(cur * (1 + pct / 100))
        else:
            # read from OUTCAR if present
            nbands = _read_nbands_from_outcar(work_dir)
            if nbands:
                incar["NBANDS"] = int(nbands * (1 + pct / 100))
    elif name == "gamma_centered_kpoints":
        _flip_kpoints_to_gamma(work_dir)
    elif name == "reduce_kpoints":
        _scale_kpoints(work_dir, 0.75)
    elif name == "continue_from_contcar":
        contcar = work_dir / "CONTCAR"
        poscar = work_dir / "POSCAR"
        if contcar.exists() and contcar.stat().st_size > 0:
            poscar.write_text(contcar.read_text(encoding="utf-8"), encoding="utf-8")
    elif name == "strip_ialgo":
        if "IALGO" in incar:
            del incar["IALGO"]
    # request_more_memory / request_more_walltime / increase_encutgw / enlarge_cell:
    # these are scheduler/structure-level actions that the runner layer must observe;
    # recorded in the returned summary so the caller can act on them.


def _read_nbands_from_outcar(work_dir: Path) -> int | None:
    out = work_dir / "OUTCAR"
    if not out.exists():
        return None
    try:
        for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
            if "NBANDS" in line:
                m = re.search(r"NBANDS\s*=\s*(\d+)", line)
                if m:
                    return int(m.group(1))
    except Exception:
        return None
    return None


def _flip_kpoints_to_gamma(work_dir: Path) -> None:
    kp = work_dir / "KPOINTS"
    if not kp.exists():
        return
    lines = kp.read_text(encoding="utf-8").splitlines()
    if len(lines) >= 3:
        if lines[2].strip().lower().startswith("m"):
            lines[2] = "Gamma"
            kp.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scale_kpoints(work_dir: Path, factor: float) -> None:
    kp = work_dir / "KPOINTS"
    if not kp.exists():
        return
    lines = kp.read_text(encoding="utf-8").splitlines()
    if len(lines) >= 4:
        try:
            parts = lines[3].split()
            new = [max(1, int(round(int(p) * factor))) for p in parts[:3]]
            lines[3] = " ".join(str(n) for n in new)
            kp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except ValueError:
            pass  # line-mode or automatic KPOINTS — skip


# -----------------------------------------------------------------------------
# Handler
# -----------------------------------------------------------------------------

class ExtendedVaspErrorHandler:
    """Scan logs for extended errors and patch INCAR in place.

    Per-error correction history is tracked: a strategy is never re-tried after
    it has been attempted in this handler instance (mirroring vasp-agent's
    behaviour). If all strategies for an error are exhausted, the error still
    surfaces in detected errors but no correction is applied.
    """

    # Errors custodian's VaspErrorHandler already handles — skip to avoid double-patching.
    _CUSTODIAN_OWNED = frozenset({
        "zbrent", "brmix", "eddrmm", "edddav", "zpotrf", "tetirr",
        "tet", "dentet", "subspacematrix",
    })

    def __init__(self, work_dir: Path, max_per_error: int = 5,
                 skip_custodian_errors: bool = False):
        self.work_dir = Path(work_dir)
        self.max_per_error = max_per_error
        self.skip_custodian_errors = skip_custodian_errors
        self._history: dict[str, list[Correction]] = {}
        self._last_detected: list[DetectedError] = []
        self._last_corrections: list[tuple[DetectedError, Correction]] = []

    def _scan_text(self) -> str:
        blob = ""
        for fname in ("vasp.out", "OUTCAR", "stderr.txt", "run.log"):
            f = self.work_dir / fname
            if not f.exists():
                continue
            try:
                blob += f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        return blob

    def detect(self) -> list[DetectedError]:
        blob = self._scan_text()
        detected: list[DetectedError] = []
        for name, pat, severity, _ in PATTERNS:
            if self.skip_custodian_errors and name in self._CUSTODIAN_OWNED:
                continue
            for m in pat.finditer(blob):
                line = blob[: m.start()].count("\n") + 1
                detected.append(DetectedError(name=name, message=m.group(0),
                                              severity=severity, line_number=line,
                                              source="combined"))
                break  # one detection per pattern per scan is enough
        detected.sort(key=lambda e: _SEVERITY_ORDER[e.severity])
        return detected

    def _pick_correction(self, name: str) -> Correction | None:
        strategies: list[Correction] = []
        for n, _, _, corrs in PATTERNS:
            if n == name:
                strategies = corrs
                break
        if not strategies:
            return None
        tried = self._history.setdefault(name, [])
        if len(tried) >= self.max_per_error:
            return None
        for c in strategies:
            if c not in tried:
                tried.append(c)
                return c
        return None

    # Bundle-protocol hooks --------------------------------------------------
    def check(self) -> bool:
        self._last_detected = self.detect()
        self._last_corrections = []
        for err in self._last_detected:
            c = self._pick_correction(err.name)
            if c is not None:
                self._last_corrections.append((err, c))
        return len(self._last_corrections) > 0

    def correct(self) -> dict[str, Any]:
        if not self._last_corrections:
            return {"detected": [e.name for e in self._last_detected], "applied": []}
        from pymatgen.io.vasp.inputs import Incar
        incar_path = self.work_dir / "INCAR"
        incar = Incar.from_file(str(incar_path)) if incar_path.exists() else Incar()
        applied: list[dict[str, Any]] = []
        side_effects: list[str] = []
        for err, c in self._last_corrections:
            incar.update(c.incar_updates)
            for act in c.actions:
                _apply_action(act, incar, self.work_dir)
                # Scheduler-level actions surface to the runner
                if act in ("request_more_memory", "request_more_walltime",
                           "increase_encutgw", "enlarge_cell"):
                    side_effects.append(act)
            applied.append({
                "error": err.name,
                "severity": err.severity.value,
                "fix": c.description,
                "confidence": c.confidence,
                "incar_updates": dict(c.incar_updates),
                "actions": list(c.actions),
            })
        incar.write_file(str(incar_path))
        return {"detected": [e.name for e in self._last_detected],
                "applied": applied,
                "side_effects": side_effects}

    # Introspection ----------------------------------------------------------
    def history(self) -> dict[str, list[str]]:
        return {k: [c.description for c in v] for k, v in self._history.items()}

    def reset(self, name: str | None = None) -> None:
        if name is None:
            self._history.clear()
        else:
            self._history.pop(name, None)


# Back-compat exports
EXTENDED_PATTERNS = [(name, pat, corrs) for name, pat, _, corrs in PATTERNS]
