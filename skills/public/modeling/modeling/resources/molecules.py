"""
内置分子与片段库

提供常用分子和化学片段 (functional groups) 的结构。
片段通过 properties["fragment"]=True 标记，含 connection_atom 连接点信息。
"""

from __future__ import annotations
from typing import Dict, List
import numpy as np

from modeling.core.structure import Structure


class BuiltinMolecules:
    """
    内置分子与片段库

    分子：完整的分子结构 (water, methane, CO2, etc.)
    片段：带连接点的功能基团 (CH3, NO2, OH, etc.)

    片段的 properties 包含:
        fragment: True
        connection_atom: int — 与母体成键的原子索引
        formal_charge: int — 片段的形式电荷
    """

    # ========== 完整分子 ==========

    @staticmethod
    def water_tip3p() -> Structure:
        """TIP3P水分子"""
        return Structure(
            positions=np.array([
                [0.000, 0.000, 0.117],  # O
                [0.757, 0.000, -0.469],  # H
                [-0.757, 0.000, -0.469],  # H
            ]),
            symbols=['O', 'H', 'H'],
            charges=np.array([-0.834, 0.417, 0.417]),
            name="water_tip3p",
        )

    @staticmethod
    def water_spce() -> Structure:
        """SPC/E水分子"""
        return Structure(
            positions=np.array([
                [0.000, 0.000, 0.000],  # O
                [0.816, 0.577, 0.000],  # H
                [-0.816, 0.577, 0.000],  # H
            ]),
            symbols=['O', 'H', 'H'],
            charges=np.array([-0.8476, 0.4238, 0.4238]),
            name="water_spce",
        )

    @staticmethod
    def sodium_ion() -> Structure:
        """钠离子"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['Na'],
            charges=np.array([1.0]),
            name="Na+",
        )

    @staticmethod
    def chloride_ion() -> Structure:
        """氯离子"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['Cl'],
            charges=np.array([-1.0]),
            name="Cl-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    @staticmethod
    def potassium_ion() -> Structure:
        """钾离子"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['K'],
            charges=np.array([1.0]),
            name="K+",
        )

    @staticmethod
    def methane() -> Structure:
        """甲烷分子 CH4"""
        d = 1.09  # C-H键长 (Å)
        t = np.arccos(-1/3)  # 四面体角
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],  # C
                [d, 0.0, 0.0],  # H
                [d*np.cos(t), d*np.sin(t), 0.0],  # H
                [d*np.cos(t), d*np.sin(t)*np.cos(2*np.pi/3), d*np.sin(t)*np.sin(2*np.pi/3)],  # H
                [d*np.cos(t), d*np.sin(t)*np.cos(4*np.pi/3), d*np.sin(t)*np.sin(4*np.pi/3)],  # H
            ]),
            symbols=['C', 'H', 'H', 'H', 'H'],
            name="methane",
        )

    @staticmethod
    def ethane() -> Structure:
        """乙烷分子 C2H6"""
        # C-C along x, staggered conformation
        cc = 1.54  # C-C键长
        ch = 1.09  # C-H键长
        angle = np.radians(109.47)  # 四面体角
        sin_a = np.sin(angle)
        cos_a = np.cos(angle)
        return Structure(
            positions=np.array([
                [-cc/2, 0.0, 0.0],  # C1
                [cc/2, 0.0, 0.0],   # C2
                [-cc/2 + ch*cos_a, ch*sin_a, 0.0],  # H on C1
                [-cc/2 + ch*cos_a, ch*sin_a*np.cos(2*np.pi/3), ch*sin_a*np.sin(2*np.pi/3)],
                [-cc/2 + ch*cos_a, ch*sin_a*np.cos(4*np.pi/3), ch*sin_a*np.sin(4*np.pi/3)],
                [cc/2 - ch*cos_a, -ch*sin_a, 0.0],  # H on C2
                [cc/2 - ch*cos_a, -ch*sin_a*np.cos(2*np.pi/3), -ch*sin_a*np.sin(2*np.pi/3)],
                [cc/2 - ch*cos_a, -ch*sin_a*np.cos(4*np.pi/3), -ch*sin_a*np.sin(4*np.pi/3)],
            ]),
            symbols=['C', 'C', 'H', 'H', 'H', 'H', 'H', 'H'],
            name="ethane",
        )

    @staticmethod
    def ethanol() -> Structure:
        """乙醇分子 CH3CH2OH"""
        return Structure(
            positions=np.array([
                [0.000, 0.000, 0.000],  # C1 (CH3)
                [1.540, 0.000, 0.000],  # C2 (CH2)
                [2.120, 1.210, 0.000],  # O
                [2.920, 1.210, 0.600],  # H (OH)
                [-0.360, -0.510, 0.890],  # H
                [-0.360, -0.510, -0.890],  # H
                [-0.360, 1.020, 0.000],   # H
                [1.900, -0.510, 0.890],   # H
                [1.900, -0.510, -0.890],  # H
            ]),
            symbols=['C', 'C', 'O', 'H', 'H', 'H', 'H', 'H', 'H'],
            name="ethanol",
        )

    @staticmethod
    def carbon_monoxide() -> Structure:
        """一氧化碳 CO"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],     # C
                [1.128, 0.0, 0.0],   # O
            ]),
            symbols=['C', 'O'],
            name="CO",
        )

    @staticmethod
    def carbon_dioxide() -> Structure:
        """二氧化碳 CO2"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],      # C
                [-1.160, 0.0, 0.0],   # O
                [1.160, 0.0, 0.0],    # O
            ]),
            symbols=['C', 'O', 'O'],
            name="CO2",
        )

    @staticmethod
    def ammonia() -> Structure:
        """氨分子 NH3"""
        nh = 1.012  # N-H键长
        angle = np.radians(107.8)  # H-N-H角
        # 金字塔形，N在顶部
        h_z = -nh * np.cos(np.radians(67.1))
        h_r = nh * np.sin(np.radians(67.1))
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                               # N
                [h_r, 0.0, h_z],                                # H
                [h_r*np.cos(2*np.pi/3), h_r*np.sin(2*np.pi/3), h_z],  # H
                [h_r*np.cos(4*np.pi/3), h_r*np.sin(4*np.pi/3), h_z],  # H
            ]),
            symbols=['N', 'H', 'H', 'H'],
            name="NH3",
        )

    @staticmethod
    def hydrogen() -> Structure:
        """氢分子 H2"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],
                [0.74, 0.0, 0.0],
            ]),
            symbols=['H', 'H'],
            name="H2",
        )

    @staticmethod
    def nitrogen() -> Structure:
        """氮分子 N2"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],
                [1.098, 0.0, 0.0],
            ]),
            symbols=['N', 'N'],
            name="N2",
        )

    @staticmethod
    def oxygen() -> Structure:
        """氧分子 O2"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],
                [1.208, 0.0, 0.0],
            ]),
            symbols=['O', 'O'],
            name="O2",
        )

    @staticmethod
    def benzene() -> Structure:
        """苯分子 C6H6"""
        cc = 1.40  # C-C键长
        ch = 1.09  # C-H键长
        positions = []
        symbols = []
        for i in range(6):
            theta = i * np.pi / 3
            # 碳原子在正六边形顶点
            positions.append([cc * np.cos(theta), cc * np.sin(theta), 0.0])
            symbols.append('C')
        for i in range(6):
            theta = i * np.pi / 3
            r = cc + ch
            positions.append([r * np.cos(theta), r * np.sin(theta), 0.0])
            symbols.append('H')
        return Structure(
            positions=np.array(positions),
            symbols=symbols,
            name="benzene",
        )

    # ========== 离子 ==========

    @staticmethod
    def fluoride_ion() -> Structure:
        """氟离子 F-"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['F'],
            charges=np.array([-1.0]),
            name="F-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    @staticmethod
    def bromide_ion() -> Structure:
        """溴离子 Br-"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['Br'],
            charges=np.array([-1.0]),
            name="Br-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    @staticmethod
    def iodide_ion() -> Structure:
        """碘离子 I-"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['I'],
            charges=np.array([-1.0]),
            name="I-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    @staticmethod
    def hydroxide_ion() -> Structure:
        """氢氧根 OH-"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],
                [0.96, 0.0, 0.0],
            ]),
            symbols=['O', 'H'],
            charges=np.array([-1.4, 0.4]),
            name="OH-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    @staticmethod
    def hydroperoxide_ion() -> Structure:
        """过氧氢根 OOH-"""
        oo = 1.48
        oh = 0.97
        angle = np.radians(100.0)  # O-O-H angle at O2
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                                 # O1
                [oo, 0.0, 0.0],                                   # O2
                [oo - oh*np.cos(angle), oh*np.sin(angle), 0.0],   # H
            ]),
            symbols=['O', 'O', 'H'],
            name="OOH-",
            properties={"formal_charge": -1, "connection_atom": 0},
        )

    # ========== 化学片段 (Fragments) ==========

    @staticmethod
    def methyl() -> Structure:
        """甲基片段 -CH3, 连接点为 C(idx=0)"""
        ch = 1.09
        t = np.arccos(-1/3)
        # 3个H朝-x方向分布，连接方向为+x
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],  # C (连接点)
                [ch*np.cos(t), ch*np.sin(t), 0.0],
                [ch*np.cos(t), ch*np.sin(t)*np.cos(2*np.pi/3), ch*np.sin(t)*np.sin(2*np.pi/3)],
                [ch*np.cos(t), ch*np.sin(t)*np.cos(4*np.pi/3), ch*np.sin(t)*np.sin(4*np.pi/3)],
            ]),
            symbols=['C', 'H', 'H', 'H'],
            name="CH3",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def nitro() -> Structure:
        """硝基片段 -NO2, 连接点为 N(idx=0)"""
        no = 1.22  # N-O键长
        angle = np.radians(125.0)  # O-N-O角的一半约62.5度
        half_angle = angle / 2
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                                  # N (连接点)
                [no*np.cos(half_angle), no*np.sin(half_angle), 0.0],   # O
                [no*np.cos(half_angle), -no*np.sin(half_angle), 0.0],  # O
            ]),
            symbols=['N', 'O', 'O'],
            name="NO2",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def hydroxyl() -> Structure:
        """羟基片段 -OH, 连接点为 O(idx=0)"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],     # O (连接点)
                [0.96, 0.0, 0.0],    # H
            ]),
            symbols=['O', 'H'],
            name="OH",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def hydroperoxy() -> Structure:
        """过氧基片段 -OOH, 连接点为 O1(idx=0)"""
        oo = 1.48
        oh = 0.97
        angle = np.radians(100.0)  # O-O-H angle at O2
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                                 # O1 (连接点)
                [oo, 0.0, 0.0],                                   # O2
                [oo - oh*np.cos(angle), oh*np.sin(angle), 0.0],   # H
            ]),
            symbols=['O', 'O', 'H'],
            name="OOH",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def amino() -> Structure:
        """氨基片段 -NH2, 连接点为 N(idx=0)"""
        nh = 1.01
        angle = np.radians(106.0)
        half = angle / 2
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                              # N (连接点)
                [nh*np.cos(half), nh*np.sin(half), 0.0],       # H
                [nh*np.cos(half), -nh*np.sin(half), 0.0],      # H
            ]),
            symbols=['N', 'H', 'H'],
            name="NH2",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def carboxyl() -> Structure:
        """羧基片段 -COOH, 连接点为 C(idx=0)"""
        # 平面结构
        co_double = 1.21  # C=O
        co_single = 1.34  # C-OH
        oh = 0.96
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],               # C (连接点)
                [co_double*np.cos(np.radians(120)), co_double*np.sin(np.radians(120)), 0.0],  # O (=O)
                [co_single, 0.0, 0.0],          # O (-OH)
                [co_single + oh, 0.0, 0.0],     # H
            ]),
            symbols=['C', 'O', 'O', 'H'],
            name="COOH",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def trifluoromethyl() -> Structure:
        """三氟甲基片段 -CF3, 连接点为 C(idx=0)"""
        cf = 1.33
        t = np.arccos(-1/3)
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],  # C (连接点)
                [cf*np.cos(t), cf*np.sin(t), 0.0],
                [cf*np.cos(t), cf*np.sin(t)*np.cos(2*np.pi/3), cf*np.sin(t)*np.sin(2*np.pi/3)],
                [cf*np.cos(t), cf*np.sin(t)*np.cos(4*np.pi/3), cf*np.sin(t)*np.sin(4*np.pi/3)],
            ]),
            symbols=['C', 'F', 'F', 'F'],
            name="CF3",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def cyano() -> Structure:
        """氰基片段 -CN, 连接点为 C(idx=0)"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],     # C (连接点)
                [1.16, 0.0, 0.0],    # N (三键)
            ]),
            symbols=['C', 'N'],
            name="CN",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def thiol() -> Structure:
        """巯基片段 -SH, 连接点为 S(idx=0)"""
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],     # S (连接点)
                [1.34, 0.0, 0.0],    # H
            ]),
            symbols=['S', 'H'],
            name="SH",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def methoxy() -> Structure:
        """甲氧基片段 -OCH3, 连接点为 O(idx=0)"""
        oc = 1.43
        ch = 1.09
        t = np.arccos(-1/3)
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],          # O (连接点)
                [oc, 0.0, 0.0],            # C
                [oc + ch, 0.0, 0.0],       # H
                [oc + ch*np.cos(t), ch*np.sin(t), 0.0],
                [oc + ch*np.cos(t), ch*np.sin(t)*np.cos(2*np.pi/3), ch*np.sin(t)*np.sin(2*np.pi/3)],
            ]),
            symbols=['O', 'C', 'H', 'H', 'H'],
            name="OCH3",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def fluorine_fragment() -> Structure:
        """氟原子片段 -F, 连接点为 F(idx=0)"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['F'],
            name="F",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def chlorine_fragment() -> Structure:
        """氯原子片段 -Cl, 连接点为 Cl(idx=0)"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['Cl'],
            name="Cl",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def bromine_fragment() -> Structure:
        """溴原子片段 -Br, 连接点为 Br(idx=0)"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['Br'],
            name="Br",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def iodine_fragment() -> Structure:
        """碘原子片段 -I, 连接点为 I(idx=0)"""
        return Structure(
            positions=np.array([[0.0, 0.0, 0.0]]),
            symbols=['I'],
            name="I",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def phenyl() -> Structure:
        """苯基片段 -C6H5, 连接点为 C1(idx=0)"""
        cc = 1.40
        ch = 1.09
        positions = []
        symbols = []
        # 6个碳在正六边形
        for i in range(6):
            theta = i * np.pi / 3
            positions.append([cc * np.cos(theta), cc * np.sin(theta), 0.0])
            symbols.append('C')
        # 5个氢 (idx=1-5的碳上各一个H, idx=0为连接点无H)
        for i in range(1, 6):
            theta = i * np.pi / 3
            r = cc + ch
            positions.append([r * np.cos(theta), r * np.sin(theta), 0.0])
            symbols.append('H')
        return Structure(
            positions=np.array(positions),
            symbols=symbols,
            name="C6H5",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def vinyl() -> Structure:
        """乙烯基片段 -CH=CH2, 连接点为 C1(idx=0)"""
        cc = 1.34  # C=C双键
        ch = 1.09
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                  # C1 (连接点)
                [cc, 0.0, 0.0],                    # C2
                [cc + ch*np.cos(np.radians(120)), ch*np.sin(np.radians(120)), 0.0],  # H on C2
                [cc + ch, 0.0, 0.0],               # H on C2
                [ch*np.cos(np.radians(120)), -ch*np.sin(np.radians(120)), 0.0],      # H on C1
            ]),
            symbols=['C', 'C', 'H', 'H', 'H'],
            name="vinyl",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    @staticmethod
    def acetyl() -> Structure:
        """乙酰基片段 -COCH3, 连接点为 C1(idx=0)"""
        co = 1.21   # C=O
        cc = 1.52   # C-C
        ch = 1.09
        t = np.arccos(-1/3)
        return Structure(
            positions=np.array([
                [0.0, 0.0, 0.0],                   # C1 (连接点, C=O)
                [co*np.cos(np.radians(120)), co*np.sin(np.radians(120)), 0.0],  # O
                [cc, 0.0, 0.0],                     # C2 (CH3)
                [cc + ch, 0.0, 0.0],                # H
                [cc + ch*np.cos(t), ch*np.sin(t), 0.0],
                [cc + ch*np.cos(t), ch*np.sin(t)*np.cos(2*np.pi/3), ch*np.sin(t)*np.sin(2*np.pi/3)],
            ]),
            symbols=['C', 'O', 'C', 'H', 'H', 'H'],
            name="acetyl",
            properties={"fragment": True, "connection_atom": 0, "formal_charge": 0},
        )

    # ========== 名称映射 ==========

    _MOLECULES: Dict[str, callable] = {
        # 水
        'water': water_tip3p,
        'water_tip3p': water_tip3p,
        'h2o': water_tip3p,
        'water_spce': water_spce,
        # 阳离子
        'na': sodium_ion,
        'na+': sodium_ion,
        'sodium': sodium_ion,
        'k': potassium_ion,
        'k+': potassium_ion,
        'potassium': potassium_ion,
        # 阴离子
        'cl-': chloride_ion,
        'chloride': chloride_ion,
        'f-': fluoride_ion,
        'fluoride': fluoride_ion,
        'br-': bromide_ion,
        'bromide': bromide_ion,
        'i-': iodide_ion,
        'iodide': iodide_ion,
        'oh-': hydroxide_ion,
        'hydroxide': hydroxide_ion,
        'ooh-': hydroperoxide_ion,
        'hydroperoxide': hydroperoxide_ion,
        # 小分子
        'methane': methane,
        'ch4': methane,
        'ethane': ethane,
        'c2h6': ethane,
        'ethanol': ethanol,
        'c2h5oh': ethanol,
        'co': carbon_monoxide,
        'carbon_monoxide': carbon_monoxide,
        'co2': carbon_dioxide,
        'carbon_dioxide': carbon_dioxide,
        'nh3': ammonia,
        'ammonia': ammonia,
        'h2': hydrogen,
        'hydrogen': hydrogen,
        'n2': nitrogen,
        'nitrogen_molecule': nitrogen,
        'o2': oxygen,
        'oxygen_molecule': oxygen,
        'benzene': benzene,
        'c6h6': benzene,
        # 片段 (fragments)
        'ch3': methyl,
        'methyl': methyl,
        'no2': nitro,
        'nitro': nitro,
        'oh': hydroxyl,
        'hydroxyl': hydroxyl,
        'ooh': hydroperoxy,
        'hydroperoxy': hydroperoxy,
        'nh2': amino,
        'amino': amino,
        'cooh': carboxyl,
        'carboxyl': carboxyl,
        'cf3': trifluoromethyl,
        'trifluoromethyl': trifluoromethyl,
        'cn': cyano,
        'cyano': cyano,
        'sh': thiol,
        'thiol': thiol,
        'och3': methoxy,
        'methoxy': methoxy,
        'f_fragment': fluorine_fragment,
        'cl_fragment': chlorine_fragment,
        'br_fragment': bromine_fragment,
        'i_fragment': iodine_fragment,
        'phenyl': phenyl,
        'c6h5': phenyl,
        'vinyl': vinyl,
        'ch=ch2': vinyl,
        'acetyl': acetyl,
        'coch3': acetyl,
    }

    @classmethod
    def get(cls, name: str) -> Structure:
        """
        获取内置分子或片段

        Args:
            name: 名称 (不区分大小写)

        Returns:
            Structure对象

        Raises:
            KeyError: 未找到
        """
        name_lower = name.lower()
        if name_lower not in cls._MOLECULES:
            available = sorted(set(cls._MOLECULES.keys()))
            raise KeyError(f"未找到 '{name}'。可用: {available}")

        factory = cls._MOLECULES[name_lower]
        if isinstance(factory, staticmethod):
            factory = factory.__func__
        return factory()

    @classmethod
    def get_fragment(cls, name: str) -> Structure:
        """
        获取片段（验证 fragment=True）

        Args:
            name: 片段名称

        Returns:
            带 fragment 标记的 Structure

        Raises:
            KeyError: 未找到
            ValueError: 不是片段
        """
        structure = cls.get(name)
        if not structure.properties.get("fragment", False):
            raise ValueError(f"'{name}' 不是片段。请使用 get() 获取完整分子。")
        return structure

    @classmethod
    def list_available(cls) -> List[str]:
        """列出所有可用名称"""
        return sorted(set(cls._MOLECULES.keys()))

    @classmethod
    def list_fragments(cls) -> List[str]:
        """列出所有可用片段名称"""
        fragments = []
        seen = set()
        for name, factory in cls._MOLECULES.items():
            if name in seen:
                continue
            try:
                if isinstance(factory, staticmethod):
                    factory = factory.__func__
                s = factory()
                if s.properties.get("fragment", False):
                    fragments.append(name)
                    seen.add(name)
            except Exception:
                pass
        return sorted(fragments)

    @classmethod
    def list_molecules(cls) -> List[str]:
        """列出所有可用完整分子名称（不含片段）"""
        molecules = []
        seen = set()
        for name, factory in cls._MOLECULES.items():
            if name in seen:
                continue
            try:
                if isinstance(factory, staticmethod):
                    factory = factory.__func__
                s = factory()
                if not s.properties.get("fragment", False):
                    molecules.append(name)
                    seen.add(name)
            except Exception:
                pass
        return sorted(molecules)
