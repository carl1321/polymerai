"""
BaseValidator - 验证器基类
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

from modeling.core.structure import Structure


class ValidationLevel(Enum):
    """验证级别"""
    ERROR = "error"      # 必须修复
    WARNING = "warning"  # 建议修复
    INFO = "info"        # 仅供参考


@dataclass
class ValidationIssue:
    """
    验证问题

    Attributes:
        level: 问题级别
        code: 问题代码 (用于程序化处理)
        message: 人类可读消息
        details: 详细信息
        suggestion: 修复建议
    """
    level: ValidationLevel
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    suggestion: Optional[str] = None

    def __repr__(self) -> str:
        return f"[{self.level.value.upper()}] {self.message}"


@dataclass
class ValidationResult:
    """
    单项验证结果

    Attributes:
        name: 验证项名称
        passed: 是否通过
        issues: 发现的问题列表
        metrics: 验证指标
    """
    name: str
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(i.level == ValidationLevel.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.level == ValidationLevel.WARNING for i in self.issues)

    def add_error(self, code: str, message: str, **kwargs):
        self.issues.append(ValidationIssue(
            level=ValidationLevel.ERROR, code=code, message=message, **kwargs
        ))
        self.passed = False

    def add_warning(self, code: str, message: str, **kwargs):
        self.issues.append(ValidationIssue(
            level=ValidationLevel.WARNING, code=code, message=message, **kwargs
        ))

    def add_info(self, code: str, message: str, **kwargs):
        self.issues.append(ValidationIssue(
            level=ValidationLevel.INFO, code=code, message=message, **kwargs
        ))


@dataclass
class ValidationReport:
    """
    完整验证报告

    Attributes:
        structure_name: 被验证的结构名称
        results: 各验证器的结果
    """
    structure_name: str = ""
    results: Dict[str, ValidationResult] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """所有必需验证是否通过"""
        # Level 1 (几何验证) 必须通过
        geometry = self.results.get("geometry")
        return geometry is None or geometry.passed

    @property
    def all_passed(self) -> bool:
        """所有验证是否都通过"""
        return all(r.passed for r in self.results.values())

    @property
    def errors(self) -> List[ValidationIssue]:
        """所有错误"""
        errors = []
        for r in self.results.values():
            errors.extend(i for i in r.issues if i.level == ValidationLevel.ERROR)
        return errors

    @property
    def warnings(self) -> List[ValidationIssue]:
        """所有警告"""
        warnings = []
        for r in self.results.values():
            warnings.extend(i for i in r.issues if i.level == ValidationLevel.WARNING)
        return warnings

    def add_result(self, result: ValidationResult):
        """添加验证结果"""
        self.results[result.name] = result

    def to_markdown(self) -> str:
        """生成Markdown格式报告"""
        lines = [
            f"# 验证报告: {self.structure_name}",
            "",
            f"**状态**: {'✅ 通过' if self.passed else '❌ 未通过'}",
            "",
        ]

        for name, result in self.results.items():
            status = "✅" if result.passed else "❌"
            lines.append(f"## {status} {name}")
            lines.append("")

            # 指标
            if result.metrics:
                for k, v in result.metrics.items():
                    lines.append(f"- {k}: {v}")
                lines.append("")

            # 问题
            if result.issues:
                lines.append("### 问题")
                for issue in result.issues:
                    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}[issue.level.value]
                    lines.append(f"- {icon} {issue.message}")
                    if issue.suggestion:
                        lines.append(f"  - 建议: {issue.suggestion}")
                lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        n_errors = len(self.errors)
        n_warnings = len(self.warnings)
        return f"ValidationReport({status}, errors={n_errors}, warnings={n_warnings})"


class BaseValidator(ABC):
    """
    验证器抽象基类

    所有验证器需要继承此类并实现validate方法
    """

    # 验证器名称
    name: str = "base"

    # 验证级别 (1=必须, 2=建议, 3=可选)
    level: int = 1

    @abstractmethod
    def validate(self, structure: Structure, **kwargs) -> ValidationResult:
        """
        执行验证

        Args:
            structure: 要验证的结构
            **kwargs: 额外参数

        Returns:
            ValidationResult
        """
        pass

    def __call__(self, structure: Structure, **kwargs) -> ValidationResult:
        """允许直接调用验证器"""
        return self.validate(structure, **kwargs)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(level={self.level})"
