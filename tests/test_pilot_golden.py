"""铁甲战士 vs 海洋混混（塔2 A10）试点金标回归门禁。

数值来源：docs/求解器设计.md §9 正确性验证、docs/项目计划书.md 试点结果。
任何共享层 1 抽牌 / 牌堆推进 / 前沿 DP 的改动须保持本文件通过。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.solver import solve_encounter

# 与 solve_encounter(hp) 当前输出一致（Fraction 聚合后的 float）
PILOT_GOLDEN: dict[int, dict[str, float | int]] = {
    47: {
        "p_must_damage": 1.0,
        "e_damage": 7.575901532153369,
        "min_damage": 3,
        "max_damage": 31,
        "leaves": 3318,
    },
    48: {
        "p_must_damage": 1.0,
        "e_damage": 7.738174860806543,
        "min_damage": 3,
        "max_damage": 31,
        "leaves": 3441,
    },
    49: {
        "p_must_damage": 1.0,
        "e_damage": 8.90984233317311,
        "min_damage": 3,
        "max_damage": 31,
        "leaves": 6520,
    },
}

E_DAMAGE_TOLERANCE = 0.01
WEIGHT_TOLERANCE = 1e-9

# 文档记录：最深停止回合 = 8；solve_encounter 返回 dict 未暴露该字段，此处不断言。


def test_pilot_golden_seapunk_all_hp():
    for hp, expected in PILOT_GOLDEN.items():
        r = solve_encounter(hp)
        assert r["truncated"] == 0, (hp, r["truncated"])
        assert abs(r["total_weight"] - 1.0) < WEIGHT_TOLERANCE, (hp, r["total_weight"])
        assert r["p_must_damage"] == expected["p_must_damage"], (hp, r["p_must_damage"])
        assert abs(r["e_damage"] - expected["e_damage"]) < E_DAMAGE_TOLERANCE, (
            hp,
            r["e_damage"],
            expected["e_damage"],
        )
        assert r["min_damage"] == expected["min_damage"], (hp, r["min_damage"])
        assert r["max_damage"] == expected["max_damage"], (hp, r["max_damage"])
        assert r["leaves"] == expected["leaves"], (hp, r["leaves"])


def test_pilot_golden_seapunk_hp47():
    """单 HP 快速门禁（CI / 本地迭代时可只跑此条）。"""
    expected = PILOT_GOLDEN[47]
    r = solve_encounter(47)
    assert r["p_must_damage"] == expected["p_must_damage"]
    assert abs(r["e_damage"] - expected["e_damage"]) < E_DAMAGE_TOLERANCE
    assert r["min_damage"] == expected["min_damage"]
    assert r["max_damage"] == expected["max_damage"]


if __name__ == "__main__":
    test_pilot_golden_seapunk_hp47()
    test_pilot_golden_seapunk_all_hp()
    print("pilot golden: 全部通过")
