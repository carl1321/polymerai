"""
BaseBuilder - 构建器基类
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from modeling.core.structure import Structure


class BaseBuilder(ABC):
    """
    构建器抽象基类

    所有具体构建器需要继承此类并实现build方法
    """

    # 构建器名称
    name: str = "base"

    # 必需参数
    required_params: list = []

    # 可选参数及默认值
    default_params: Dict[str, Any] = {}

    # 若为 True，Pipeline 会把上一步结构作为 `prev` 关键字传入 build()
    accepts_prev: bool = False

    def __init__(self):
        self._last_params: Dict[str, Any] = {}

    @abstractmethod
    def build(self, **params) -> Structure:
        """
        构建结构

        Args:
            **params: 构建参数

        Returns:
            Structure对象
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

    def __call__(self, **params) -> Structure:
        """允许直接调用构建器"""
        validated = self.validate_params(params)
        self._last_params = validated
        return self.build(**validated)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
