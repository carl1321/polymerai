# Modeling - 原子尺度建模系统

基于自然语言交互的原子尺度建模框架，支持MD/DFT/QM结构建模。

## 安装

```bash
pip install -e .
```

## 快速开始

```python
from modeling import ModelingSession

# 创建会话
session = ModelingSession()

# 加载用户分子
session.load_molecule("protein.pdb", name="protein")

# 构建体系
system = session.build("""
    创建8nm的立方盒子
    将protein放置在中心
    用水填充剩余空间
""")

# 验证
report = session.validate(system)
print(report)

# 导出
session.export(system, "output.pdb")
```

## 文档

详见 [docs/design.md](docs/design.md)

## 依赖

- numpy
- ase

## 许可

MIT
