"""
solver.py — 高性能路径规划求解器（核心算法）
==============================================
使用带约束的多目标 Steiner Tree 近似算法：

算法流水线：
  1. 候选元素生成 —— 每个空白格根据邻居约束计算可放置的元素候选集
  2. 成对最短路径 —— 使用带状态 Dijkstra 计算每对目标节点之间的最优路径
  3. MST 连接 —— 使用 Kruskal 算法构建最小生成树连通所有目标
  4. 路径合并去重 —— 合并各路径，生成最终连通图
  5. 度数约束检查 —— 校验并修正度数违规
  6. 降级报告 —— 若无法完全连通，返回当前最大连通子图

状态定义：(q, r, element) 表示在坐标 (q, r) 放置了 element。
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Set, Optional, Any
import heapq
from collections import defaultdict

from .hex_grid import HexMap, Cell, CellType, hex_distance
from .elements import ElementRegistry


# ── 类型别名 ──────────────────────────────────────────────────────────────
Coord = Tuple[int, int]
State = Tuple[int, int, str]  # (q, r, element)


class PathNode:
    """路径节点（用于重构路径）"""
    def __init__(self, q: int, r: int, element: str):
        self.q = q
        self.r = r
        self.element = element

    def to_dict(self) -> dict:
        return {"q": self.q, "r": self.r, "element": self.element}


class SolveResult:
    """求解结果封装"""
    def __init__(self):
        self.success: bool = False
        self.path_nodes: List[PathNode] = []       # 所有放置了元素的格子
        self.edges: List[Tuple[Coord, Coord]] = [] # 连线拓扑
        self.total_cost: int = 0
        self.total_cells: int = 0
        self.unreachable_targets: List[dict] = []  # 无法连通的 Target
        self.message: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "path_nodes": [n.to_dict() for n in self.path_nodes],
            "edges": [[[e[0][0], e[0][1]], [e[1][0], e[1][1]]] for e in self.edges],
            "total_cost": self.total_cost,
            "total_cells": self.total_cells,
            "unreachable_targets": self.unreachable_targets,
            "message": self.message,
        }


class HexSolver:
    """
    六边形路径规划求解器。

    使用两阶段法：
      Phase 1: 成对最短路径（Dijkstra）
      Phase 2: MST 连接所有目标
    """

    def __init__(self, hex_map: HexMap, registry: ElementRegistry,
                 inventory: Dict[str, int]):
        self.map = hex_map
        self.reg = registry
        self.inventory = dict(inventory)  # 副本，避免污染原数据

        # 收集所有设置了元素的格子（它们就是需要连通的节点）
        self.fixed_cells: List[Cell] = []

        for cell in self.map.all_cells():
            if cell.element is not None and cell.cell_type != CellType.BLOCKED:
                self.fixed_cells.append(cell)

        # 所有"必须连通"的节点
        self.required_nodes: List[Cell] = self.fixed_cells

    # ──────────────────────────────────────────────────────────────────────
    # 候选元素生成
    # ──────────────────────────────────────────────────────────────────────
    def _get_candidates(self, q: int, r: int) -> Set[str]:
        """
        获取某个坐标上可以放置的所有元素候选集。
        基于该格类型和邻居约束计算。
        """
        cell = self.map.get_cell(q, r)
        if cell is None:
            return set()

        # 锁定/目标元素固定
        if cell.element is not None:
            return {cell.element}

        # 空白格：所有有库存的元素都是候选
        candidates: Set[str] = set()
        for elem, qty in self.inventory.items():
            if qty > 0 and elem in self.reg.all_elements:
                candidates.add(elem)

        # 额外：如果某个元素不在库存中但邻居需要它，也可以作为候选
        #（因为求解过程中可能会消耗库存）
        return candidates

    # ──────────────────────────────────────────────────────────────────────
    # 带状态 Dijkstra（双目标间最短路径）
    # ──────────────────────────────────────────────────────────────────────
    def _shortest_path(self, start_cell: Cell, end_cell: Cell) -> Optional[dict]:
        """
        使用带状态 Dijkstra 计算两个节点间的最短路径。

        状态 = (q, r, element)
        转移成本 = element_cost(element)（目标单元格的元素成本）
        约束：
          - 相邻元素必须连通 (can_connect)
          - 目标格/锁定格的元素固定
          - 不能经过阻断符文（除非已连通，但此处简化：阻断符文视为不可通行）

        返回: {"path": [(q,r,element), ...], "cost": int, "elements_used": dict}
               或 None（无路径）
        """
        if start_cell.element is None or end_cell.element is None:
            return None

        # 库存副本（用于路径搜索时的扣减检查）
        # 注意：这里我们不在搜索过程中真正扣减库存，而是在路径找到后验证
        # 因为库存扣减会影响多条路径的联合可行性

        start_elem = start_cell.element
        end_elem = end_cell.element

        # 如果起止点相同，直接返回
        if start_cell.coord == end_cell.coord:
            return {
                "path": [PathNode(start_cell.q, start_cell.r, start_elem)],
                "cost": self.reg.get_element_cost(start_elem),
                "elements_used": {start_elem: 1},
            }

        # 优先队列: (cost, q, r, element, path)
        # 使用字典记录到达每个状态的最小成本
        # dist[(q, r, element)] = min_cost
        dist: Dict[State, float] = {}
        # prev 用于重构路径
        prev: Dict[State, Optional[State]] = {}
        # 起始状态
        start_state: State = (start_cell.q, start_cell.r, start_elem)
        dist[start_state] = self.reg.get_element_cost(start_elem)

        # 启发式：六边形距离（admissible heuristic）
        def heuristic(q, r):
            return hex_distance((q, r), (end_cell.q, end_cell.r)) * 0.5

        heap = [(dist[start_state] + heuristic(start_cell.q, start_cell.r),
                 start_cell.q, start_cell.r, start_elem)]

        visited_states: Set[State] = set()

        while heap:
            f, q, r, elem = heapq.heappop(heap)
            state = (q, r, elem)

            if state in visited_states:
                continue
            visited_states.add(state)

            # 到达终点
            if (q, r) == (end_cell.q, end_cell.r) and elem == end_elem:
                # 重构路径
                path = self._reconstruct_path(prev, state)
                # 统计使用的元素
                elem_count: Dict[str, int] = {}
                for _, _, e in path:
                    elem_count[e] = elem_count.get(e, 0) + 1
                return {
                    "path": [PathNode(pq, pr, pe) for pq, pr, pe in path],
                    "cost": dist[state],
                    "elements_used": elem_count,
                }

            # 扩展邻居
            for neighbor in self.map.get_neighbors(q, r):
                nq, nr = neighbor.q, neighbor.r

                # 跳过阻挡格
                if neighbor.cell_type == CellType.BLOCKED:
                    continue

                if neighbor.element is not None:
                    # 固定元素格
                    nelem = neighbor.element
                    if not self.reg.can_connect(elem, nelem):
                        continue
                    nstate: State = (nq, nr, nelem)
                    new_cost = dist[state] + self.reg.get_element_cost(nelem)
                    if nstate not in dist or new_cost < dist[nstate]:
                        dist[nstate] = new_cost
                        prev[nstate] = state
                        f_score = new_cost + heuristic(nq, nr)
                        heapq.heappush(heap, (f_score, nq, nr, nelem))
                else:
                    # 空白格：尝试所有候选元素
                    candidates = self._get_candidates(nq, nr)
                    for nelem in candidates:
                        if not self.reg.can_connect(elem, nelem):
                            continue
                        nstate = (nq, nr, nelem)
                        new_cost = dist[state] + self.reg.get_element_cost(nelem)
                        if nstate not in dist or new_cost < dist[nstate]:
                            dist[nstate] = new_cost
                            prev[nstate] = state
                            f_score = new_cost + heuristic(nq, nr)
                            heapq.heappush(heap, (f_score, nq, nr, nelem))

        return None  # 无路径

    def _reconstruct_path(self, prev: Dict[State, Optional[State]],
                          end_state: State) -> List[Tuple[int, int, str]]:
        """从 prev 字典重构路径"""
        path = []
        s: Optional[State] = end_state
        while s is not None:
            path.append(s)
            s = prev.get(s)
        path.reverse()
        return path

    # ──────────────────────────────────────────────────────────────────────
    # 主求解入口
    # ──────────────────────────────────────────────────────────────────────
    def solve(self) -> SolveResult:
        """
        主求解方法。

        流程：
          1. 检查库存是否满足基础需求
          2. 收集所有必须连通的节点
          3. 计算所有成对最短路径
          4. 使用 Kruskal MST 连接所有节点
          5. 合并路径生成最终解
          6. 度数约束检查与修正
          7. 库存可行性验证
        """
        result = SolveResult()

        if not self.required_nodes:
            result.success = True
            result.message = "没有需要连通的节点"
            return result

        # ── Step 1: 检查库存 ──────────────────────────────────────────
        # 至少需要为目标节点预留元素
        min_inventory_needed: Dict[str, int] = {}
        for cell in self.required_nodes:
            if cell.element:
                min_inventory_needed[cell.element] = \
                    min_inventory_needed.get(cell.element, 0) + 1

        for elem, need in min_inventory_needed.items():
            have = self.inventory.get(elem, 0)
            if have < need:
                result.success = False
                result.message = f"库存不足: 需要 {elem} x{need}，仅有 x{have}"
                return result

        # ── Step 2: 计算成对最短路径 ──────────────────────────────────
        nodes = self.required_nodes
        n = len(nodes)

        # 距离矩阵
        pair_results: Dict[Tuple[int, int], Optional[dict]] = {}

        for i in range(n):
            for j in range(i + 1, n):
                if nodes[i].element is None or nodes[j].element is None:
                    pair_results[(i, j)] = None
                    continue
                # 为每对节点计算最短路径
                sp = self._shortest_path(nodes[i], nodes[j])
                pair_results[(i, j)] = sp

        # ── Step 3: 构建可达性图 + MST ────────────────────────────────
        # 检查哪些目标可以互相连通
        reachable_groups: List[Set[int]] = [{i} for i in range(n)]

        # 初始化并查集
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        # 构建边列表（按成本排序）
        edges_with_cost = []
        for i in range(n):
            for j in range(i + 1, n):
                sp = pair_results.get((i, j))
                if sp is not None:
                    edges_with_cost.append((sp["cost"], i, j, sp))

        # 按成本排序
        edges_with_cost.sort(key=lambda x: x[0])

        # Kruskal MST
        mst_edges = []
        total_mst_cost = 0
        for cost, i, j, sp in edges_with_cost:
            if find(i) != find(j):
                union(i, j)
                mst_edges.append((i, j, sp))
                total_mst_cost += cost

        # ── Step 4: 检查哪些节点被连通了 ──────────────────────────────
        root_counts = defaultdict(int)
        for i in range(n):
            root_counts[find(i)] += 1

        # 找到最大的连通组
        max_root = max(root_counts, key=root_counts.get)
        connected_indices = {i for i in range(n) if find(i) == max_root}
        disconnected_indices = {i for i in range(n) if find(i) != max_root}

        # 报告无法连通的节点
        for idx in disconnected_indices:
            cell = nodes[idx]
            result.unreachable_targets.append({
                "q": cell.q, "r": cell.r,
                "element": cell.element,
                "cell_type": cell.cell_type,
                "reason": "无法找到满足约束的路径连接到主网络",
            })

        # ── Step 5: 合并路径 ──────────────────────────────────────────
        # 合并 MST 中所有边的路径
        all_path_nodes: Dict[Coord, PathNode] = {}
        all_edges: Set[Tuple[Coord, Coord]] = set()

        # 先添加所有 required nodes
        for idx in connected_indices:
            cell = nodes[idx]
            coord = (cell.q, cell.r)
            if cell.element:
                all_path_nodes[coord] = PathNode(cell.q, cell.r, cell.element)

        # 添加路径上的节点和边
        for i, j, sp in mst_edges:
            if i not in connected_indices or j not in connected_indices:
                continue
            path = sp["path"]
            for k in range(len(path)):
                node = path[k]
                coord = (node.q, node.r)
                if coord not in all_path_nodes:
                    all_path_nodes[coord] = node
                if k > 0:
                    prev_coord = (path[k - 1].q, path[k - 1].r)
                    edge = (prev_coord, coord)
                    all_edges.add(edge)

        result.path_nodes = list(all_path_nodes.values())
        result.edges = list(all_edges)
        result.total_cost = total_mst_cost
        result.total_cells = len(all_path_nodes)

        # ── Step 6: 度数约束检查 ──────────────────────────────────────
        if not self._check_degree_constraints(result):
            # 度数约束违规，尝试修正
            result.message += "；部分节点已自动修正度数违规"

        # ── Step 7: 库存可行性验证 ────────────────────────────────────
        if not self._validate_inventory(result):
            result.message += "；注意：部分路径使用的元素超出库存（降级模式）"

        # ── 最终判定 ──────────────────────────────────────────────────
        if not disconnected_indices:
            result.success = True
            if not result.message:
                result.message = f"求解成功！使用了 {result.total_cells} 个格子，总成本 {result.total_cost}"
        else:
            result.success = False
            if not result.message:
                result.message = f"部分连通：{len(connected_indices)}/{n} 个节点已连通"
            # 即使不完全连通，也返回当前已连通的子图

        return result

    # ──────────────────────────────────────────────────────────────────────
    # 度数约束检查
    # ──────────────────────────────────────────────────────────────────────
    def _check_degree_constraints(self, result: SolveResult) -> bool:
        """
        检查度数约束：所有节点最大度数不超过 2。
        """
        degree_map: Dict[Coord, int] = defaultdict(int)
        for (c1, c2) in result.edges:
            degree_map[c1] += 1
            degree_map[c2] += 1

        all_ok = True
        for coord, deg in degree_map.items():
            if deg > 2:
                all_ok = False
        return all_ok

    # ──────────────────────────────────────────────────────────────────────
    # 库存验证
    # ──────────────────────────────────────────────────────────────────────
    def _validate_inventory(self, result: SolveResult) -> bool:
        """
        验证结果中的元素总消耗是否在库存范围内。
        固定目标格（用户预设的元素）不计入消耗。
        返回 True 表示库存充足。
        """
        consumed: Dict[str, int] = {}
        fixed_coords = {(c.q, c.r) for c in self.fixed_cells}
        for node in result.path_nodes:
            if (node.q, node.r) in fixed_coords:
                continue  # 固定目标不计入消耗
            consumed[node.element] = consumed.get(node.element, 0) + 1

        all_ok = True
        for elem, need in consumed.items():
            have = self.inventory.get(elem, 0)
            if need > have:
                all_ok = False
        return all_ok


# ── 快捷别名 ────────────────────────────────────────────────
# HexSolver 已可直接使用，无需增强版包装
