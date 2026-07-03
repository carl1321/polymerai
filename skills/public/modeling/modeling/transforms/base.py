"""
BaseTransform - 变换器基类
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class BaseTransform(ABC):
    """
    变换器抽象基类

    变换器将已有结构转换为新结构

    与 Builder 的区别:
    - Builder: 从无到有创建结构 (参数 -> Structure)
    - Transform: 变换已有结构 (Structure + 参数 -> Structure)
    """

    # 变换器名称
    name: str = "base"

    # 必需参数
    required_params: list = []

    # 可选参数及默认值
    default_params: Dict[str, Any] = {}

    def __init__(self, **params):
        """
        初始化变换器

        Args:
            **params: 变换参数，在 apply() 时使用
        """
        self.params = self.validate_params(params)

    @abstractmethod
    def apply(self, structure: "Structure") -> "Structure":
        """
        应用变换

        Args:
            structure: 输入结构

        Returns:
            变换后的新结构
        """
        pass

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证并补全参数

        Args:
            params: 用户提供的参数

        Returns:
            补全后的参数

        Raises:
            ValueError: 缺少必需参数
        """
        # 检查必需参数
        missing = [p for p in self.required_params if p not in params]
        if missing:
            raise ValueError(f"{self.name}: 缺少必需参数: {missing}")

        # 补全默认参数
        full_params = self.default_params.copy()
        full_params.update(params)

        return full_params

    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典 (用于 Recipe)

        Returns:
            包含类型和参数的字典
        """
        return {
            "type": "transform",
            "name": self.name,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseTransform":
        """
        从字典反序列化

        Args:
            data: 字典数据

        Returns:
            Transform 实例
        """
        params = data.get("params", {})
        return cls(**params)

    def __call__(self, structure: "Structure") -> "Structure":
        """允许直接调用变换器"""
        return self.apply(structure)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.params})"
