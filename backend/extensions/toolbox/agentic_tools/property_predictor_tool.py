"""Property predictor tool (compat alias).

This tool exists to support UIs / prompts that refer to the legacy tool name
`property_predictor_tool`.

Implementation strategy:
- Delegate to the skill-backed tool `predict_sam_properties` resolved dynamically
  from the repo `skills/` root via `extensions.toolbox.agentic_tools.skill_tools`.
"""

import logging

from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool("property_predictor_tool")
def property_predictor_tool(smiles_text: str, properties: str = "HOMO,LUMO,DM") -> str:
    """Predict SAM molecule properties (compat wrapper).

    Args:
        smiles_text: Free-form text containing SMILES (one per line is fine).
        properties: Comma-separated property names, default "HOMO,LUMO,DM".
    """
    try:
        from extensions.toolbox.agentic_tools import skill_tools

        predict = getattr(skill_tools, "predict_sam_properties")
        return predict(smiles_text=smiles_text, properties=properties)
    except Exception as e:
        logger.exception("property_predictor_tool failed: %s", e)
        return f"Error: property_predictor_tool failed: {e}"
