"""
Recipe - 操作序列的序列化/反序列化

支持将 Pipeline 导出为 JSON 格式，便于：
- LLM 生成
- 保存/加载
- 编辑/修改
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import json


class Recipe:
    """
    Recipe - 建模操作配方

    将建模操作序列化为 JSON 格式

    Example:
        >>> recipe = Recipe("my_structure")
        >>> recipe.add_builder("bulk", element="Pt")
        >>> recipe.add_transform("slab", miller=[1,1,1], layers=4)
        >>> recipe.save("my_recipe.json")

        # 从 JSON 加载
        >>> recipe = Recipe.load("my_recipe.json")
        >>> pipeline = recipe.to_pipeline()
        >>> structure = pipeline.run()
    """

    def __init__(self, name: str = "unnamed"):
        """
        初始化 Recipe

        Args:
            name: Recipe 名称
        """
        self.name = name
        self.steps: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}

    def add_builder(self, name: str, **params) -> "Recipe":
        """
        添加 Builder 步骤

        Args:
            name: Builder 名称 (bulk, box, molecule, filler)
            **params: Builder 参数

        Returns:
            self，支持链式调用
        """
        self.steps.append({
            "type": "builder",
            "name": name,
            "params": params,
        })
        return self

    def add_transform(self, name: str, **params) -> "Recipe":
        """
        添加 Transform 步骤

        Args:
            name: Transform 名称 (slab, supercell, defect, adsorbate, vacuum, rotate, translate, mirror)
            **params: Transform 参数

        Returns:
            self，支持链式调用
        """
        self.steps.append({
            "type": "transform",
            "name": name,
            "params": params,
        })
        return self

    def to_dict(self) -> Dict[str, Any]:
        """
        导出为字典

        Returns:
            Recipe 字典
        """
        return {
            "name": self.name,
            "steps": self.steps,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """
        导出为 JSON 字符串

        Args:
            indent: 缩进空格数

        Returns:
            JSON 字符串
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, filepath: str):
        """
        保存到文件

        Args:
            filepath: 文件路径
        """
        Path(filepath).write_text(self.to_json(), encoding='utf-8')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recipe":
        """
        从字典创建 Recipe

        Args:
            data: Recipe 字典

        Returns:
            Recipe 实例
        """
        recipe = cls(name=data.get("name", "unnamed"))
        recipe.steps = data.get("steps", [])
        recipe.metadata = data.get("metadata", {})
        return recipe

    @classmethod
    def from_json(cls, json_str: str) -> "Recipe":
        """
        从 JSON 字符串创建 Recipe

        Args:
            json_str: JSON 字符串

        Returns:
            Recipe 实例
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def load(cls, filepath: str) -> "Recipe":
        """
        从文件加载 Recipe

        Args:
            filepath: 文件路径

        Returns:
            Recipe 实例
        """
        content = Path(filepath).read_text(encoding='utf-8')
        return cls.from_json(content)

    @classmethod
    def from_pipeline(cls, pipeline: "Pipeline") -> "Recipe":
        """
        从 Pipeline 创建 Recipe

        Args:
            pipeline: Pipeline 实例

        Returns:
            Recipe 实例
        """
        from modeling.builders.base import BaseBuilder
        from modeling.transforms.base import BaseTransform

        recipe = cls()

        for step in pipeline.steps:
            if isinstance(step, BaseBuilder):
                recipe.steps.append({
                    "type": "builder",
                    "name": step.name,
                    "params": getattr(step, '_last_params', {}),
                })
            elif isinstance(step, BaseTransform):
                recipe.steps.append(step.to_dict())

        return recipe

    def to_pipeline(self) -> "Pipeline":
        """
        转换为 Pipeline

        Returns:
            Pipeline 实例
        """
        from modeling.pipeline import Pipeline

        # Builder 和 Transform 的注册表
        builder_registry = self._get_builder_registry()
        transform_registry = self._get_transform_registry()

        steps = []
        for step_data in self.steps:
            step_type = step_data["type"]
            step_name = step_data["name"]
            params = step_data.get("params", {})

            if step_type == "builder":
                if step_name not in builder_registry:
                    raise ValueError(f"未知的 Builder: {step_name}")
                builder_cls = builder_registry[step_name]
                # 对于 Builder，参数在 build() 时传入
                builder = builder_cls()
                builder._last_params = params
                steps.append(builder)

            elif step_type == "transform":
                if step_name not in transform_registry:
                    raise ValueError(f"未知的 Transform: {step_name}")
                transform_cls = transform_registry[step_name]
                steps.append(transform_cls(**params))

            else:
                raise ValueError(f"未知的步骤类型: {step_type}")

        return Pipeline(steps)

    @staticmethod
    def _get_builder_registry() -> Dict[str, type]:
        """获取 Builder 注册表"""
        from modeling.builders import BoxBuilder, Filler, Assembler
        from modeling.builders.bulk import BulkBuilder
        from modeling.builders.molecule import MoleculeBuilder

        return {
            "box": BoxBuilder,
            "bulk": BulkBuilder,
            "molecule": MoleculeBuilder,
            "filler": Filler,
        }

    @staticmethod
    def _get_transform_registry() -> Dict[str, type]:
        """获取 Transform 注册表"""
        from modeling.transforms import (
            SlabTransform, SupercellTransform, DefectTransform,
            AdsorbateTransform, VacuumTransform,
            RotateTransform, TranslateTransform, MirrorTransform,
        )

        return {
            "slab": SlabTransform,
            "supercell": SupercellTransform,
            "defect": DefectTransform,
            "adsorbate": AdsorbateTransform,
            "vacuum": VacuumTransform,
            "rotate": RotateTransform,
            "translate": TranslateTransform,
            "mirror": MirrorTransform,
        }

    def __len__(self) -> int:
        return len(self.steps)

    def __repr__(self) -> str:
        return f"Recipe(name='{self.name}', steps={len(self.steps)})"
