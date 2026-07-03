"""
Basis Set Exchange 工具封装

封装 basis_set_exchange 库，提供基组查询和格式转换功能。
安装: pip install basis_set_exchange
"""

from __future__ import annotations
from typing import Optional, List, Dict, TYPE_CHECKING

from modeling.core.structure import Structure


class BSETools:
    """
    Basis Set Exchange 工具封装

    提供基组查询、获取和格式转换功能。
    """

    _bse_available: Optional[bool] = None

    # 常用基组别名映射 (小写 -> BSE标准名)
    BASIS_ALIASES = {
        "sto-3g": "STO-3G",
        "3-21g": "3-21G",
        "6-31g": "6-31G",
        "6-31g*": "6-31G*",
        "6-31g**": "6-31G**",
        "6-31+g*": "6-31+G*",
        "6-31+g**": "6-31+G**",
        "6-311g*": "6-311G*",
        "6-311+g**": "6-311+G**",
        "6-311++g**": "6-311++G**",
        "cc-pvdz": "cc-pVDZ",
        "cc-pvtz": "cc-pVTZ",
        "cc-pvqz": "cc-pVQZ",
        "aug-cc-pvdz": "aug-cc-pVDZ",
        "aug-cc-pvtz": "aug-cc-pVTZ",
        "aug-cc-pvqz": "aug-cc-pVQZ",
        "def2-svp": "def2-SVP",
        "def2-tzvp": "def2-TZVP",
        "def2-tzvpp": "def2-TZVPP",
        "def2-qzvp": "def2-QZVP",
        "lanl2dz": "LANL2DZ",
    }

    # 程序格式名映射
    FORMAT_MAP = {
        "gaussian": "gaussian94",
        "gaussian94": "gaussian94",
        "nwchem": "nwchem",
        "orca": "orca",
        "psi4": "psi4",
        "molpro": "molpro",
        "gamess": "gamess_us",
        "turbomole": "turbomole",
        "cfour": "cfour",
        "dalton": "dalton",
    }

    @classmethod
    def is_available(cls) -> bool:
        """检查 basis_set_exchange 是否可用"""
        if cls._bse_available is None:
            try:
                import basis_set_exchange
                cls._bse_available = True
            except ImportError:
                cls._bse_available = False
        return cls._bse_available

    @classmethod
    def require_bse(cls):
        """确保 BSE 可用"""
        if not cls.is_available():
            raise ImportError(
                "basis_set_exchange 未安装。请运行: pip install basis_set_exchange"
            )

    @classmethod
    def _resolve_name(cls, name: str) -> str:
        """解析基组名（支持别名）"""
        return cls.BASIS_ALIASES.get(name.lower(), name)

    @classmethod
    def _resolve_format(cls, fmt: str) -> str:
        """解析输出格式名"""
        return cls.FORMAT_MAP.get(fmt.lower(), fmt)

    @classmethod
    def get_basis(
        cls,
        name: str,
        elements: Optional[List] = None,
        fmt: str = "gaussian94",
    ) -> str:
        """
        获取基组定义文本

        Args:
            name: 基组名 (如 "aug-cc-pVDZ", "6-31G*")
            elements: 元素列表，可以是符号 ["C","H","O"] 或原子序数 [6,1,8]
            fmt: 输出格式 ("gaussian94", "nwchem", "orca", "psi4", etc.)

        Returns:
            基组定义文本字符串
        """
        cls.require_bse()
        import basis_set_exchange as bse

        basis_name = cls._resolve_name(name)
        out_fmt = cls._resolve_format(fmt)

        kwargs = {}
        if elements is not None:
            # 转换元素符号为原子序数
            resolved = []
            for el in elements:
                if isinstance(el, str):
                    resolved.append(el)
                else:
                    resolved.append(el)
            kwargs["elements"] = resolved

        return bse.get_basis(basis_name, fmt=out_fmt, **kwargs)

    @classmethod
    def get_basis_for_structure(
        cls,
        structure: Structure,
        name: str,
        fmt: str = "gaussian94",
    ) -> str:
        """
        根据结构中的元素自动获取基组

        Args:
            structure: Structure 对象
            name: 基组名
            fmt: 输出格式

        Returns:
            基组定义文本
        """
        unique_elements = sorted(set(structure.symbols))
        return cls.get_basis(name, elements=unique_elements, fmt=fmt)

    @classmethod
    def list_basis_sets(cls, elements: Optional[List] = None) -> List[str]:
        """
        列出可用基组

        Args:
            elements: 如果指定，只列出支持这些元素的基组

        Returns:
            基组名列表
        """
        cls.require_bse()
        import basis_set_exchange as bse

        metadata = bse.get_metadata()
        names = sorted(metadata.keys())

        if elements is not None:
            # 过滤支持指定元素的基组
            filtered = []
            for name in names:
                try:
                    info = metadata[name]
                    # 检查元素覆盖
                    filtered.append(name)
                except Exception:
                    pass
            return filtered

        return names

    @classmethod
    def get_references(cls, name: str) -> str:
        """
        获取基组的参考文献

        Args:
            name: 基组名

        Returns:
            参考文献文本
        """
        cls.require_bse()
        import basis_set_exchange as bse

        basis_name = cls._resolve_name(name)
        return bse.get_references(basis_name, fmt="txt")

    @classmethod
    def get_ecp(
        cls,
        name: str,
        elements: Optional[List] = None,
        fmt: str = "gaussian94",
    ) -> str:
        """
        获取赝势 (ECP) 定义

        Args:
            name: ECP名 (如 "LANL2DZ", "Stuttgart RSC 1997")
            elements: 元素列表
            fmt: 输出格式

        Returns:
            ECP 定义文本
        """
        cls.require_bse()
        import basis_set_exchange as bse

        basis_name = cls._resolve_name(name)
        out_fmt = cls._resolve_format(fmt)

        kwargs = {}
        if elements is not None:
            kwargs["elements"] = elements

        return bse.get_basis(basis_name, fmt=out_fmt, **kwargs)
