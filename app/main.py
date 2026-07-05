"""
main.py — FastAPI 后端入口
============================
提供 REST API 端点，用于接收前端请求并调用求解器。

端点：
  POST /api/solve — 求解最优路径
  GET  /api/health — 健康检查
  GET  /api/default_recipes — 获取默认元素配方数据
"""

from __future__ import annotations
import os
import sys
from typing import Dict, List, Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 确保能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .hex_grid import HexMap, Cell, CellType
from .elements import ElementRegistry, DEFAULT_ASPECTS, DEFAULT_RECIPES
from .solver import HexSolver, SolveResult


# ── FastAPI 应用初始化 ──────────────────────────────────────────────────
app = FastAPI(
    title="神秘时代·六边形连线谜宫 — 路径规划求解器",
    version="2.0.0",
    description="高性能 Thaumcraft 风格六边形网格路径规划求解 API",
)

# CORS 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic 请求/响应模型 ─────────────────────────────────────────────
class SolveRequest(BaseModel):
    """求解请求体"""
    radius: int = Field(3, ge=2, le=6, description="网格半径")
    blocked: List[Dict[str, int]] = Field(
        default_factory=list,
        description="阻挡格坐标列表 [{'q': 0, 'r': 1}, ...]",
    )
    targets: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="带元素的格子列表 [{'q': 0, 'r': 1, 'element': 'ignis'}, ...]",
    )
    recipes: Dict[str, Any] = Field(
        default_factory=dict,
        description="自定义合成表 {'aspects': [...], 'recipes': {...}}",
    )
    inventory: Dict[str, int] = Field(
        default_factory=dict,
        description="玩家当前库存 {'ignis': 5, 'aer': 3, ...}",
    )


class SolveResponse(BaseModel):
    """求解响应体"""
    success: bool
    path_nodes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="路径节点列表 [{q, r, element}, ...]",
    )
    edges: List[List[List[int]]] = Field(
        default_factory=list,
        description="连线拓扑 [[[q1,r1], [q2,r2]], ...]",
    )
    total_cost: int = 0
    total_cells: int = 0
    unreachable_targets: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="无法连通的节点列表",
    )
    message: str = ""


# ── 全局元素注册表 ──────────────────────────────────────────────────────
_default_registry = ElementRegistry()
_default_registry.load_recipes(DEFAULT_ASPECTS, DEFAULT_RECIPES)


# ── API 端点 ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "thaumcraft-hex-solver",
        "version": "2.0.0",
    }


@app.get("/api/default_recipes")
async def get_default_recipes():
    """获取默认元素配方数据"""
    return {
        "aspects": DEFAULT_ASPECTS,
        "recipes": DEFAULT_RECIPES,
        "base_aspects": _default_registry.base_aspects,
        "composite_aspects": _default_registry.composite_aspects,
    }


@app.post("/api/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    """
    核心求解端点。

    接收前端发来的地图配置与库存数据，调用求解器计算最优路径。
    """
    # ── 1. 构建元素注册表 ────────────────────────────────────────────
    registry = ElementRegistry()
    if request.recipes and "aspects" in request.recipes:
        # 使用自定义合成表
        registry.load_recipes(
            request.recipes["aspects"],
            request.recipes.get("recipes", {}),
        )
    else:
        # 使用默认 Thaumcraft 元素表
        registry = _default_registry

    # ── 2. 构建地图 ──────────────────────────────────────────────────
    hex_map = HexMap(request.radius)

    # 设置阻挡格
    for b in request.blocked:
        cell = hex_map.get_cell(b.get("q", 0), b.get("r", 0))
        if cell:
            cell.cell_type = CellType.BLOCKED

    # 设置带元素的格子（求解器会连通所有带元素的格子）
    for t in request.targets:
        cell = hex_map.get_cell(t.get("q", 0), t.get("r", 0))
        if cell:
            cell.element = t.get("element")

    # ── 3. 库存降级：确保至少有 1 个基础元素兜底 ────────────────────
    inventory = dict(request.inventory)
    if not inventory:
        for base in registry.base_aspects[:3]:
            inventory[base] = 5

    # ── 4. 运行求解器 ──────────────────────────────────────────────────
    solver = HexSolver(hex_map, registry, inventory)
    result: SolveResult = solver.solve()

    # ── 6. 构建响应 ──────────────────────────────────────────────────
    return SolveResponse(
        success=result.success,
        path_nodes=[n.to_dict() for n in result.path_nodes],
        edges=[[[e[0][0], e[0][1]], [e[1][0], e[1][1]]] for e in result.edges],
        total_cost=result.total_cost,
        total_cells=result.total_cells,
        unreachable_targets=result.unreachable_targets,
        message=result.message,
    )


# ── 静态文件挂载（开发用）───────────────────────────────────────────────
# 在生产环境中应使用 nginx 等反向代理来提供静态文件
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# ── 直接启动 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
