"""
hex_grid.py — 六边形网格数据结构
===================================
采用轴向坐标系 (q, r)，提供：
- 网格生成（半径 R → 所有合法格子坐标）
- 邻居查找（6 方向固定偏移）
- 坐标序列化 / 反序列化
"""

from __future__ import annotations
from typing import List, Tuple, Set, Optional, Dict, Any

# ── 六方向邻居偏移（轴向坐标）─────────────────────────────────────────────
HEX_DIRECTIONS: List[Tuple[int, int]] = [
    (1, 0), (-1, 0),
    (0, 1), (0, -1),
    (1, -1), (-1, 1),
]

# ── 网格大小分类 ──────────────────────────────────────────────────────────
GRID_SIZES = {
    "small": 3,   # 37 cells
    "medium": 4,  # 61 cells
    "large": 5,   # 91 cells
}


def hex_neighbors(q: int, r: int) -> List[Tuple[int, int]]:
    """返回 (q, r) 的 6 个邻居坐标"""
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]


def generate_hex_grid(radius: int) -> List[Tuple[int, int]]:
    """
    生成半径为 radius 的大六边形网格的所有合法坐标。
    约束: abs(q) <= R, abs(r) <= R, abs(q + r) <= R
    """
    cells: List[Tuple[int, int]] = []
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            if abs(q + r) <= radius:
                cells.append((q, r))
    return cells


def hex_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """六边形网格曼哈顿距离（轴向坐标）"""
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


# ── Cell 类型枚举 ─────────────────────────────────────────────────────────
class CellType:
    EMPTY = "empty"           # 空白可用
    BLOCKED = "blocked"       # 走不通的阻挡格


class Cell:
    """
    单个六边形格子的运行时数据模型。
    """
    def __init__(self, q: int, r: int):
        self.q: int = q
        self.r: int = r
        self.cell_type: str = CellType.EMPTY
        self.element: Optional[str] = None   # 该格上放置的元素名称

    @property
    def coord(self) -> Tuple[int, int]:
        return (self.q, self.r)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "q": self.q,
            "r": self.r,
            "cell_type": self.cell_type,
            "element": self.element,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Cell":
        cell = cls(d["q"], d["r"])
        cell.cell_type = d.get("cell_type", CellType.EMPTY)
        cell.element = d.get("element")
        return cell


class HexMap:
    """
    管理整个六边形地图，包含所有 Cell 的访问与修改。
    """
    def __init__(self, radius: int):
        self.radius: int = radius
        self.cells: Dict[Tuple[int, int], Cell] = {}
        coords = generate_hex_grid(radius)
        for q, r in coords:
            self.cells[(q, r)] = Cell(q, r)

    def get_cell(self, q: int, r: int) -> Optional[Cell]:
        return self.cells.get((q, r))

    def exists(self, q: int, r: int) -> bool:
        return (q, r) in self.cells

    def get_neighbors(self, q: int, r: int) -> List[Cell]:
        """返回 (q, r) 在地图范围内的所有邻居 Cell"""
        result = []
        for nq, nr in hex_neighbors(q, r):
            cell = self.get_cell(nq, nr)
            if cell is not None:
                result.append(cell)
        return result

    def all_cells(self) -> List[Cell]:
        return list(self.cells.values())

    def to_dict(self) -> List[Dict[str, Any]]:
        return [cell.to_dict() for cell in self.all_cells()]

    @classmethod
    def from_dict(cls, radius: int, cells_data: List[Dict[str, Any]]) -> "HexMap":
        hm = cls(radius)
        for d in cells_data:
            key = (d["q"], d["r"])
            if key in hm.cells:
                hm.cells[key] = Cell.from_dict(d)
        return hm
