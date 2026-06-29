"""层 2：局面求解器（路径内 DP）+ 层 1 DFS 打到击杀的加权统计。"""

from __future__ import annotations

import gc
import json
import time
from collections import defaultdict
from fractions import Fraction

from engine.combat import (
    ATTACKS,
    PLAYABLE,
    block_is_sufficient,
    can_kill_this_turn,
    end_player_turn,
    enemy_turn,
    has_playable_attack,
    play_card,
    prepare_next_turn,
)
from engine.deck import DEFEND, IRONCLAD_A10_DECK
from engine.draw_scheduler import (
    TurnPiles,
    end_turn_piles,
    weighted_draw_at_turn_start,
    weighted_opening,
)
from engine.progress import NullProgress, ProgressCallback
from engine.types import (
    EMPTY_PILE,
    MAX_DAMAGE,
    PathResult,
    Pile,
    SolveResult,
    State,
    TurnTrace,
)

# 前缀内无法击杀时层 2 返回的“无效战损”哨兵。
# 取值远大于任何真实战损（敌人 HP 有限、伤害有限），但小于 int 溢出风险。
INF_DAMAGE = 10**9

# DFS 打到击杀的硬上界（仅防实现 bug 导致的无限延长，不参与统计口径）。
HARD_TURN_CAP = 40

# ---------------------------------------------------------------------------
# 增量前沿求解（正确且高效）
#
# 思路：弃牌堆演化与出牌无关（回合末整手进弃牌堆），故层 1 抽牌分支与层 2 出牌
# 解耦。沿抽牌 DFS 维护一个「战斗状态前沿」：回合初所有可达战斗状态 → 到达它的
# 最小累计战损。每回合用当前抽到的手牌把前沿推进一步（within_turn 枚举本回合所有
# 出牌结果，按 §5 无歧义最优；这里为求正确不剪枝、枚举全部出牌子集取每个后继的最
# 小战损）。停止条件用前沿真实算出的 best_kill ≤ surv（再拖不可能更低）。
#
# 战斗状态（玩家回合初，能量满、未抽牌、玩家格挡=0、铁甲此 deck 无玩家增益/减益）：
#   cs = (enemy_hp, enemy_block, enemy_strength, enemy_vulnerable, intent_index)
# ---------------------------------------------------------------------------

CombatCS = tuple  # (enemy_hp, enemy_block, enemy_strength, enemy_vulnerable, intent_index)


def _cs_to_state(cs: CombatCS, hand: Pile) -> State:
    ehp, eblk, estr, evul, intent = cs
    return State(
        enemy_hp=ehp,
        enemy_block=eblk,
        enemy_strength=estr,
        enemy_vulnerable=evul,
        intent_index=intent,
        player_block=0,
        player_vulnerable=0,
        player_weak=0,
        player_frail=0,
        player_strength=0,
        player_dexterity=0,
        damage_taken=0,
        turn_count=1,
        energy=3,
        hand=hand,
        draw=EMPTY_PILE,
        discard=EMPTY_PILE,
        exhaust=EMPTY_PILE,
        hand_at_turn_start=hand,
    )


