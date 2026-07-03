"""
Component - 建模组件基类
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import numpy as np


class ComponentType(Enum):
    """组件类型"""
    BOX = "box"
    NANOTUBE = "nanotube"
    SLAB = "slab"
    CRYSTAL = "crystal"
    MOLECULE = "molecule"
    FILLER = "filler"


class PlacementType(Enum):
    """放置方式"""
    CENTER = "center"
    ORIGIN = "origin"
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


@dataclass
class Placement:
    """
    放置信息

    Attributes:
        type: 放置类型
        position: 位置坐标 (nm)
        rotation: 旋转角度 (度)
    """
    type: PlacementType = PlacementType.CENTER
    position: Optional[np.ndarray] = None  # nm
    rotation: Optional[np.ndarray] = None  # degrees, [rx, ry, rz]

    @classmethod
    def at_center(cls) -> Placement:
        return cls(type=PlacementType.CENTER)

    @classmethod
    def at_origin(cls) -> Placement:
        return cls(type=PlacementType.ORIGIN)

    @classmethod
    def at_position(cls, x: float, y: float, z: float) -> Placement:
        return cls(type=PlacementType.ABSOLUTE, position=np.array([x, y, z]))


@dataclass
class Component:
    """
    建模组件

    表示建模过程中的一个组件（如纳米管、分子、填充区域等）

    Attributes:
        type: 组件类型
        name: 组件名称
        placement: 放置信息
        params: 组件特定参数
        structure: 构建后的结构 (延迟生成)
    """

    type: ComponentType
    name: str = ""
    placement: Placement = field(default_factory=Placement.at_center)
    params: Dict[str, Any] = field(default_factory=dict)
    structure: Optional[Any] = None  # Structure, 延迟导入避免循环依赖

    def is_built(self) -> bool:
        """是否已构建"""
        return self.structure is not None

    def __repr__(self) -> str:
        status = "built" if self.is_built() else "pending"
        return f"Component({self.type.value}, name='{self.name}', {status})"
