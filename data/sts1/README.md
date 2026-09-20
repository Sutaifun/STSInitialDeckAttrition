# 塔1 数据索引

高进阶对标 **A20**（怪物数值档用 JSON 的 `high`，录入时与塔2 的 A10 档区分）。

## 角色（4）

| 文件 | 机制摘要 | solver_status |
|------|----------|---------------|
| `characters/ironclad.json` | 标准 11 选 5 | data_only |
| `characters/silent.json` | 13 选 7；仅弃诅咒耦合层 1；诅咒消耗后 7选5↔10选3 | data_only |
| `characters/defect.json` | 充能球 | data_only |
| `characters/watcher.json` | 姿态（愤怒/平静/神格）、至纯之水 | data_only |

储君、亡灵契约师仅塔2，见 `data/sts2/`。

## 卡牌

| 文件 | 说明 |
|------|------|
| `cards/slimed.json` | 粘液：打出后消耗；无其他效果 |

## 遭遇战（Act1 弱怪池）

| 遭遇文件 | 说明 | 求解器 |
|----------|------|--------|
| `encounters/cultist.json` | 邪教徒 ×1 | data_only |
| `encounters/jaw_worm.json` | 大颚虫 ×1（加权 AI） | data_only |
| `encounters/two_louses.json` | 2×虱（各 50% 红/绿） | data_only |
| `encounters/small_slimes.json` | 小史莱姆两种排布 50/50 | data_only |

录入对标 A20 的 `low`/`high` 数值来源：wiki.gg Exordium 弱池与各怪物页。

## 机制文档

`docs/角色战斗机制.md`