def within_turn(
    cs: CombatCS, hand: Pile, memo: dict
) -> tuple[bool, dict[CombatCS, int]]:
    """
    单回合推进：给定回合初战斗状态 cs 与本回合手牌，枚举所有合法出牌序列。
    返回 (can_kill, alive)：
    - can_kill：是否存在一条本回合击杀的出牌（击杀时本回合不再挨打，额外战损 0）。
    - alive：{下一回合初战斗状态 cs' → 到达 cs' 的本回合最小额外战损（敌人行动造成）}。
    """
    key = (cs, hand)
    cached = memo.get(key)
    if cached is not None:
        return cached

    alive: dict[CombatCS, int] = {}
    can_kill = False
    seen: set = set()

    def rec(s: State) -> None:
        nonlocal can_kill
        if s.enemy_hp <= 0:
            can_kill = True
            return
        k = (s.enemy_hp, s.enemy_block, s.enemy_vulnerable, s.player_block, s.energy, s.hand)
        if k in seen:
            return
        seen.add(k)

        # 选项：此刻结束回合 → 敌人行动 → 下一回合初。
        after_enemy = enemy_turn(s)  # 不处理弃牌/抽牌（牌堆独立演化）
        nxt = prepare_next_turn(after_enemy)
        cs2 = (
            nxt.enemy_hp,
            nxt.enemy_block,
            nxt.enemy_strength,
            nxt.enemy_vulnerable,
            nxt.intent_index,
        )
        extra = after_enemy.damage_taken  # s.damage_taken==0，故即本回合挨打
        if cs2 not in alive or extra < alive[cs2]:
            alive[cs2] = extra

        # 选项：再打一张牌。
        for card in PLAYABLE:
            ns = play_card(s, card)
            if ns is not None:
                rec(ns)

    rec(_cs_to_state(cs, hand))
    result = (can_kill, alive)
    memo[key] = result
    return result


def _combat_key(state: State) -> tuple:
    return (
        state.enemy_hp,
        state.enemy_block,
        state.enemy_strength,
        state.enemy_vulnerable,
        state.intent_index,
        state.player_block,
        state.player_vulnerable,
        state.player_weak,
        state.player_frail,
        state.player_strength,
        state.player_dexterity,
        state.damage_taken,
        state.turn_count,
    )


def _state_from(combat_key: tuple, piles: TurnPiles, energy: int, hand: Pile, hand_start: Pile) -> State:
    return State(
        combat_key[0],
        combat_key[1],
        combat_key[2],
        combat_key[3],
        combat_key[4],
        combat_key[5],
        combat_key[6],
        combat_key[7],
        combat_key[8],
        combat_key[9],
        combat_key[10],
        combat_key[11],
        combat_key[12],
        energy,
        hand,
        piles.draw,
        piles.discard,
        piles.exhaust,
        hand_start,
    )


def _is_terminal_combat(combat_key: tuple) -> bool:
    # 仅 enemy_hp<=0 为真正终止；MAX_DAMAGE 为 absurd 保险丝（防 bug，不参与统计）。
    return combat_key[0] <= 0 or combat_key[11] >= MAX_DAMAGE


def _path_to_key(path: tuple[TurnPiles, ...]) -> tuple:
    return tuple((tp.hand, tp.draw, tp.discard, tp.exhaust) for tp in path)


def _play_candidates(state: State, *, lethal_possible: bool) -> tuple[str, ...]:
    if state.enemy_hp <= 0:
        return ()
    if lethal_possible:
        return ATTACKS
    if block_is_sufficient(state) and has_playable_attack(state):
        return ATTACKS
    if block_is_sufficient(state):
        return ()
    return ATTACKS + (DEFEND,)


def _may_end_turn(state: State, *, lethal_possible: bool) -> bool:
    if state.enemy_hp <= 0:
        return True
    if lethal_possible:
        return False
    if block_is_sufficient(state) and has_playable_attack(state):
        return False
    return True


