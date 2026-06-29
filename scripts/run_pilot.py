#!/usr/bin/env python3
"""试点：铁甲战士 vs 海洋混混（A10）。DFS 打到击杀 + 加权统计。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.deck import opening_combination_count
from engine.progress import make_progress
from engine.solver import HARD_TURN_CAP, solve_encounter


def main() -> None:
    sys.setrecursionlimit(500_000)
    parser = argparse.ArgumentParser()
    parser.add_argument("--hp", type=int, nargs="+", default=[47, 48, 49])
    parser.add_argument(
        "--progress",
        action="store_true",
        help="显示抽牌路线求解进度（stderr）",
    )
    parser.add_argument(
        "--gc-interval",
        type=int,
        default=500,
        help="每记录 N 条路线触发一次 gc.collect()（0=关闭）",
    )
    parser.add_argument(
        "--hard-cap",
        type=int,
        default=HARD_TURN_CAP,
        help="DFS 延长回合硬上界（仅防 bug，不参与统计口径）",
    )
    parser.add_argument(
        "--dist",
        action="store_true",
        help="打印加权战损分布",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="DIR",
        help="导出每条路线明细 JSONL 到该目录（每个 HP 一个文件 route_hp{HP}.jsonl）",
    )
    args = parser.parse_args()

    export_dir = Path(args.export) if args.export else None
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)

    print(f"第 1 回合上手组合: {opening_combination_count()}")

    progress = make_progress(args.progress)

    for hp in args.hp:
        t0 = time.perf_counter()
        export_path = str(export_dir / f"route_hp{hp}.jsonl") if export_dir else None
        r = solve_encounter(
            hp,
            progress=progress,
            gc_interval=args.gc_interval,
            hard_turn_cap=args.hard_cap,
            export_path=export_path,
        )
        elapsed = time.perf_counter() - t0
        print(f"\n=== 海洋混混 HP={hp} ===")
        print(f"  叶子路线数: {r['leaves']}")
        print(f"  权重和(校验≈1): {r['total_weight']:.6f}")
        print(f"  P(必伤): {r['p_must_damage']:.6f}")
        print(f"  加权期望战损: {r['e_damage']:.4f}")
        print(f"  战损范围: {r['min_damage']} – {r['max_damage']}")
        if export_path:
            print(f"  路线明细已导出: {export_path}")
        if r["truncated"]:
            print(f"  [警告] 触发硬上界截断: {r['truncated']} 条")
        if args.dist:
            print("  加权战损分布:")
            for d, p in r["distribution"].items():
                bar = "#" * int(round(p * 50))
                print(f"    D={d:>3}  {p * 100:6.2f}%  {bar}")
        print(f"  耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
