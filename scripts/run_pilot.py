#!/usr/bin/env python3
"""试点：铁甲战士 vs 海洋混混（A10）。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.deck import opening_combination_count
from engine.draw_scheduler import count_draw_paths
from engine.progress import make_progress
from engine.solver import solve_encounter


def main() -> None:
    sys.setrecursionlimit(500_000)
    parser = argparse.ArgumentParser()
    parser.add_argument("--hp", type=int, nargs="+", default=[47, 48, 49])
    parser.add_argument("--turns", type=int, default=8, help="回合上限")
    parser.add_argument(
        "--progress",
        action="store_true",
        help="显示抽牌路径求解进度（stderr）",
    )
    parser.add_argument(
        "--gc-interval",
        type=int,
        default=500,
        help="每处理 N 条抽牌路径触发一次 gc.collect()（0=关闭）",
    )
    args = parser.parse_args()

    print(f"第 1 回合上手组合: {opening_combination_count()}")
    print(f"抽牌路径数（{args.turns} 回合）: {count_draw_paths(args.turns)}")

    progress = make_progress(args.progress)

    for hp in args.hp:
        t0 = time.perf_counter()
        r = solve_encounter(
            hp,
            max_turns=args.turns,
            progress=progress,
            gc_interval=args.gc_interval,
        )
        elapsed = time.perf_counter() - t0
        print(f"\n=== 海洋混混 HP={hp} ===")
        print(f"  抽牌路径: {r['draw_paths']}")
        print(f"  必伤路径: {r['must_damage']}")
        print(f"  无伤路径: {r['zero_damage']}")
        print(f"  P(必伤): {r['p_must_damage']:.6f}")
        print(f"  战损范围: {r['min_damage']} – {r['max_damage']}")
        print(f"  耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
