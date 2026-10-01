"""两芯联合树轮定年对齐引擎.

规则
----
* 两支样芯共同对入同一地区年表, 每支末环必须匹配, 且两支末环落在同一日历年。
* 缺环: 样芯跨度内跳过年表项 (g); 伪环: 跳过样芯项 (f, 含首条匹配之前的样芯项)。
* 每支缺环、伪环各不超过限额 (默认 3), 每支至少匹配 8 环。
* 匹配差值 = |样芯指数 - 年表指数|, 逐环容差挂在样芯环上, 任一匹配越界即非法。

优化目标 (字典序):
    1. 两芯 (缺环 + 伪环) 总数最小;
    2. 全部匹配中的最大绝对差值最小;
    3. 全部匹配绝对差值之和最小。

对全部同优映射判定唯一 / 歧义, 并按映射 (年表位, 样芯环) 序列的稳定字典序
给出前两份见证。
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import merge as heap_merge
from typing import Dict, Iterable, List, Optional, Tuple

MIN_MATCHES = 8
DEFAULT_QUOTA = 3
RELAXED_QUOTA = 6

# 一条匹配: (样芯环下标 0-based, 年表项下标 0-based)
Pair = Tuple[int, int]


@dataclass(frozen=True)
class Placement:
    """单支样芯对年表的一份完整对齐。"""

    pairs: Tuple[Pair, ...]
    missing: int  # g: 跨度内跳过的年表项数
    false: int  # f: 跳过的样芯项数
    max_diff: int
    sum_diff: int
    span_start: int  # 首个匹配年表项下标

    @property
    def end_index(self) -> int:
        return self.pairs[-1][1]

    @property
    def skips(self) -> int:
        return self.missing + self.false

    def key(self) -> Tuple[Pair, ...]:
        # 以年表位为主序的匹配序列, 作为见证稳定排序键
        return tuple((j, i) for i, j in self.pairs)


@dataclass
class CoreAnalysis:
    """单支样芯在给定限额下的全部分析结果。"""

    sample: List[int]
    chron: List[int]
    cap_missing: int
    cap_false: int
    # end_index -> 可行放置的端点记录 (g, f, max_diff, sum_diff)
    end_records: Dict[int, List[Tuple[int, int, int, int]]]

    def feasible_ends(self) -> List[int]:
        return sorted(self.end_records)

    def min_skips_at(self, end: int) -> Optional[int]:
        recs = self.end_records.get(end)
        if not recs:
            return None
        return min(g + f for g, f, _, _ in recs)


# --------------------------------------------------------------------------- #
# 动态规划
# --------------------------------------------------------------------------- #


def _abs_diff(a: int, b: int) -> int:
    return a - b if a >= b else b - a


def _frontier_add(front: List[Tuple[int, int]], cand: Tuple[int, int]) -> List[Tuple[int, int]]:
    """把 (max_diff, sum_diff) 并入双目标最小化 Pareto 前沿。"""
    mx, sm = cand
    for a, b in front:
        if a <= mx and b <= sm:
            return front
    merged = [(a, b) for a, b in front if not (mx <= a and sm <= b)]
    merged.append(cand)
    return merged


def analyze_core(
    sample: List[int],
    chron: List[int],
    tolerance: List[int],
    cap_missing: int,
    cap_false: int,
) -> CoreAnalysis:
    """对一支样芯做全终点 DP。

    状态 (i, j, g, f): 样芯环 i 与年表项 j 已匹配, 跨度内已跳 g 个年表项、
    f 个样芯项; 状态值为该状态下 (最大差值, 差值和) 的 Pareto 前沿。
    首条匹配允许落在样芯环 i0 (0..cap_false), 其之前样芯项全部计伪环。
    """
    n, m = len(sample), len(chron)
    states: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}

    # 起点: 任意容差允许的 (i0, j0), f = i0
    for i0 in range(min(cap_false, n - 1) + 1):
        for j0 in range(m):
            d = _abs_diff(sample[i0], chron[j0])
            if d <= tolerance[i0]:
                states[(i0, j0, 0, i0)] = [(d, d)]

    for i in range(n):
        for j in range(m):
            for g in range(cap_missing + 1):
                for f in range(cap_false + 1):
                    front = states.get((i, j, g, f))
                    if not front:
                        continue
                    # 下一条匹配: 跳过 df 个样芯项、dg 个年表项
                    for step_i in range(1, cap_false - f + 2):
                        ip = i + step_i
                        if ip >= n:
                            break
                        df = step_i - 1
                        fp = f + df
                        for step_j in range(1, cap_missing - g + 2):
                            jp = j + step_j
                            if jp >= m:
                                break
                            dg = step_j - 1
                            d = _abs_diff(sample[ip], chron[jp])
                            if d > tolerance[ip]:
                                continue
                            gp = g + dg
                            key = (ip, jp, gp, fp)
                            new_front = states.get(key)
                            if new_front is None:
                                new_front = []
                            for mx, sm in front:
                                nd = max(mx, d)
                                ns = sm + d
                                new_front = _frontier_add(new_front, (nd, ns))
                            states[key] = new_front

    end_records: Dict[int, List[Tuple[int, int, int, int]]] = {}
    last = n - 1
    max_false_for_min_matches = n - MIN_MATCHES  # f <= n-8 才能至少匹配 8 环
    for (i, j, g, f), front in states.items():
        if i != last or f > max_false_for_min_matches:
            continue
        recs = end_records.setdefault(j, [])
        for mx, sm in front:
            rec = (g, f, mx, sm)
            if rec not in recs:
                recs.append(rec)
    return CoreAnalysis(sample, chron, cap_missing, cap_false, end_records)


# --------------------------------------------------------------------------- #
# 见证路径枚举 (精确目标统计量 + 后缀可达剪枝, 按键序产生)
# --------------------------------------------------------------------------- #


def enumerate_paths(
    sample: List[int],
    chron: List[int],
    tolerance: List[int],
    end: int,
    total_missing: int,
    total_false: int,
    target_max: int,
    target_sum: int,
) -> Iterable[Placement]:
    """枚举在指定终点与精确 (g, f, max, sum) 下的全部对齐, 按键序产生。"""
    n = len(sample)
    matched = n - total_false
    j0 = end - (matched - 1) - total_missing
    if j0 < 0 or matched < MIN_MATCHES:
        return
    last_i = n - 1
    if total_false > n - MIN_MATCHES:
        return

    def allowed(i: int, j: int) -> bool:
        return 0 <= j < len(chron) and _abs_diff(sample[i], chron[j]) <= tolerance[i]

    # 后缀松弛界: suf[(i,j,g,f)] = (后续最小差值和, 后续最小单点最大差值)
    # 两者各自独立取最小, 作为合法 (只放松不收紧) 的剪枝界。
    INF = 10**30
    suf: Dict[Tuple[int, int, int, int], Tuple[int, int]] = {
        (last_i, end, total_missing, total_false): (0, 0)
    }
    for i in range(last_i - 1, -1, -1):
        for j in range(j0, end):
            for g in range(total_missing + 1):
                for f in range(total_false + 1):
                    # 剩余年表步数 = 剩余样芯步数 + 剩余缺环 - 剩余伪环
                    if (end - j) != (last_i - i) + (total_missing - g) - (
                        total_false - f
                    ):
                        continue
                    best_sum = INF
                    best_max = INF
                    for step_i in range(1, total_false - f + 2):
                        ip = i + step_i
                        if ip > last_i:
                            break
                        df = step_i - 1
                        fp = f + df
                        for step_j in range(1, total_missing - g + 2):
                            jp = j + step_j
                            if jp > end:
                                break
                            dg = step_j - 1
                            gp = g + dg
                            if (end - jp) != (last_i - ip) + (total_missing - gp) - (
                                total_false - fp
                            ):
                                continue
                            q = suf.get((ip, jp, gp, fp))
                            if q is None or not allowed(ip, jp):
                                continue
                            d = _abs_diff(sample[ip], chron[jp])
                            if d + q[0] < best_sum:
                                best_sum = d + q[0]
                            cand_max = max(d, q[1])
                            if cand_max < best_max:
                                best_max = cand_max
                    if best_sum < INF:
                        suf[(i, j, g, f)] = (best_sum, best_max)

    def dfs(
        i: int,
        j: int,
        g: int,
        f: int,
        mx: int,
        sm: int,
        pairs: List[Pair],
    ) -> Iterable[Placement]:
        if i == last_i:
            if j == end and g == total_missing and f == total_false:
                yield Placement(
                    pairs=tuple(pairs),
                    missing=g,
                    false=f,
                    max_diff=mx,
                    sum_diff=sm,
                    span_start=pairs[0][1],
                )
            return
        successors: List[Tuple[int, int, int, int, int]] = []
        for step_i in range(1, total_false - f + 2):
            ip = i + step_i
            if ip > last_i:
                break
            df = step_i - 1
            fp = f + df
            for step_j in range(1, total_missing - g + 2):
                jp = j + step_j
                if jp > end:
                    break
                dg = step_j - 1
                gp = g + dg
                if (end - jp) != (last_i - ip) + (total_missing - gp) - (
                    total_false - fp
                ):
                    continue
                successors.append((jp, ip, gp, fp, dg + df))
        successors.sort()  # (年表位, 样芯环) 升序 => 键序 DFS
        for jp, ip, gp, fp, _skip in successors:
            if not allowed(ip, jp):
                continue
            d = _abs_diff(sample[ip], chron[jp])
            nmx = max(mx, d)
            nsm = sm + d
            if nmx > target_max or nsm > target_sum:
                continue
            q = suf.get((ip, jp, gp, fp))
            if q is None:
                continue
            if nsm + q[0] > target_sum or max(nmx, q[1]) > target_max:
                continue
            pairs.append((ip, jp))
            yield from dfs(ip, jp, gp, fp, nmx, nsm, pairs)
            pairs.pop()

    # 起点年表位固定为 j0; 首条样芯环 i0 之前全部计伪环, i0 升序即键序
    for i0 in range(total_false + 1):
        if i0 >= n:
            break
        if not allowed(i0, j0):
            continue
        d = _abs_diff(sample[i0], chron[j0])
        if d > target_max or d > target_sum:
            continue
        q = suf.get((i0, j0, 0, i0))
        if q is None:
            continue
        if d + q[0] > target_sum or max(d, q[1]) > target_max:
            continue
        pairs: List[Pair] = [(i0, j0)]
        yield from dfs(i0, j0, 0, i0, d, d, pairs)


# --------------------------------------------------------------------------- #
# 单芯独立证据
# --------------------------------------------------------------------------- #


@dataclass
class IndependentEvidence:
    feasible_alone: bool
    minimum_skips: Optional[int]
    optimal_end_indices: List[int]
    best_placement: Optional[Placement]
    reasons: List[str]


def _best_record(recs: List[Tuple[int, int, int, int]]) -> Tuple[int, int, int, int]:
    """(g,f,mx,sm) 中按 (g+f, mx, sm) 取最优。"""
    return min(recs, key=lambda r: (r[0] + r[1], r[2], r[3]))


def best_independent_placement(
    analysis: CoreAnalysis,
    sample: List[int],
    chron: List[int],
    tolerance: List[int],
) -> Tuple[Optional[Placement], Optional[int], List[int]]:
    """返回 (按键序的第一份独立最优放置, 最少跳环数, 达到该数的终点列表)。"""
    ends = analysis.feasible_ends()
    if not ends:
        return None, None, []
    min_skips = min(analysis.min_skips_at(t) for t in ends)  # type: ignore[arg-type]
    best_ends = [t for t in ends if analysis.min_skips_at(t) == min_skips]
    for end in best_ends:  # 终点升序, 内部枚举键序, 首个即全局键序最小
        g, f, mx, sm = _best_record(
            [r for r in analysis.end_records[end] if r[0] + r[1] == min_skips]
        )
        for placement in enumerate_paths(sample, chron, tolerance, end, g, f, mx, sm):
            return placement, min_skips, best_ends
    return None, min_skips, best_ends


def evidence_from_analysis(
    analysis: CoreAnalysis,
    sample: List[int],
    chron: List[int],
    tolerance: List[int],
) -> IndependentEvidence:
    """从已完成的单芯 DP 构造独立证据。"""
    placement, min_skips, best_ends = best_independent_placement(
        analysis, sample, chron, tolerance
    )
    if placement is not None:
        return IndependentEvidence(
            feasible_alone=True,
            minimum_skips=min_skips,
            optimal_end_indices=best_ends,
            best_placement=placement,
            reasons=[],
        )

    # 限额内无解: 放宽限额重试, 判断是跳环限额还是容差/匹配数问题
    relaxed = analyze_core(
        sample,
        chron,
        tolerance,
        min(RELAXED_QUOTA, len(chron)),
        min(RELAXED_QUOTA, len(sample) - MIN_MATCHES),
    )
    rel_placement, rel_min_skips, rel_best_ends = best_independent_placement(
        relaxed, sample, chron, tolerance
    )
    if rel_placement is not None:
        return IndependentEvidence(
            feasible_alone=False,
            minimum_skips=rel_min_skips,
            optimal_end_indices=rel_best_ends,
            best_placement=rel_placement,
            reasons=["skip_quota_exceeded"],
        )
    return IndependentEvidence(
        feasible_alone=False,
        minimum_skips=None,
        optimal_end_indices=[],
        best_placement=None,
        reasons=["no_tolerance_alignment"],
    )


def independent_evidence(
    sample: List[int],
    chron: List[int],
    tolerance: List[int],
    cap_missing: int,
    cap_false: int,
) -> IndependentEvidence:
    analysis = analyze_core(sample, chron, tolerance, cap_missing, cap_false)
    return evidence_from_analysis(analysis, sample, chron, tolerance)


# --------------------------------------------------------------------------- #
# 两芯联合求解
# --------------------------------------------------------------------------- #


@dataclass
class NoSolution:
    reason: str
    message: str
    evidence_a: IndependentEvidence
    evidence_b: IndependentEvidence


@dataclass
class Solution:
    total_skips: int
    max_diff: int
    sum_diff: int
    optimal_end_indices: List[int]
    witnesses: List[Tuple[Placement, Placement]]  # 1 份(唯一)或 2 份(歧义)
    ambiguous: bool


def _joint_stats(
    rec_a: Tuple[int, int, int, int], rec_b: Tuple[int, int, int, int]
) -> Tuple[int, int, int]:
    ga, fa, mxa, sma = rec_a
    gb, fb, mxb, smb = rec_b
    return (ga + fa + gb + fb, max(mxa, mxb), sma + smb)


def joint_align(
    chron: List[int],
    sample_a: List[int],
    sample_b: List[int],
    tolerance_a: List[int],
    tolerance_b: List[int],
    cap_missing_a: int = DEFAULT_QUOTA,
    cap_false_a: int = DEFAULT_QUOTA,
    cap_missing_b: int = DEFAULT_QUOTA,
    cap_false_b: int = DEFAULT_QUOTA,
    witness_limit: int = 2,
):
    """联合对齐两芯; 返回 Solution 或 NoSolution。两芯限额分别生效。"""
    ana_a = analyze_core(sample_a, chron, tolerance_a, cap_missing_a, cap_false_a)
    ana_b = analyze_core(sample_b, chron, tolerance_b, cap_missing_b, cap_false_b)

    ev_a = evidence_from_analysis(ana_a, sample_a, chron, tolerance_a)
    ev_b = evidence_from_analysis(ana_b, sample_b, chron, tolerance_b)

    if not ev_a.feasible_alone or not ev_b.feasible_alone:
        return NoSolution(
            reason="core_infeasible_under_limits",
            message=(
                "至少一支样芯在缺环/伪环限额、最少匹配环数与逐环容差下无法对入年表"
            ),
            evidence_a=ev_a,
            evidence_b=ev_b,
        )

    ends_a = set(ana_a.feasible_ends())
    ends_b = set(ana_b.feasible_ends())
    common_ends = sorted(ends_a & ends_b)
    if not common_ends:
        return NoSolution(
            reason="no_common_end_year",
            message="两支样芯各自可对入年表, 但可行终年集合没有交集, 无法落在同一日历年",
            evidence_a=ev_a,
            evidence_b=ev_b,
        )

    # 各共同终年下两芯记录组合的字典序最优统计量
    best_at: Dict[int, Tuple[int, int, int]] = {}
    best_stats: Optional[Tuple[int, int, int]] = None
    for end in common_ends:
        best_here: Optional[Tuple[int, int, int]] = None
        for ra in ana_a.end_records[end]:
            for rb in ana_b.end_records[end]:
                stats = _joint_stats(ra, rb)
                if best_here is None or stats < best_here:
                    best_here = stats
        assert best_here is not None
        best_at[end] = best_here
        if best_stats is None or best_here < best_stats:
            best_stats = best_here
    assert best_stats is not None
    optimal_ends = [end for end in common_ends if best_at[end] == best_stats]

    def end_witnesses(end: int):
        """按 (A 映射键, B 映射键) 稳定序惰性产生该终年内所有全局最优联合见证。

        A 侧各 (g,f,max,sum) 记录的路径生成器按键序归并; 对每份 A 放置再按需
        枚举 B 侧跳环数恰好互补的放置。取到两份即可判定歧义, 不全量物化。
        """
        target_skips, target_max, target_sum = best_stats
        a_records = [
            (g, f, mx, sm)
            for (g, f, mx, sm) in ana_a.end_records[end]
            if g + f <= target_skips and mx <= target_max and sm <= target_sum
        ]
        b_by_skips: Dict[int, List[Tuple[int, int, int, int]]] = {}
        for g, f, mx, sm in ana_b.end_records[end]:
            if g + f <= target_skips and mx <= target_max and sm <= target_sum:
                b_by_skips.setdefault(g + f, []).append((g, f, mx, sm))

        def a_stream(rec):
            g, f, mx, sm = rec
            for pa in enumerate_paths(
                sample_a, chron, tolerance_a, end, g, f, mx, sm
            ):
                yield pa.key(), pa

        a_iter = heap_merge(
            *(a_stream(rec) for rec in a_records), key=lambda x: x[0]
        )
        for ka, pa in a_iter:
            need_b = target_skips - pa.skips
            b_streams = []
            for g2, f2, mx2, sm2 in b_by_skips.get(need_b, ()):
                if max(pa.max_diff, mx2) != target_max:
                    continue
                if pa.sum_diff + sm2 != target_sum:
                    continue

                def b_stream(g2=g2, f2=f2, mx2=mx2, sm2=sm2):
                    for pb in enumerate_paths(
                        sample_b, chron, tolerance_b, end, g2, f2, mx2, sm2
                    ):
                        if max(pa.max_diff, pb.max_diff) != target_max:
                            continue
                        if pa.sum_diff + pb.sum_diff != target_sum:
                            continue
                        yield pb

                b_streams.append(b_stream())
            # 跨记录按 B 映射键序全局归并, 保证见证稳定有序
            for pb in heap_merge(*b_streams, key=lambda p: p.key()) if b_streams else ():
                yield (ka, pb.key()), pa, pb

    # 终年升序; 每个终年内部按键序 => 全局稳定序; 仅消费到第 witness_limit 份
    def all_ends():
        for end in optimal_ends:
            yield from end_witnesses(end)

    witnesses: List[Tuple[Placement, Placement]] = []
    for _key, pa, pb in all_ends():
        witnesses.append((pa, pb))
        if len(witnesses) >= witness_limit:
            break

    # 两份不同的同优见证 => 歧义; 只取到一份(已穷尽) => 唯一
    ambiguous = len(witnesses) >= 2

    return Solution(
        total_skips=best_stats[0],
        max_diff=best_stats[1],
        sum_diff=best_stats[2],
        optimal_end_indices=optimal_ends,
        witnesses=witnesses,
        ambiguous=ambiguous,
    )
