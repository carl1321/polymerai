"""
BoxBuilder - 模拟盒子构建器
"""

from __future__ import annotations
from typing import Union, Tuple
import numpy as np

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure


class BoxBuilder(BaseBuilder):
    """
    模拟盒子构建器

    创建空的正交模拟盒子，并设置周期性边界条件。

    Parameters:
        size: 盒子尺寸，单位 Å。可以是标量（立方盒子）或 (a, b, c) 三元组
        pbc: 周期性边界条件，默认 [True, True, True]
    """

    name = "box"
    required_params = ["size"]
    default_params = {
        "pbc": [True, True, True],
    }

    def build(
        self,
        size: Union[float, Tuple[float, float, float]],
        pbc: Tuple[bool, bool, bool] = (True, True, True),
        **kwargs,
    ) -> Structure:
        if isinstance(size, (int, float)):
            dims = (float(size),) * 3
        else:
            if len(size) != 3:
                raise ValueError(f"box size must be scalar or length-3, got {size!r}")
            dims = tuple(float(x) for x in size)

        cell = np.diag(dims)
        return Structure(
            positions=np.zeros((0, 3)),
            symbols=[],
            cell=cell,
            pbc=list(pbc),
            name=f"box_{dims[0]:g}x{dims[1]:g}x{dims[2]:g}A",
        )
