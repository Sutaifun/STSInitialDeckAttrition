# STSInitialDeckAttrition — Agent 指南

供自动化 Agent 快速理解本仓库。人类读者也可从 `docs/项目计划书.md` 进入。

---

## 1. 项目是什么

量化比较 **Slay the Spire 1（塔1）** 与 **Slay the Spire 2（塔2）** 在 **首场弱怪战斗** 中的战损差异。

- **不**接游戏本体、**不**用真实游玩日志。
- 用 wiki / 已录入 JSON 描述怪物与初始卡组，枚举 **抽牌路线** ω，在 **完美信息 + 最优出牌** 下求每场 **D(ω)** = 最小总战损。
- 核心统计：**加权** \(P(D>0)\)、加权期望战损、分布（权重 w(ω) 来自组合多重数，**非等权**）。

当前试点：**塔2 A10 · 铁甲战士 vs 海洋混混**（HP 47/48/49 各算一遍）。

---

## 2. 文档地图（先读这些）

| 路径 | 内容 |
|------|------|
| `docs/项目计划书.md` | 目标、范围、进度 |
| `docs/游戏机制.md` | 战斗规则（能量、格挡、buff、诅咒） |
| `docs/抽牌枚举协议.md` | 多重集抽牌、稳态循环、**组合权重** |
| `docs/求解器设计.md` | **权威技术方案**：DFS 打到击杀、层2 DP、剪枝、内存、输出路线图 |
| `docs/游戏数据格式.md` | JSON 目录与 schema |
| `docs/角色战斗机制.md` | 六角色首场机制、译名对照、`first_fight_model` 说明 |
| `data/sts2/pilot_ironclad_vs_seapunk.md` | 当前试点设定摘要 |
| `data/sts2/README.md` / `data/sts1/README.md` | 角色与遭遇数据索引 |

**技术决策以 `docs/求解器设计.md` 为准。**

---

## 3. 代码结构

```text
engine/
  types.py           # State, Pile, SolveResult, TurnTrace, PathResult
  load_data.py       # 从 data/sts2/*.json 构建牌组/卡牌数值/敌人意图（去硬编码）
  deck.py            # 多重集 Pile、组合抽牌、IRONCLAD_A10_DECK（← load_data）
  combat.py          # 出牌/回合/敌人意图、incoming_damage、can_kill_this_turn（数值 ← load_data）
  draw_scheduler.py  # 抽牌组合枚举、带权单步、定长路径 enumerate_draw_paths
  solver.py          # 增量前沿 DP solve_encounter；_PathSolver（导出/复核）、within_turn
  progress.py        # ConsoleProgress / NullProgress

scripts/
  run_pilot.py       # 命令行试点；--progress --hp --gc-interval --hard-cap --dist --export

tests/
  test_manual.py     # 手算用例

data/sts1/           # 塔1 角色 JSON（遭遇待录）
data/sts2/           # 塔2 角色、卡牌、遭遇 JSON（见各 README）
```

### 3.1 两层求解器

1. **层 1 抽牌**：DFS 展开上手组合；每叶带权重 w(ω)。  
2. **层 2 出牌**：`solve_encounter` 用**增量前沿 DP**——沿抽牌 DFS 维护「战斗状态前沿」（每个回合初战斗状态 → 最小累计战损），每回合用 `within_turn` 把前沿推进一步，停在 `best_kill ≤ surv`。不再每个前缀从头重解（旧 `_PathSolver` 每前缀重建会慢且其近似击杀判定会低估战损）。`_PathSolver`（精确）仅用于导出/逐条复核。

### 3.2 关键表示

- **Pile** = `tuple[int,int,int,int]` = (打击, 防御, 痛击, 诅咒) 张数；**不**枚举牌序。
- **State**：回合初完整局面（`engine/types.py`）。
- 弃牌堆成分由 **抽牌路径** 决定，与出牌无关（`docs/抽牌枚举协议.md` §7）。

### 3.3 层 2 剪枝（已实现，文档 §5）

1. 本回合可击杀 → 只走击杀分支。  
2. 格挡已够 → 不打防、不空过，有攻击就打。  
3. 手牌无防可打 → 剩余费用全力攻击。

### 3.4 内存

- **禁止**跨路径无限 `lru_cache`（曾 OOM）。  
- 使用 `_PathSolver` **路径内 memo**，路径结束即释放。  
- `solve_encounter` 流式聚合，不保留全部 D(ω) 列表（`--export` 时写 JSONL）。

---

## 4. 实现状态 vs 目标

| 能力 | 状态 |
|------|------|
| 战斗引擎 + 剪枝 | ✅ |
| 路径内 memo + gc | ✅ |
| 进度条 `--progress`（支持未知总数） | ✅ |
| **DFS 打到击杀**（增量前沿 DP，停止条件 `best_kill ≤ surv`） | ✅ |
| **加权 w(ω) 汇总**（`Fraction` 精确，`P`/`E[D]`/分布） | ✅ |
| JSON 加载器（`engine/load_data.py`，引擎已去硬编码） | ✅ |
| 路线明细 JSONL 导出（`--export`，回放校验） | ✅ |

改求解逻辑前请读 `docs/求解器设计.md` §4（停止条件）+ §8 路线图，避免恢复已废弃的定长截断 / 等权 / 全局 cache。

> ⚠️ **关键陷阱**：不要一见「本回合可击杀」就停止延长抽牌树。正确停止条件是 **`best_kill ≤ surv`**（详见 `docs/求解器设计.md` §4）。

---

## 5. 常用命令

```powershell
# 在仓库根目录执行
python tests\test_manual.py
python scripts\run_pilot.py --hp 47 48 49 --progress --dist
python scripts\run_pilot.py --hp 47 --export data/exports
```

PowerShell 用 `;` 链接命令，不用 `&&`。长跑建议 `sys.setrecursionlimit` 已设在 `run_pilot.py`。

---

## 6. 扩展数据时

1. 按 `docs/游戏数据格式.md` 增加 JSON。  
2. 更新或新增 `pilot_*.md`。  
3. 实现/扩展 JSON → `engine` 加载（勿长期双份硬编码）。  
4. 新角色：确认 `docs/抽牌枚举协议.md` 协议档（标准档 / 猎手档）；机制见 `docs/角色战斗机制.md`。

---

## 7. 不要做的事

- 不要枚举牌序或全排列洗牌（应用组合 + 权重）。  
- 不要用固定回合截断当最终统计（会低估长局战损）。  
- 不要对抽牌路线等权算概率。  
- 不要未经请求提交 git、不要扩写无关文档。  
- 用户交流使用 **中文**。

---

## 8. 仓库内无

- 无 `requirements.txt`（当前仅标准库）。  
- 无塔1 **遭遇** JSON（`data/sts1/characters/` 已建，见 `data/sts1/README.md`）。  
- 无 CI。
