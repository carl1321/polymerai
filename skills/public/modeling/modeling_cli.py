"""
modeling_cli.py — CLI entry for the modeling skill.

Thin argparse wrapper around Recipe → Pipeline → Structure → writer. Five
subcommands: run, convert, validate, tools, list. Single-step operations are
expressed as one-step Recipes rather than dedicated subcommands; see
references/recipes.md for templates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def cmd_run(args: argparse.Namespace) -> int:
    from modeling.recipe import Recipe
    from modeling.io import write_structure

    recipe = Recipe.load(args.recipe)
    pipeline = recipe.to_pipeline()
    structure = pipeline.run()

    meta_output = recipe.metadata.get("output", {}) if isinstance(recipe.metadata, dict) else {}
    out_path = args.output or meta_output.get("filename")
    out_format = args.format or meta_output.get("format")

    if out_path is None:
        print("ERROR: no output path (pass -o or set metadata.output.filename)", file=sys.stderr)
        return 2

    write_structure(structure, out_path, format=out_format) if out_format else write_structure(structure, out_path)
    print(f"Wrote {out_path} ({len(structure.positions)} atoms)")

    if args.validate:
        return _run_validators(structure, level=args.validate_level)
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    from modeling.io import read_structure, write_structure

    structure = read_structure(args.input)
    if args.format:
        write_structure(structure, args.output, format=args.format)
    else:
        write_structure(structure, args.output)
    print(f"Converted {args.input} -> {args.output}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from modeling.io import read_structure

    structure = read_structure(args.structure)
    return _run_validators(structure, level=args.level)


def cmd_tools(_: argparse.Namespace) -> int:
    from modeling.tools import check_tools_availability

    status = check_tools_availability()
    width = max(len(k) for k in status)
    for name, ok in status.items():
        mark = "OK" if ok else "missing"
        print(f"  {name:<{width}}  {mark}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from modeling.recipe import Recipe

    if args.kind == "builders":
        registry = Recipe._get_builder_registry()
    else:
        registry = Recipe._get_transform_registry()
    for key, cls in sorted(registry.items()):
        print(f"  {key:<14}  {cls.__module__}.{cls.__name__}")
    return 0


def _run_validators(structure, level: int) -> int:
    from modeling.validators import GeometryValidator, ChemistryValidator, PhysicsValidator

    validators = [GeometryValidator()]
    if level >= 2:
        validators.append(ChemistryValidator())
    if level >= 3:
        validators.append(PhysicsValidator())

    exit_code = 0
    for v in validators:
        result = v.validate(structure)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        for issue in result.issues:
            print(f"    {issue}")
            if issue.suggestion:
                print(f"      suggestion: {issue.suggestion}")
        if not result.passed:
            exit_code = 1
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modeling_cli",
        description="Atomic-scale structure modeling CLI (Recipe-driven).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Execute a Recipe JSON and write output.")
    p_run.add_argument("recipe", help="Path to recipe JSON file.")
    p_run.add_argument("-o", "--output", help="Output structure path (overrides recipe.metadata.output.filename).")
    p_run.add_argument("--format", help="Output format override (e.g. poscar, lammps, gro, xyz, pdb, cif, gaussian).")
    p_run.add_argument("--validate", action="store_true", help="Run validators on the final structure.")
    p_run.add_argument("--validate-level", type=int, default=2, choices=[1, 2, 3], help="Validation level (default 2).")
    p_run.set_defaults(func=cmd_run)

    p_conv = sub.add_parser("convert", help="Convert a structure file between formats.")
    p_conv.add_argument("-i", "--input", required=True)
    p_conv.add_argument("-o", "--output", required=True)
    p_conv.add_argument("--format", help="Output format override (default: inferred from extension).")
    p_conv.set_defaults(func=cmd_convert)

    p_val = sub.add_parser("validate", help="Validate a structure file.")
    p_val.add_argument("structure")
    p_val.add_argument("--level", type=int, default=2, choices=[1, 2, 3], help="Validation depth (default 2).")
    p_val.set_defaults(func=cmd_validate)

    p_tools = sub.add_parser("tools", help="Report backend tool availability.")
    p_tools.set_defaults(func=cmd_tools)

    p_list = sub.add_parser("list", help="List available builders or transforms.")
    p_list.add_argument("kind", choices=["builders", "transforms"])
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
