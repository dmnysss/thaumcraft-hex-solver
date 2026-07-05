# 神秘时代 · 六边形连线谜宫 — 路径规划求解工具

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Frontend-Vue.js-4FC08D)](https://vuejs.org/)
[![Thaumcraft](https://img.shields.io/badge/Game-Thaumcraft%204.2.3.5a-6441A5)](https://ftb.fandom.com/wiki/Thaumcraft)

基于 Thaumcraft 4.2.3.5a 的神秘时代风格六边形连线谜宫高性能路径规划求解工具。采用严格前后端分离架构，后端使用 Python FastAPI 提供纯 API 服务，前端为独立单文件 HTML 页面。

## 功能特性

- 🧠 **智能寻路** — 基于图论 MST（最小生成树）的多目标最优路径算法，自动连通玩家放置的所有元素节点
- 🔮 **官方配方** — 内置 Thaumcraft 4.2.3.5a 完整 48 种元素（6 基础 + 42 复合）合成表
- 📦 **库存管理** — 右侧库存栏实时调整每种元素的可用数量，求解自动扣减
- 🖱️ **直观交互** — 左键切换阻挡、右键快捷选元素、搜索框即时过滤
- 🎨 **视觉反馈** — 六边形网格 Canvas 渲染，彩色图标 + 虚线圆圈标记路径，悬停显示中文/英文名
- 🔧 **配方编辑器** — 左侧面板支持新增/删除自定义配方，支持导入/导出 JSON
- 📐 **多尺寸支持** — 小盘(R=3/37格)、中盘(R=4/61格)、大盘(R=5/91格)

## 快速开始

### 前置依赖

- Python ≥ 3.9
- pip

### 安装 & 启动

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/thaumcraft-hex-solver.git
cd thaumcraft-hex-solver

# 安装依赖
pip install -r requirements.txt

# 启动后端服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开浏览器访问 `http://localhost:8000` 即可使用。

## 项目结构

```
thaumcraft-hex-solver/
├── app/
│   ├── __init__.py          # 包初始化
│   ├── hex_grid.py          # 六边形网格（轴向坐标 q,r）
│   ├── elements.py          # 元素系统（合成表、连通判定）
│   ├── solver.py            # 核心求解器（Dijkstra + MST）
│   └── main.py              # FastAPI 后端入口
├── static/
│   └── index.html           # 单文件前端（Vue3 + Canvas）
├── requirements.txt         # Python 依赖
└── README.md
```

## API 文档

### `POST /api/solve`

核心求解接口。

**请求体：**
```json
{
  "radius": 3,
  "blocked": [{"q": 0, "r": 1}],
  "targets": [{"q": 0, "r": 0, "element": "ignis"}],
  "recipes": {
    "aspects": ["ignis", "aer", "lux", ...],
    "recipes": {"lux": ["ignis", "aer"], ...}
  },
  "inventory": {"ignis": 5, "aer": 3}
}
```

**响应：**
```json
{
  "success": true,
  "path_nodes": [{"q": 0, "r": 1, "element": "ignis"}, ...],
  "edges": [[[0,0], [1,-1]], ...],
  "total_cost": 6,
  "total_cells": 4,
  "unreachable_targets": [],
  "message": "求解成功！使用了 4 个格子，总成本 6"
}
```

### `GET /api/default_recipes`

获取内置的 Thaumcraft 4.2.3.5a 完整合成表。

### `GET /api/health`

健康检查。

## 核心算法

### 网格模型

采用轴向坐标系 (q, r)，六方向邻居偏移固定为：
```
(+1,0), (-1,0), (0,+1), (0,-1), (+1,-1), (-1,+1)
```

### 元素连通规则

相邻格子 A 和 B 能够连通，当且仅当存在直接合成原料关系：
- A 是 B 的合成原料，或 B 是 A 的合成原料
- 相同元素不能连通

### 路径搜索

1. **带状态 Dijkstra**：状态 = (q, r, element)，在空白格枚举所有候选元素
2. **Kruskal MST**：计算所有目标对的成对最短路径，构建最小生成树连接所有节点
3. **约束检查**：度数限制（≤2）、库存消耗验证

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.9+, FastAPI, Uvicorn, Pydantic |
| 前端 | Vue.js 3 (CDN), HTML5 Canvas |
| 算法 | Dijkstra, Kruskal MST, 状态图搜索 |

## 许可证

MIT License