class _PathSolver:
    """
    单条抽牌路径（前缀）的层 2 求解器。
    记忆化表仅在路径内有效，路径结束后随实例回收，避免全局 cache 撑爆内存。

    truncate 控制“前缀用尽但敌人未死”的行为：
    - True ：返回当前累计战损（旧定长语义，可能低估，仅供 solve_draw_path 兼容）。
    - False：返回 INF_DAMAGE（无效），交由外层 DFS 延长抽牌路线（打到击杀）。

    accurate_lethal 控制「本回合可否击杀」的判定口径：
    - False（默认，DFS 统计用）：用回合初满手牌近似（over-approx），剪枝更激进、整树更快；
      会产生 best is None 的“强制进攻却无牌可打”死线，按 combat_key[11] 兜底——
      本回合 damage_taken 不变，与真击杀线同值，不影响 min 统计（已交叉验证）。
    - True（导出重建用，仅对单条前缀）：用当前子状态精确判定，无死线、无 phantom，
      best 永不为 None，reconstruct 可精确跟随最优出牌迹。单条前缀求解开销很小。
    """

    __slots__ = ("suffix_key", "truncate", "accurate_lethal", "_memo", "_kill_memo")

    def __init__(
        self, suffix_key: tuple, *, truncate: bool = True, accurate_lethal: bool = False
    ) -> None:
        self.suffix_key = suffix_key
        self.truncate = truncate
        self.accurate_lethal = accurate_lethal
        self._memo: dict[tuple, int] = {}
        self._kill_memo: dict[tuple, bool] = {}

    def _piles_at(self, turn_idx: int) -> TurnPiles:
        h, d, disc, exh = self.suffix_key[turn_idx]
        return TurnPiles(h, d, disc, exh)

    def _turn_start_state(
        self, combat_key: tuple, turn_idx: int, hand_start: Pile
    ) -> State:
        return _state_from(combat_key, self._piles_at(turn_idx), 3, hand_start, hand_start)

    def solve(self, enemy_hp: int, first_hand: Pile) -> int:
        ck = (enemy_hp, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)
        return self._solve_turn(ck, 0, 3, first_hand, first_hand)

    def _solve_turn(
        self,
        combat_key: tuple,
        turn_idx: int,
        energy: int,
        hand: tuple[int, int, int, int],
        hand_start: tuple[int, int, int, int],
    ) -> int:
        key = (combat_key, turn_idx, energy, hand, hand_start)
        cached = self._memo.get(key)
        if cached is not None:
            return cached

        if _is_terminal_combat(combat_key):
            self._memo[key] = combat_key[11]
            return combat_key[11]

        state = _state_from(combat_key, self._piles_at(turn_idx), energy, hand, hand_start)

        if state.enemy_hp <= 0:
            self._memo[key] = combat_key[11]
            return combat_key[11]

        if self.accurate_lethal:
            lethal_possible = can_kill_this_turn(state, self._kill_memo)
        else:
            turn_start = self._turn_start_state(combat_key, turn_idx, hand_start)
            lethal_possible = can_kill_this_turn(turn_start, self._kill_memo)

        best: int | None = None

        for card in _play_candidates(state, lethal_possible=lethal_possible):
            nxt = play_card(state, card)
            if nxt is not None:
                if nxt.enemy_hp <= 0:
                    self._memo[key] = combat_key[11]
                    return combat_key[11]
                d = self._solve_turn(
                    _combat_key(nxt),
                    turn_idx,
                    nxt.energy,
                    nxt.hand,
                    hand_start,
                )
                if best is None or d < best:
                    best = d
                    if best == 0:
                        self._memo[key] = 0
                        return 0

        if _may_end_turn(state, lethal_possible=lethal_possible):
            after = end_player_turn(state)
            if after.enemy_hp <= 0 or _is_terminal_combat(_combat_key(after)):
                end_dmg = after.damage_taken
            else:
                next_idx = turn_idx + 1
                if next_idx >= len(self.suffix_key):
                    # 前缀用尽，敌人未死。
                    end_dmg = after.damage_taken if self.truncate else INF_DAMAGE
                else:
                    np = self._piles_at(next_idx)
                    end_dmg = self._solve_turn(
                        _combat_key(after),
                        next_idx,
                        3,
                        np.hand,
                        np.hand,
                    )

            if best is None or end_dmg < best:
                best = end_dmg

        # best is None 仅在 hybrid（accurate_lethal=False）近似下出现的死线；
        # accurate 模式下 may_end=False 必有可打牌，best 永不为 None。
        result = best if best is not None else combat_key[11]
        self._memo[key] = result
        return result

    def _end_turn_value(
        self, state: State, turn_idx: int
    ) -> tuple[int, State, int | None]:
        """复刻 _solve_turn 的「结束回合」取值。返回 (end_dmg, after, next_idx 或 None)。"""
        after = end_player_turn(state)
        if after.enemy_hp <= 0 or _is_terminal_combat(_combat_key(after)):
            return after.damage_taken, after, None
        next_idx = turn_idx + 1
        if next_idx >= len(self.suffix_key):
            return (after.damage_taken if self.truncate else INF_DAMAGE), after, None
        np = self._piles_at(next_idx)
        end_dmg = self._solve_turn(_combat_key(after), next_idx, 3, np.hand, np.hand)
        return end_dmg, after, next_idx

    def reconstruct(self, enemy_hp: int, first_hand: Pile) -> tuple[TurnTrace, ...]:
        """
        在 solve() 之后沿最优值回溯每回合出牌序列。
        各动作值经 _solve_turn（记忆化）按需重算，精确复刻 solve 的取值与选择。
        要求实例 truncate=False 且 accurate_lethal=True（无 phantom 死线）。
        """
        assert self.accurate_lethal and not self.truncate
        traces: list[TurnTrace] = []
        combat_key = (enemy_hp, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)
        turn_idx = 0
        hand = first_hand
        hand_start = first_hand

        while True:
            cur_ck = combat_key
            cur_energy = 3
            cur_hand = hand
            plays: list[str] = []
            turn_hand = self._piles_at(turn_idx).hand

            while True:
                target = self._solve_turn(cur_ck, turn_idx, cur_energy, cur_hand, hand_start)
                state = _state_from(cur_ck, self._piles_at(turn_idx), cur_energy, cur_hand, hand_start)
                lethal = can_kill_this_turn(state, self._kill_memo)  # 与 accurate solve 一致

                advanced = False
                for card in _play_candidates(state, lethal_possible=lethal):
                    nxt = play_card(state, card)
                    if nxt is None:
                        continue
                    if nxt.enemy_hp <= 0:
                        if cur_ck[11] == target:  # 击杀：本回合敌人不再行动
                            plays.append(card)
                            traces.append(
                                TurnTrace(
                                    turn=turn_idx + 1,
                                    hand=turn_hand,
                                    plays=tuple(plays),
                                    damage_after=cur_ck[11],
                                    enemy_hp_after_plays=nxt.enemy_hp,
                                )
                            )
                            return tuple(traces)
                    else:
                        val = self._solve_turn(
                            _combat_key(nxt), turn_idx, nxt.energy, nxt.hand, hand_start
                        )
                        if val == target:
                            plays.append(card)
                            cur_ck = _combat_key(nxt)
                            cur_energy = nxt.energy
                            cur_hand = nxt.hand
                            advanced = True
                            break
                if advanced:
                    continue

                if not _may_end_turn(state, lethal_possible=lethal):
                    raise RuntimeError("reconstruct: 无匹配动作且不可结束回合")
                end_dmg, after, next_idx = self._end_turn_value(state, turn_idx)
                if end_dmg != target:
                    raise RuntimeError("reconstruct: 结束回合值与最优不符")
                if next_idx is None:
                    traces.append(
                        TurnTrace(
                            turn=turn_idx + 1,
                            hand=turn_hand,
                            plays=tuple(plays),
                            damage_after=after.damage_taken,
                            enemy_hp_after_plays=after.enemy_hp,
                        )
                    )
                    return tuple(traces)

                traces.append(
                    TurnTrace(
                        turn=turn_idx + 1,
                        hand=turn_hand,
                        plays=tuple(plays),
                        damage_after=after.damage_taken,
                        enemy_hp_after_plays=state.enemy_hp,
                    )
                )
                combat_key = _combat_key(after)
                turn_idx = next_idx
                hand = self._piles_at(next_idx).hand
                hand_start = hand
                break


