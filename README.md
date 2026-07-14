# STSInitialDeckAttrition

量化比较《杀戮尖塔》（塔1）与《杀戮尖塔 2》（塔2）在 **首场弱怪战斗** 中的战损差异（**Initial Deck Attrition**）。

## 背景

许多玩家感觉塔2首场更容易掉血。本项目用游戏数据验证：在 **初始卡组**、**最优出牌**（完美信息，对应 SL 玩法）的前提下，有多少抽牌路线 **必定无法零战损**，以及战损分布如何。

- 不与游戏本体联动，不依赖真实游玩记录
- 怪物与卡组来自 wiki / 手工录入的 JSON
- 按抽牌路线的 **真实概率权重** 汇总统计（非等权）

## 当前进度

**求解器**（铁甲战士试点）：增量前沿 DP，DFS 打到击杀；塔2 A10 · 铁甲 vs 海洋混混 HP 47/48/49 → P(必伤)=1.0，E[D] ≈ 7.58 / 7.74 / 8.91。

**数据**：塔2 五角色 + Underdocks 弱怪 4 场 JSON 已录；塔1 四角色 JSON 已录；机制说明见 `docs/角色战斗机制.md`（待用户逐角色细化）。

## 快速开始

```bash
python tests/test_manual.py
python scripts/run_pilot.py --hp 47 48 49 --dist
python scripts/run_pilot.py --hp 47 --export data/exports
```

需要 Python 3.10+，无第三方依赖。

## 文档

| 文件 | 说明 |
|------|------|
| [AGENTS.md](AGENTS.md) | 项目结构与 Agent 上手指南 |
| [docs/项目计划书.md](docs/项目计划书.md) | 目标与范围 |
| [docs/游戏机制.md](docs/游戏机制.md) | 通用战斗规则 |
| [docs/角色战斗机制.md](docs/角色战斗机制.md) | 六角色首场机制、译名 |
| [docs/游戏数据格式.md](docs/游戏数据格式.md) | JSON schema |
| [docs/抽牌枚举协议.md](docs/抽牌枚举协议.md) | 抽牌组合与协议档 |
| [docs/求解器设计.md](docs/求解器设计.md) | 求解器技术方案 |

## 许可

未指定。数据描述来源于游戏公开 wiki 与社区资料，仅供研究交流。
