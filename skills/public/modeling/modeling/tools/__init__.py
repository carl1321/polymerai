"""
工具封装模块

封装外部工具的 Python 接口

工具分类:
- 结构操作: ASE, Atomsk
- 结构生成: PyXtal, VASPKIT
- 分子填充: Packmol
- 拓扑构建: Moltemplate
- 分析可视化: OVITO
- 量子化学: BSE (Basis Set Exchange), xTB
"""

from modeling.tools.ase_tools import ASETools
from modeling.tools.packmol_tools import PackmolTools
from modeling.tools.pyxtal_tools import PyXtalTools
from modeling.tools.atomsk_tools import AtomskTools
from modeling.tools.moltemplate_tools import MoltemplateTools
from modeling.tools.ovito_tools import OvitoTools
from modeling.tools.vaspkit_tools import VaspkitTools
from modeling.tools.bse_tools import BSETools
from modeling.tools.xtb_tools import XTBTools

__all__ = [
    "ASETools",
    "PackmolTools",
    "PyXtalTools",
    "AtomskTools",
    "MoltemplateTools",
    "OvitoTools",
    "VaspkitTools",
    "BSETools",
    "XTBTools",
]


def check_tools_availability() -> dict:
    """
    检查所有工具的可用性

    Returns:
        {工具名: 是否可用} 字典
    """
    return {
        "ASE": ASETools.is_available(),
        "Packmol": PackmolTools.is_available(),
        "PyXtal": PyXtalTools.is_available(),
        "Atomsk": AtomskTools.is_available(),
        "Moltemplate": MoltemplateTools.is_available(),
        "OVITO": OvitoTools.is_available(),
        "VASPKIT": VaspkitTools.is_available(),
        "BSE": BSETools.is_available(),
        "XTB": XTBTools.is_available(),
    }