def solve_draw_path(enemy_hp: int, path: tuple[TurnPiles, ...]) -> int:
    """旧定长语义：前缀用尽未死则返回截断战损（仅供测试 / 兼容）。"""
    if not path:
        return 0
    return _PathSolver(
        _path_to_key(path), truncate=True, accurate_lethal=True
    ).solve(enemy_hp, path[0].hand)


def solve_prefix_killable(enemy_hp: int, path: tuple[TurnPiles, ...]) -> tuple[int, bool]:
    """
    在“强制前缀内击杀”的语义下求解该抽牌前缀。

    返回 (kill_damage, killable)：
    - killable=True ：前缀内存在击杀方案，kill_damage = 强制在 ≤t 回合击杀的最小总战损（上界）。
    - killable=False：前缀内任何出牌都杀不掉敌人。

    注意：kill_damage 本身不一定是真实 D(ω)——若拖到更晚回合、先垫格挡再击杀可能更低。
    停止延长需配合“生存下界”判定，见 solve_encounter。
    """
    if not path:
        return (0, enemy_hp <= 0)
    d = _PathSolver(
        _path_to_key(path), truncate=False, accurate_lethal=True
    ).solve(enemy_hp, path[0].hand)
    if d >= INF_DAMAGE:
        return (INF_DAMAGE, False)
    return (d, True)


