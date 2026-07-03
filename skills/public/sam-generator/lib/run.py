"""Runnable entry for SAM molecule generation. Used by tool.py and scripts/generate.py."""


def run_generate(
    scaffold_condition: str,
    anchoring_group: str,
    gen_size: int = 10,
) -> list[dict]:
    """Generate SAM molecules from scaffold condition and anchoring group.

    Args:
        scaffold_condition: Comma-separated scaffold SMILES (e.g. "c1ccccc1,c1ccc2c(c1)[nH]c1ccccc12").
        anchoring_group: Anchoring group SMILES (e.g. "O=P(O)(O)").
        gen_size: Number of molecules to generate (default 10).

    Returns:
        List of dicts with keys: smiles, scaffold_condition, scaffold_smiles.
    """
    from .sam_generator import SAMGenerator

    scaffolds = [s.strip() for s in scaffold_condition.split(",") if s.strip()]
    if not scaffolds:
        return []
    generator = SAMGenerator(scaffolds, anchoring_group, gen_size)
    return generator.generate_with_scaffold()
