# 塔1 数据索引

高进阶对标 **A20**（怪物数值档用 JSON 的 `high`，录入时与塔2 的 A10 档区分）。

## 角色（4）

| 文件 | 机制摘要 | solver_status |
|------|----------|---------------|
| `characters/ironclad.json` | 标准 11 选 5 | data_only（遭遇未录） |
| `characters/silent.json` | 13 选 7；仅弃诅咒耦合层 1；诅咒消耗后 7选5↔10选3 | data_only |
| `characters/defect.json` | 充能球 | data_only |
| `characters/watcher.json` | 姿态（愤怒/平静/神格）、至纯之水 | data_only |

储君、亡灵契约师仅塔2，见 `data/sts2/`。

## 遭遇战

塔1 Act1 弱怪池（如邪教徒、大颚虫、小史莱姆等）**待录入** `encounters/`。

录入时请注明对标 A20 的 `low`/`high` 数值来源。

## 机制文档

`docs/角色战斗机制.md`