def solve_path_with_trace(enemy_hp: int, path: tuple[TurnPiles, ...]) -> PathResult:
    """求解前缀（须为可在前缀内击杀的完整 ω）并重建最优出牌迹。weight 由调用方填。"""
    solver = _PathSolver(_path_to_key(path), truncate=False, accurate_lethal=True)
    d = solver.solve(enemy_hp, path[0].hand)
    trace = solver.reconstruct(enemy_hp, path[0].hand)
    return PathResult(
        weight=Fraction(0),
        min_damage=d,
        opening_hand=path[0].hand,
        turns=trace,
    )


def solve_state(state: State) -> SolveResult:
    tp = TurnPiles(state.hand, state.draw, state.discard, state.exhaust)
    dmg = solve_draw_path(state.enemy_hp, (tp,))
    return SolveResult(min_damage=dmg, play_path=(), end_state=None, combat_over=False)


def _path_result_to_json(enemy_hp: int, weight: Fraction, pr: PathResult) -> str:
    obj = {
        "enemy_hp": enemy_hp,
        "weight": float(weight),
        "weight_frac": [weight.numerator, weight.denominator],
        "min_damage": pr.min_damage,
        "opening_hand": list(pr.opening_hand),
        "turns": [
            {
                "turn": t.turn,
                "hand": list(t.hand),
                "plays": list(t.plays),
                "damage_after": t.damage_after,
                "enemy_hp": t.enemy_hp_after_plays,
            }
            for t in pr.turns
        ],
    }
    return json.dumps(obj, ensure_ascii=False)


