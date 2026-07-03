"""
I/O模块

文件读写功能
"""

from modeling.io.readers import read_structure, StructureReader
from modeling.io.writers import write_structure, StructureWriter

__all__ = [
    "read_structure",
    "write_structure",
    "StructureReader",
    "StructureWriter",
]
