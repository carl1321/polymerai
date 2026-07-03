#!/usr/bin/env python3
"""vasp-phonon CLI — finite-displacement phonons via phonopy + VASP.

Workflow:
  stage=prepare  → phonopy generates SPOSCAR + POSCAR-00N, VASP inputs written per disp
  stage=run      → run VASP for each displacement (ISIF=2, IBRION=-1, NSW=1)
  stage=collect  → phonopy -f vasprun*.xml → FORCE_SETS, then bands + DOS
  stage=all      → prepare → run → collect

Requires `phonopy` installed: `pip install phonopy`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_relax_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, emit_deerflow_async_envelope, resolve_vasp_command
from vasp_skills_lib.runtime import RuntimeState, append_event, read_progress, write_progress
from vasp_skills_lib.scheduler import JobScheduler
from vasp_skills_lib.executor import get_executor

sys.path.insert(0, str(Path(__file__).parent))


def _check_phonopy() -> bool:
    try:
        import phonopy  # noqa: F401
        return True
    except ImportError:
        print("ERROR: phonopy not installed. `pip install phonopy`.", file=sys.stderr)
        return False


def _infer_expected_displacements(work_dir: Path) -> int:
    poscars = sorted(work_dir.glob("POSCAR-???"))
    if poscars:
        return len(poscars)
    subs = sorted(p for p in work_dir.iterdir() if p.is_dir() and p.name.startswith("disp-"))
    return len(subs)


def _phonon_contract(work_dir: Path) -> tuple[int, list[Path]]:
    subs = sorted(p for p in work_dir.iterdir() if p.is_dir() and p.name.startswith("disp-"))
    progress = read_progress(work_dir)
    expected = progress.get("expected_displacements")
    if expected is None:
        expected = _infer_expected_displacements(work_dir)
    return int(expected or 0), subs


def _check_run_prereqs(work_dir: Path) -> tuple[int, list[Path]]:
    expected, subs = _phonon_contract(work_dir)
    if not subs:
        raise RuntimeError("phonon run requires disp-* directories; run stage=prepare first")
    if expected and len(subs) != expected:
        raise RuntimeError(
            f"phonon run found {len(subs)} disp dirs but expected {expected}; rerun stage=prepare"
        )
    return expected or len(subs), subs


def _write_summary(work_dir: Path, payload: dict) -> None:
    (work_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _prepare(args, config) -> int:
    if not _check_phonopy():
        return 1
    from phonopy_driver import generate_displacements

    poscars = generate_displacements(
        args.poscar,
        args.work_dir,
        supercell=tuple(args.supercell),
        displacement=args.disp,
    )
    print(f"Generated {len(poscars)} displaced supercells.")
    from pymatgen.core import Structure

    for pos in poscars:
        idx = pos.stem.split("-")[-1]
        sub = args.work_dir / f"disp-{idx}"
        sub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pos, sub / "POSCAR")
        structure = Structure.from_file(str(sub / "POSCAR"))
        build_relax_inputs(
            structure,
            sub,
            user_incar=args.incar,
            incar_overrides={
                "ISIF": 2,
                "IBRION": -1,
                "NSW": 1,
                "EDIFF": 1e-7,
                "PREC": "Accurate",
                "LREAL": False,
                "ADDGRID": True,
            },
        )
        if args.potcar is not None:
            shutil.copy2(args.potcar, sub / "POTCAR")
        else:
            try:
                generate_potcar(
                    sub / "POSCAR",
                    sub,
                    functional=config.potcar.get("functional", "PBE"),
                    backend=config.potcar.get("backend", "vasp-potcar"),
                )
            except Exception as e:
                print(f"WARN POTCAR {sub}: {e}", file=sys.stderr)

    write_progress(
        args.work_dir,
        {
            "software": "vasp",
            "workflow": "phonon",
            "stage": "prepare",
            "state": RuntimeState.QUEUED,
            "expected_displacements": len(poscars),
            "completed_displacements": 0,
            "supercell": list(args.supercell),
            "displacement": args.disp,
        },
    )
    append_event(
        args.work_dir,
        {
            "event": "phonon_prepare_finished",
            "expected_displacements": len(poscars),
        },
    )
    _write_summary(
        args.work_dir,
        {
            "success": True,
            "stage": "prepare",
            "expected_displacements": len(poscars),
        },
    )
    return 0


def _run(args, config) -> int:
    try:
        expected, subs = _check_run_prereqs(args.work_dir)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    cmd = resolve_vasp_command(config, args.executor)
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-phonon")
    entries = [{"work_dir": str(sub.resolve()), "job_name": "vasp-phonon"} for sub in subs]
    meta = {
        "kind": "phonon_run",
        "expected_displacements": expected,
        "submit_script": submit_script,
        "entries": entries,
        "max_concurrent": args.max_concurrent,
        "poll_interval": args.poll_interval,
        "max_errors": args.max_errors,
        "use_handlers": not args.no_handlers,
        "executor": args.executor,
    }
    rt = args.work_dir / ".calc_runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "detached_group.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    state_file = rt / "phonon_jobs.json"
    build_map: dict[str, object] = {str(sub.resolve()): (lambda s=submit_script: s) for sub in subs}
    with get_executor(config, args.executor) as ex:
        sched = JobScheduler(
            ex,
            state_file=state_file,
            max_concurrent=args.max_concurrent,
            poll_interval=args.poll_interval,
            max_errors=args.max_errors,
            use_handlers=not args.no_handlers,
        )
        for sub in subs:
            sched.add(sub, build_map[str(sub.resolve())], job_name="vasp-phonon")
        if args.resume:
            sched.restore(build_scripts=build_map, on_dones=None)
        sched.submit_all()

    poll_cmd = " ".join(
        [
            "python",
            "-m",
            "vasp_skills_lib.scheduler_group_poll",
            "--work-root",
            shlex.quote(str(args.work_dir.resolve())),
            "--state-file",
            shlex.quote(str(state_file.resolve())),
        ]
        + (["--config", shlex.quote(str(args.config.resolve()))] if args.config is not None else [])
    )
    emit_deerflow_async_envelope(
        work_dir=args.work_dir,
        config_path=args.config,
        job_id=None,
        task_kind="vasp_phonon_run",
        display_name=args.poscar.stem or "vasp-phonon",
        poll_interval_seconds=max(args.poll_interval, 60),
        poll_command=poll_cmd,
    )
    summary_payload = {
        "submitted": True,
        "stage": "run",
        "expected_displacements": expected,
        "work_dir": str(args.work_dir.resolve()),
        "note": "disp energies finalized in summary.json after gateway polls phonon_jobs.",
    }
    _write_summary(args.work_dir, summary_payload)
    write_progress(
        args.work_dir,
        {
            "software": "vasp",
            "workflow": "phonon",
            "stage": "run",
            "state": RuntimeState.RUNNING,
            "expected_displacements": expected,
            "completed_displacements": 0,
        },
    )
    append_event(
        args.work_dir,
        {
            "event": "phonon_run_submitted",
            "expected_displacements": expected,
        },
    )
    print(json.dumps(summary_payload, indent=2, ensure_ascii=False))
    return 0


def _collect(args, config) -> int:
    if not _check_phonopy():
        return 1
    from phonopy_driver import collect_forces, compute_bands_dos

    expected, subs = _phonon_contract(args.work_dir)
    if not subs:
        print("No disp-* directories found. Run stage=prepare first.", file=sys.stderr)
        return 1
    if not (args.work_dir / "phonopy_disp.yaml").exists():
        print("phonopy_disp.yaml not found. Run stage=prepare first.", file=sys.stderr)
        return 1

    vaspruns = sorted(sub / "vasprun.xml" for sub in subs if (sub / "vasprun.xml").exists())
    completed = len(vaspruns)
    expected = expected or len(subs)
    if completed != expected:
        print(
            f"Phonon collect requires {expected} completed displacements, found {completed}.",
            file=sys.stderr,
        )
        _write_summary(
            args.work_dir,
            {
                "success": False,
                "stage": "collect",
                "expected_displacements": expected,
                "completed_displacements": completed,
                "error": "incomplete_displacements",
            },
        )
        write_progress(
            args.work_dir,
            {
                "software": "vasp",
                "workflow": "phonon",
                "stage": "collect",
                "state": RuntimeState.FAILED,
                "expected_displacements": expected,
                "completed_displacements": completed,
            },
        )
        return 2

    write_progress(
        args.work_dir,
        {
            "software": "vasp",
            "workflow": "phonon",
            "stage": "collect",
            "state": RuntimeState.PARSING,
            "expected_displacements": expected,
            "completed_displacements": completed,
        },
    )

    try:
        collect_forces(args.work_dir, vaspruns)
        res = compute_bands_dos(args.work_dir, mesh=tuple(args.mesh))
    except Exception as e:
        print(f"Phonon collect failed: {e}", file=sys.stderr)
        _write_summary(
            args.work_dir,
            {
                "success": False,
                "stage": "collect",
                "expected_displacements": expected,
                "completed_displacements": completed,
                "error": str(e),
            },
        )
        write_progress(args.work_dir, {"state": RuntimeState.FAILED})
        append_event(args.work_dir, {"event": "phonon_collect_failed", "error": str(e)})
        return 2

    summary = {
        "success": True,
        "stage": "collect",
        "expected_displacements": expected,
        "completed_displacements": completed,
        "outputs": res,
    }
    _write_summary(args.work_dir, summary)
    write_progress(args.work_dir, {"stage": "collect", "state": RuntimeState.FINISHED})
    append_event(args.work_dir, {"event": "phonon_collect_finished", "outputs": res})
    print(f"Done. {res}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-phonon")
    p.add_argument("poscar", type=Path, help="primitive-cell POSCAR (relaxed)")
    p.add_argument("--work-dir", type=Path, default=Path("./phonon"))
    p.add_argument("--stage", choices=["prepare", "run", "collect", "all"], default="all")
    p.add_argument("--supercell", nargs=3, type=int, default=[2, 2, 2])
    p.add_argument("--disp", type=float, default=0.01)
    p.add_argument("--mesh", nargs=3, type=int, default=[31, 31, 31])
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--executor", choices=["local", "ssh", "scnet"], default=None)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None, help="User-supplied POTCAR (skip auto-gen)")
    p.add_argument("--no-handlers", action="store_true")
    p.add_argument("--max-errors", type=int, default=5)
    p.add_argument("--max-concurrent", type=int, default=8,
                   help="并发提交的最大 disp 数 (默认 8)")
    p.add_argument("--poll-interval", type=int, default=60,
                   help="状态轮询间隔秒 (默认 60)")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="忽略 phonon_jobs.json，从头重新提交所有 disp")
    p.set_defaults(resume=True)
    args = p.parse_args()

    if not args.poscar.exists():
        print(f"POSCAR not found: {args.poscar}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    if args.stage in ("prepare", "all"):
        rc = _prepare(args, config)
        if rc != 0:
            return rc
    if args.stage in ("run", "all"):
        rc = _run(args, config)
        if rc != 0:
            return rc
    if args.stage in ("collect", "all"):
        return _collect(args, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
