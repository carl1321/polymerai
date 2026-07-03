#!/usr/bin/env python3
"""vasp-elastic CLI — elastic constants via 6×2 strain protocol or VASP built-in.

- method=builtin: single VASP run with IBRION=6, ISIF=3, NFREE=2 (VASP does it internally)
- method=manual: generate 12 strained POSCARs, run each via vasp-relax (ISIF=2), fit C_ij
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

import numpy as np
from pymatgen.core import Structure
from pymatgen.io.vasp.inputs import Poscar

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_relax_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, emit_deerflow_async_envelope, resolve_vasp_command, submit_and_emit_async
from vasp_skills_lib.scheduler import JobScheduler
from vasp_skills_lib.executor import get_executor

sys.path.insert(0, str(Path(__file__).parent))
from strain_protocol import generate_strained_structures  # noqa: E402


def _prepare_one(structure: Structure, work_dir: Path, config, args):
    build_relax_inputs(
        structure,
        work_dir,
        user_incar=args.incar,
        incar_overrides={"ISIF": 2, "IBRION": 2, "EDIFFG": -0.005, "PREC": "Accurate"},
    )
    if args.potcar is not None:
        import shutil
        shutil.copy2(args.potcar, work_dir / "POTCAR")
    else:
        try:
            generate_potcar(work_dir / "POSCAR", work_dir,
                            functional=config.potcar.get("functional", "PBE"),
                            backend=config.potcar.get("backend", "vasp-potcar"))
        except Exception as e:
            print(f"WARN: POTCAR gen failed in {work_dir}: {e}", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-elastic")
    p.add_argument("poscar", type=Path, help="relaxed CONTCAR")
    p.add_argument("--method", choices=["builtin", "manual"], default="builtin")
    p.add_argument("--work-dir", type=Path, default=Path("./elastic"))
    p.add_argument("--strain", type=float, default=0.005, help="strain magnitude (manual only)")
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--executor", choices=["local", "ssh", "scnet"], default=None)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None, help="User-supplied POTCAR (skip auto-gen)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-handlers", action="store_true")
    p.add_argument("--max-errors", type=int, default=5)
    p.add_argument("--max-concurrent", type=int, default=8,
                   help="manual 模式下并发提交的最大应变数 (默认 8)")
    p.add_argument("--poll-interval", type=int, default=60)
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.set_defaults(resume=True)
    args = p.parse_args()

    if not args.poscar.exists():
        print(f"POSCAR not found: {args.poscar}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))

    if args.method == "builtin":
        # Single run; VASP handles 6x2 internally
        overrides = {"IBRION": 6, "ISIF": 3, "NFREE": 2, "POTIM": args.strain,
                     "PREC": "Accurate", "EDIFF": 1e-7}
        build_relax_inputs(structure, args.work_dir, user_incar=args.incar, incar_overrides=overrides)
        if args.potcar is not None:
            import shutil
            shutil.copy2(args.potcar, args.work_dir / "POTCAR")
        else:
            try:
                generate_potcar(args.work_dir / "POSCAR", args.work_dir,
                                functional=config.potcar.get("functional", "PBE"),
                                backend=config.potcar.get("backend", "vasp-potcar"))
            except Exception as e:
                print(f"WARN: POTCAR gen failed: {e}", file=sys.stderr)

        if args.dry_run:
            print(f"DRY RUN: builtin elastic in {args.work_dir}")
            return 0

        cmd = resolve_vasp_command(config, args.executor)
        submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-elastic")
        submit_and_emit_async(
            args.work_dir,
            cmd,
            config,
            executor_override=args.executor,
            submit_script=submit_script,
            job_name="vasp-elastic",
            task_kind="vasp_elastic",
            display_name=args.poscar.stem or "vasp-elastic",
            config_path=args.config,
        )
        summary = {
            "submitted": True,
            "method": "builtin",
            "work_dir": str(args.work_dir.resolve()),
            "task_kind": "vasp_elastic",
            "note": "TOTAL ELASTIC MODULI in OUTCAR after gateway poll.",
        }
        (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    # manual method: 12 sub-jobs
    strained = generate_strained_structures(structure, magnitude=args.strain)
    print(f"Manual 6×2 strain protocol: {len(strained)} sub-jobs in {args.work_dir}")

    for tag, s in strained:
        sub = args.work_dir / tag
        sub.mkdir(parents=True, exist_ok=True)
        Poscar(s).write_file(str(sub / "POSCAR"))
        _prepare_one(s, sub, config, args)

    if args.dry_run:
        print(f"DRY RUN: 12 strained inputs in {args.work_dir}")
        return 0

    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-elastic")
    tags = [tag for tag, _ in strained]
    entries = [{"work_dir": str((args.work_dir / tag).resolve()), "job_name": f"vasp-elastic-{tag}"} for tag in tags]
    meta = {
        "kind": "elastic_manual",
        "tags": tags,
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
    state_file = rt / "elastic_jobs.json"
    build_map: dict[str, object] = {str((args.work_dir / tag).resolve()): (lambda s=submit_script: s) for tag in tags}
    with get_executor(config, args.executor) as ex:
        sched = JobScheduler(
            ex,
            state_file=state_file,
            max_concurrent=args.max_concurrent,
            poll_interval=args.poll_interval,
            max_errors=args.max_errors,
            use_handlers=not args.no_handlers,
        )
        for tag, _ in strained:
            sub = args.work_dir / tag
            sched.add(sub, build_map[str(sub.resolve())], job_name=f"vasp-elastic-{tag}")
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
        task_kind="vasp_elastic_manual",
        display_name=args.poscar.stem or "vasp-elastic",
        poll_interval_seconds=max(args.poll_interval, 60),
        poll_command=poll_cmd,
    )
    stub = {
        "submitted": True,
        "method": "manual",
        "work_dir": str(args.work_dir.resolve()),
        "strains": len(strained),
        "note": "strain energies summarized after gateway polls all elastic_jobs.",
    }
    (args.work_dir / "summary.json").write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stub, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
