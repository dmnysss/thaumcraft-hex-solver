"""
elements.py — 元素系统与合成规则引擎
======================================
负责：
1. 基础/复合元素的定义与管理
2. 合成表 (recipes) 的解析与验证
3. 元素连通性判定（核心规则：相邻两格元素必须满足合成关系）
4. 元素成本计算（基础元素=1，复合元素=2）
"""

from __future__ import annotations
from typing import Dict, List, Set, Optional, Tuple


class ElementRegistry:
    """
    元素注册表：管理所有元素名称、合成关系、连通性查询。
    支持 JSON 动态导入。

    连通规则：
      相邻格子 A（元素 ea）和 B（元素 eb）能够连通，当且仅当：
        - ea == eb（相同元素），或者
        - ea 是 eb 的直接合成原料之一（ea in recipes[eb]），或者
        - eb 是 ea 的直接合成原料之一（eb in recipes[ea]）
    """

    def __init__(self):
        # 基础元素集合（没有配方的元素即为基础元素）
        self.base_aspects: List[str] = []
        # 复合元素集合
        self.composite_aspects: List[str] = []
        # 所有元素的完整列表
        self.all_elements: List[str] = []
        # 合成配方: {"复合元素": ["原料1", "原料2"]}
        self.recipes: Dict[str, List[str]] = {}
        # 反向映射: {"原料": set("使用该原料的复合元素")}
        self.reverse_recipes: Dict[str, Set[str]] = {}
        # 每个元素的合成树深度（基础元素=0）
        self.element_depth: Dict[str, int] = {}

    def load_recipes(self, aspects: List[str],
                     recipes: Dict[str, List[str]]) -> None:
        """
        从动态配置加载元素与配方。

        参数:
          aspects: 所有元素的列表（含基础+复合）
          recipes: 复合元素→[原料1, 原料2] 的字典

        注意：基础元素不出现在 recipes 的 key 中。
        """
        self.recipes = dict(recipes)
        self.all_elements = list(aspects)

        # 构建反向映射
        self.reverse_recipes = {}
        for child, parents in recipes.items():
            for p in parents:
                self.reverse_recipes.setdefault(p, set()).add(child)

        # 区分基础/复合元素
        recipe_keys = set(recipes.keys())
        self.composite_aspects = [e for e in aspects if e in recipe_keys]
        self.base_aspects = [e for e in aspects if e not in recipe_keys]

        # 计算合成深度（拓扑排序 / BFS）
        self._compute_depths()

    def _compute_depths(self) -> None:
        """计算每个元素的合成树深度（基础元素=0）。"""
        depth: Dict[str, int] = {}
        # 基础元素深度为 0
        for e in self.base_aspects:
            depth[e] = 0
        # 迭代计算复合元素深度（最多迭代 len(aspects) 轮）
        changed = True
        while changed:
            changed = False
            for child, parents in self.recipes.items():
                if child in depth:
                    continue
                if all(p in depth for p in parents):
                    depth[child] = max(depth[p] for p in parents) + 1
                    changed = True
        self.element_depth = depth

    def can_connect(self, ea: Optional[str], eb: Optional[str]) -> bool:
        """
        判断元素 ea 和 eb 是否满足连通规则。

        两个相邻格子能够连通，当且仅当：
          1. ea 是 eb 的合成原料（ea in recipes[eb]），或者
          2. eb 是 ea 的合成原料（eb in recipes[ea]）

        注意：相同元素相邻视为无效（必须存在合成原料关系）。
        """
        if ea is None or eb is None:
            return False
        if ea == eb:
            return False
        # ea → eb
        if eb in self.recipes and ea in self.recipes[eb]:
            return True
        # eb → ea
        if ea in self.recipes and eb in self.recipes[ea]:
            return True
        return False

    def is_base_element(self, element: str) -> bool:
        """判断是否为基础元素"""
        return element in self.base_aspects

    def get_element_cost(self, element: str) -> int:
        """
        获取元素成本：
          - 基础元素 = 1
          - 复合元素 = 2
        """
        return 1 if self.is_base_element(element) else 2

    def get_connectable_elements(self, element: str) -> Set[str]:
        """
        返回与给定元素可以连通的所有元素集合（不含自身）。
        """
        result: Set[str] = set()
        # element 作为原料 → 所有使用 element 合成的复合元素
        if element in self.reverse_recipes:
            result.update(self.reverse_recipes[element])
        # element 作为产物 → 其原料都可连通
        if element in self.recipes:
            result.update(self.recipes[element])
        return result

    def to_dict(self) -> dict:
        return {
            "base_aspects": self.base_aspects,
            "composite_aspects": self.composite_aspects,
            "all_elements": self.all_elements,
            "recipes": self.recipes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ElementRegistry":
        reg = cls()
        reg.load_recipes(data.get("aspects", []),
                         data.get("recipes", {}))
        return reg


# ── 默认 Thaumcraft 4.2.3.5a 元素数据 ─────────────────
# 6 大基础元素 + 42 种复合元素，共 48 种
DEFAULT_ASPECTS = [
    # 基础 (Primal)
    "aer", "terra", "ignis", "aqua", "ordo", "perditio",
    # 第一层复合
    "victus", "potentia", "lux", "motus", "vacuos",
    "tempestas", "gelum", "venenum", "vitreus", "permutatio",
    # 第二层复合
    "herba", "mortuus", "limus", "sano", "bestia",
    "vinculum", "arbor", "iter", "spiritus", "tenebrae",
    "praecantatio", "metallum", "volatus",
    # 第三层复合
    "sensus", "cognitio", "humanus", "corpus", "exanimis",
    "instrumentum", "perfodio", "messis", "fames",
    "auram", "vitium", "alienis",
    # 第四层复合
    "pannus", "telum", "tutamen", "machina", "fabrico",
    "lucrum", "meto",
]

DEFAULT_RECIPES = {
    # ── 第一层 (基础 × 基础) ───────────────────────
    "victus":       ["aqua", "terra"],
    "potentia":     ["ignis", "ordo"],
    "lux":          ["aer", "ignis"],
    "motus":        ["aer", "ordo"],
    "vacuos":       ["aer", "perditio"],
    "tempestas":    ["aer", "aqua"],
    "gelum":        ["ignis", "perditio"],
    "venenum":      ["aqua", "perditio"],
    "vitreus":      ["ordo", "terra"],
    "permutatio":   ["ordo", "perditio"],
    # ── 第二层 ─────────────────────────────────────
    "herba":        ["terra", "victus"],
    "mortuus":      ["perditio", "victus"],
    "limus":        ["aqua", "victus"],
    "sano":         ["ordo", "victus"],
    "bestia":       ["motus", "victus"],
    "vinculum":     ["motus", "perditio"],
    "arbor":        ["aer", "herba"],
    "iter":         ["motus", "terra"],
    "spiritus":     ["mortuus", "victus"],
    "tenebrae":     ["lux", "vacuos"],
    "praecantatio": ["potentia", "vacuos"],
    "metallum":     ["terra", "vitreus"],
    "volatus":      ["aer", "motus"],
    # ── 第三层 ─────────────────────────────────────
    "sensus":       ["aer", "spiritus"],
    "cognitio":     ["ignis", "spiritus"],
    "humanus":      ["bestia", "cognitio"],
    "corpus":       ["bestia", "mortuus"],
    "exanimis":     ["motus", "mortuus"],
    "instrumentum": ["humanus", "ordo"],
    "perfodio":     ["humanus", "terra"],
    "messis":       ["herba", "humanus"],
    "fames":        ["vacuos", "victus"],
    "auram":        ["aer", "praecantatio"],
    "vitium":       ["perditio", "praecantatio"],
    "alienis":      ["vacuos", "tenebrae"],
    # ── 第四层 ─────────────────────────────────────
    "pannus":       ["bestia", "instrumentum"],
    "telum":        ["ignis", "instrumentum"],
    "tutamen":      ["instrumentum", "terra"],
    "machina":      ["instrumentum", "motus"],
    "fabrico":      ["humanus", "instrumentum"],
    "lucrum":       ["fames", "humanus"],
    "meto":         ["instrumentum", "messis"],
}
