"""vasp-analysis CLI — argparse-based subcommand dispatcher."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_workdir(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workdir", default=".", help="VASP work directory (default: .)")
    p.add_argument("--out", default=None, help="Output file path")
    p.add_argument("--fmt", default="png", choices=("png", "pdf", "svg"))


def _cmd_auto(args: argparse.Namespace) -> int:
    from .workflows.auto import run

    products = run(args.workdir, fmt=args.fmt)
    for kind, path in products.items():
        print(f"{kind}: {path}")
    return 0


def _cmd_band(args: argparse.Namespace) -> int:
    from .plotters.band import plot

    out = plot(args.workdir, projected=args.projected, out=args.out, fmt=args.fmt)
    print(f"band → {out}")
    return 0


def _cmd_dos(args: argparse.Namespace) -> int:
    from .plotters.dos import plot

    out = plot(args.workdir, orbital=args.orbital, element=args.element,
               out=args.out, fmt=args.fmt)
    print(f"dos → {out}")
    return 0


def _cmd_band_dos(args: argparse.Namespace) -> int:
    from .plotters.band_dos import plot

    out = plot(args.workdir, out=args.out, fmt=args.fmt)
    print(f"band+dos → {out}")
    return 0


def _cmd_phonon(args: argparse.Namespace) -> int:
    from .plotters.phonon import plot

    out = plot(args.workdir, supercell=args.supercell, mode=args.mode,
               out=args.out, fmt=args.fmt)
    print(f"phonon → {out}")
    return 0


def _cmd_optical(args: argparse.Namespace) -> int:
    from .plotters.optical import plot

    out = plot(args.workdir, out=args.out, fmt=args.fmt)
    print(f"optical → {out}")
    return 0


def _cmd_fermi(args: argparse.Namespace) -> int:
    from .plotters.fermi import plot

    out = plot(args.workdir, dim=args.dim, out=args.out, fmt=args.fmt)
    print(f"fermi → {out}")
    return 0


def _cmd_unfolding(args: argparse.Namespace) -> int:
    from .plotters.unfolding import plot

    out = plot(args.workdir, supercell=args.supercell, out=args.out, fmt=args.fmt)
    print(f"unfolding → {out}")
    return 0


def _cmd_elastic(args: argparse.Namespace) -> int:
    from .plotters.elastic import plot

    out = plot(args.workdir, out=args.out, fmt=args.fmt)
    print(f"elastic → {out}")
    return 0


def _cmd_defect(args: argparse.Namespace) -> int:
    from .plotters.defect import plot

    defect_dirs = [Path(p) for p in args.defect_dirs.split(",")] if args.defect_dirs else []
    out = plot(Path(args.bulk), defect_dirs=defect_dirs, out=args.out, fmt=args.fmt)
    print(f"defect → {out}")
    return 0


def _cmd_convergence(args: argparse.Namespace) -> int:
    from .plotters.convergence import plot

    dirs = [Path(p) for p in args.dirs.split(",")]
    out = plot(dirs, param=args.param, out=args.out, fmt=args.fmt)
    print(f"convergence → {out}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    from .reporters.summary import write

    out = write(args.workdir, out=args.out)
    print(f"summary → {out}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    from .reporters.comparison import write

    out = write([Path(p) for p in args.dirs], out=args.out)
    print(f"compare → {out}")
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    from .detector import detect

    result = detect(args.workdir)
    print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vasp-analysis",
        description="VASP post-processing and publication-quality plotting.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_auto = sub.add_parser("auto", help="Detect calc type and run all relevant plotters")
    _add_workdir(p_auto)
    p_auto.set_defaults(func=_cmd_auto)

    p_band = sub.add_parser("band", help="Electronic band structure")
    _add_workdir(p_band)
    p_band.add_argument("--projected", action="store_true", help="Element-projected")
    p_band.set_defaults(func=_cmd_band)

    p_dos = sub.add_parser("dos", help="Density of states")
    _add_workdir(p_dos)
    p_dos.add_argument("--orbital", action="store_true")
    p_dos.add_argument("--element", action="store_true")
    p_dos.set_defaults(func=_cmd_dos)

    p_bd = sub.add_parser("band-dos", help="Combined band + DOS")
    _add_workdir(p_bd)
    p_bd.set_defaults(func=_cmd_band_dos)

    p_ph = sub.add_parser("phonon", help="Phonon dispersion (assumes phonopy already run)")
    _add_workdir(p_ph)
    p_ph.add_argument("--supercell", nargs=3, type=int, default=[2, 2, 2])
    p_ph.add_argument("--mode", choices=("finite", "dfpt"), default="finite")
    p_ph.set_defaults(func=_cmd_phonon)

    p_opt = sub.add_parser("optical", help="Dielectric / absorption / reflectance")
    _add_workdir(p_opt)
    p_opt.set_defaults(func=_cmd_optical)

    p_fs = sub.add_parser("fermi", help="Fermi surface (2D or 3D)")
    _add_workdir(p_fs)
    p_fs.add_argument("--dim", choices=("2d", "3d"), default="3d")
    p_fs.set_defaults(func=_cmd_fermi)

    p_unf = sub.add_parser("unfolding", help="Band unfolding (pyprocar)")
    _add_workdir(p_unf)
    p_unf.add_argument("--supercell", nargs=3, type=int, default=[2, 2, 2])
    p_unf.set_defaults(func=_cmd_unfolding)

    p_el = sub.add_parser("elastic", help="Elastic constants heatmap + Voigt/Reuss/Hill")
    _add_workdir(p_el)
    p_el.set_defaults(func=_cmd_elastic)

    p_def = sub.add_parser("defect", help="Defect formation energy diagram")
    p_def.add_argument("--bulk", required=True, help="Bulk reference workdir")
    p_def.add_argument("--defect-dirs", required=True,
                       help="Comma-separated list of defect calc dirs")
    p_def.add_argument("--out", default=None)
    p_def.add_argument("--fmt", default="png")
    p_def.set_defaults(func=_cmd_defect)

    p_conv = sub.add_parser("convergence", help="Plot ENCUT/KPOINTS/SIGMA convergence")
    p_conv.add_argument("--param", required=True, choices=("ENCUT", "KPOINTS", "SIGMA"))
    p_conv.add_argument("--dirs", required=True,
                        help="Comma-separated calc dirs scanning the parameter")
    p_conv.add_argument("--out", default=None)
    p_conv.add_argument("--fmt", default="png")
    p_conv.set_defaults(func=_cmd_convergence)

    p_sum = sub.add_parser("summary", help="Write markdown summary of one workdir")
    _add_workdir(p_sum)
    p_sum.set_defaults(func=_cmd_summary)

    p_cmp = sub.add_parser("compare", help="Compare multiple workdirs")
    p_cmp.add_argument("dirs", nargs="+")
    p_cmp.add_argument("--out", default=None)
    p_cmp.set_defaults(func=_cmd_compare)

    p_det = sub.add_parser("detect", help="Auto-detect calc type from workdir")
    p_det.add_argument("--workdir", default=".")
    p_det.set_defaults(func=_cmd_detect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