def solve_encounter(
    enemy_hp: int,
    *,
    progress: ProgressCallback | None = None,
    gc_interval: int = 500,
    hard_turn_cap: int = HARD_TURN_CAP,
    export_path: str | None = None,
) -> dict:
    """
    DFS 打到击杀，按组合权重 w(ω) 加权统计整场遭遇。

    层 1：逐回合枚举带权抽牌组合（weighted_*），每延长一回合对该前缀求两个量：
          - surv  = 仅生存 t 回合的最小战损（truncate=True），任意更长 ω 的下界；
          - killd = 强制 ≤t 回合击杀的最小战损（truncate=False），上界。
          当 killd == surv 时，再拖延也不可能更低 → 记录 (w, killd)；否则抽下一回合。
          （不能一见“可击杀”就停：为早杀牺牲格挡反而更亏，须等击杀代价降到生存下界。）
    层 2：_PathSolver —— 固定抽牌前缀下最优出牌的最小总战损。

    统计（不等权）：
    - P(必伤)   = Σ_{D>0} w / Σ w
    - E[战损]   = Σ w·D / Σ w
    - 加权分布  = {D: Σ w} / Σ w
    """
    reporter = progress or NullProgress()
    label = f"HP={enemy_hp}"
    reporter.on_start(0, label)  # 总数未知（打到击杀，无法预先计数）

    total_w = Fraction(0)
    must_w = Fraction(0)
    sum_wd = Fraction(0)
    hist: dict[int, Fraction] = defaultdict(Fraction)
    min_damage: int | None = None
    max_damage: int | None = None
    leaves = 0
    truncated = 0

    export_file = open(export_path, "w", encoding="utf-8") if export_path else None

    def record(weight: Fraction, damage: int) -> None:
        nonlocal total_w, must_w, sum_wd, min_damage, max_damage, leaves
        total_w += weight
        sum_wd += weight * damage
        hist[damage] += weight
        if damage > 0:
            must_w += weight
        min_damage = damage if min_damage is None else min(min_damage, damage)
        max_damage = damage if max_damage is None else max(max_damage, damage)
        leaves += 1
        reporter.on_step(leaves, 0, label)
        if gc_interval > 0 and leaves % gc_interval == 0:
            gc.collect()

    wt_memo: dict = {}  # within_turn 缓存（跨整场遭遇共享）

    def dfs(
        turn_idx: int,
        draw: Pile,
        discard: Pile,
        exhaust: Pile,
        prefix: tuple[TurnPiles, ...],
        weight: Fraction,
        frontier: dict[CombatCS, int],
        best_kill: int,
    ) -> None:
        nonlocal truncated
        if turn_idx == 1:
            branches = weighted_opening()
        else:
            branches = weighted_draw_at_turn_start(draw, discard, exhaust)

        for tp, step_p in branches:
            w = weight * step_p
            new_prefix = prefix + (tp,)

            # 用本回合手牌把前沿推进一步。
            nf: dict[CombatCS, int] = {}
            bk = best_kill
            for cs, dmg in frontier.items():
                can_kill, alive = within_turn(cs, tp.hand, wt_memo)
                if can_kill and dmg < bk:
                    bk = dmg  # 本回合击杀：本回合不再挨打，D = 进入本回合的累计战损
                for cs2, extra in alive.items():
                    nd = dmg + extra
                    if cs2 not in nf or nd < nf[cs2]:
                        nf[cs2] = nd
            surv = min(nf.values()) if nf else INF_DAMAGE  # 生存下界（再拖至少这么多）

            if bk <= surv:
                # 击杀代价已降到生存下界，延长不可能更低 → D(ω) 确定。
                record(w, bk)
                if export_file is not None:
                    pr = solve_path_with_trace(enemy_hp, new_prefix)
                    export_file.write(_path_result_to_json(enemy_hp, w, pr) + "\n")
            elif turn_idx >= hard_turn_cap:
                # 保险丝：理论上不可达（敌人 HP 有限、每回合必有攻击牌）。
                truncated += 1
                record(w, bk if bk < INF_DAMAGE else surv)
            else:
                nd_, ndisc, nexh = end_turn_piles(tp)
                dfs(turn_idx + 1, nd_, ndisc, nexh, new_prefix, w, nf, bk)

    t0 = time.perf_counter()
    init_frontier: dict[CombatCS, int] = {(enemy_hp, 0, 0, 0, 0): 0}
    try:
        dfs(
            1,
            IRONCLAD_A10_DECK,
            EMPTY_PILE,
            EMPTY_PILE,
            (),
            Fraction(1),
            init_frontier,
            INF_DAMAGE,
        )
    finally:
        if export_file is not None:
            export_file.close()
    elapsed = time.perf_counter() - t0
    reporter.on_finish(label, elapsed)
    gc.collect()

    p_must = float(must_w / total_w) if total_w else 0.0
    e_damage = float(sum_wd / total_w) if total_w else 0.0
    distribution = {
        d: float(w / total_w) for d, w in sorted(hist.items())
    } if total_w else {}

    return {
        "enemy_hp": enemy_hp,
        "leaves": leaves,
        "total_weight": float(total_w),  # 应 ≈ 1.0（校验用）
        "p_must_damage": p_must,
        "e_damage": e_damage,
        "min_damage": min_damage or 0,
        "max_damage": max_damage or 0,
        "distribution": distribution,
        "truncated": truncated,
    }
