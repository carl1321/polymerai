"""
Pipeline - 管道执行器

顺序执行 Builders 和 Transforms
"""

from __future__ import annotations
from typing import List, Union, Optional, Dict, Any
from copy import deepcopy

from modeling.core.structure import Structure
from modeling.builders.base import BaseBuilder
from modeling.transforms.base import BaseTransform


class Pipeline:
    """
    管道执行器

    顺序执行一系列 Builders 和 Transforms，支持：
    - 逐步执行
    - 中间预览
    - 回滚
    - 序列化为 Recipe

    Example:
        >>> pipeline = Pipeline([
        ...     BulkBuilder("Pt"),
        ...     SlabTransform(miller=(1,1,1), layers=4),
        ...     SupercellTransform(matrix=(3,3,1)),
        ... ])
        >>> structure = pipeline.run()

        # 或逐步执行
        >>> pipeline.run_next()  # BulkBuilder
        >>> pipeline.preview()   # 查看当前状态
        >>> pipeline.run_next()  # SlabTransform
    """

    def __init__(
        self,
        steps: Optional[List[Union[BaseBuilder, BaseTransform]]] = None
    ):
        """
        初始化管道

        Args:
            steps: 步骤列表（Builders 和 Transforms）
        """
        self.steps: List[Union[BaseBuilder, BaseTransform]] = steps or []
        self._current_step: int = 0
        self._current_structure: Optional[Structure] = None
        self._history: List[Structure] = []

    def add(self, step: Union[BaseBuilder, BaseTransform]) -> "Pipeline":
        """
        添加步骤

        Args:
            step: Builder 或 Transform

        Returns:
            self，支持链式调用
        """
        self.steps.append(step)
        return self

    def run(self) -> Structure:
        """
        执行所有步骤

        Returns:
            最终结构

        Raises:
            ValueError: 步骤列表为空
            RuntimeError: 执行失败
        """
        if not self.steps:
            raise ValueError("步骤列表为空")

        self.reset()

        while self._current_step < len(self.steps):
            self.run_next()

        return self._current_structure

    def run_next(self) -> Structure:
        """
        执行下一步

        Returns:
            执行后的结构

        Raises:
            StopIteration: 已执行完所有步骤
        """
        if self._current_step >= len(self.steps):
            raise StopIteration("所有步骤已执行完毕")

        step = self.steps[self._current_step]

        # 保存历史（用于回滚）
        if self._current_structure is not None:
            self._history.append(self._current_structure)

        # 执行步骤
        if isinstance(step, BaseBuilder):
            # Builder: 从无到有创建
            params = step._last_params if hasattr(step, '_last_params') else {}
            if getattr(step, 'accepts_prev', False):
                self._current_structure = step.build(prev=self._current_structure, **params)
            else:
                self._current_structure = step.build(**params)
        elif isinstance(step, BaseTransform):
            # Transform: 变换已有结构
            if self._current_structure is None:
                raise RuntimeError(
                    f"Transform '{step.name}' 需要输入结构，"
                    "但当前没有结构。请先执行 Builder。"
                )
            self._current_structure = step.apply(self._current_structure)
        else:
            raise TypeError(f"未知的步骤类型: {type(step)}")

        self._current_step += 1

        return self._current_structure

    def preview(self) -> Optional[Structure]:
        """
        预览当前状态

        Returns:
            当前结构（不执行任何操作）
        """
        return self._current_structure

    def rollback(self, steps: int = 1) -> Optional[Structure]:
        """
        回滚指定步数

        Args:
            steps: 回滚步数

        Returns:
            回滚后的结构
        """
        for _ in range(steps):
            if self._history and self._current_step > 0:
                self._current_structure = self._history.pop()
                self._current_step -= 1

        return self._current_structure

    def reset(self):
        """重置管道状态"""
        self._current_step = 0
        self._current_structure = None
        self._history.clear()

    @property
    def is_complete(self) -> bool:
        """是否已执行完所有步骤"""
        return self._current_step >= len(self.steps)

    @property
    def progress(self) -> str:
        """执行进度"""
        return f"{self._current_step}/{len(self.steps)}"

    def to_recipe(self) -> Dict[str, Any]:
        """
        导出为 Recipe 格式

        Returns:
            Recipe 字典
        """
        from modeling.recipe import Recipe
        return Recipe.from_pipeline(self).to_dict()

    @classmethod
    def from_recipe(cls, recipe: Union[Dict, "Recipe"]) -> "Pipeline":
        """
        从 Recipe 创建 Pipeline

        Args:
            recipe: Recipe 字典或对象

        Returns:
            Pipeline 实例
        """
        from modeling.recipe import Recipe

        if isinstance(recipe, dict):
            recipe = Recipe.from_dict(recipe)

        return recipe.to_pipeline()

    def __len__(self) -> int:
        return len(self.steps)

    def __repr__(self) -> str:
        return f"Pipeline(steps={len(self.steps)}, progress={self.progress})"
