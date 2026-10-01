"""对齐算法测试: 规则、最优性、唯一性/歧义、无解证据, 以及对拍暴力枚举。"""

from __future__ import annotations

import itertools

import pytest

from app.alignment import (
    MIN_MATCHES,
    NoSolution,
    analyze_core,
    enumerate_paths,
    independent_evidence,
    joint_align,
)


# --------------------------------------------------------------------------- #
# 暴力参考实现: 直接枚举匹配位置组合
# --------------------------------------------------------------------------- #


def brute_placements(sample, chron, tol, cap_g, cap_f):
    """枚举单芯全部合法放置 (位置组合方式)。"""
    n, m = len(sample), len(chron)
    results = []
    # 选择样芯环子集与年表位子集, 等长、保序, 末环必须在内
    for k in range(MIN_MATCHES, n + 1):
        f = n - k
        if f > cap_f:
            continue
        for ring_combo in itertools.combinations(range(n), k):
            if ring_combo[-1] != n - 1:
                continue
            for g in range(0, cap_g + 1):
                span = k + g
                for start in range(0, m - span + 1):
                    # 缺环只能落在跨度内部相对位 1..span-2
                    for gap_combo in itertools.combinations(range(1, span - 1), g):
                        gaps = set(gap_combo)
                        chron_pos = [
                            start + t
                            for t in range(span)
                            if t not in gaps
                        ]
                        assert len(chron_pos) == k
                        diffs = [
                            abs(sample[r] - chron[c])
                            for r, c in zip(ring_combo, chron_pos)
                        ]
                        if all(d <= tol[r] for d, r in zip(diffs, ring_combo)):
                            results.append(
                                {
                                    "rings": ring_combo,
                                    "pos": tuple(chron_pos),
                                    "g": g,
                                    "f": f,
                                    "end": chron_pos[-1],
                                    "mx": max(diffs),
                                    "sm": sum(diffs),
                                }
                            )
    return results


def brute_joint(chron, sa, sb, ta, tb, cga, cfa, cgb, cfb):
    ra = brute_placements(sa, chron, ta, cga, cfa)
    rb = brute_placements(sb, chron, tb, cgb, cfb)
    by_end_b = {}
    for y in rb:
        by_end_b.setdefault(y["end"], []).append(y)

    best = None
    count = 0
    two_smallest = []  # 仅保留键序最小的两份, 避免笛卡尔积爆内存
    for x in ra:
        for y in by_end_b.get(x["end"], ()):
            stats = (
                x["g"] + x["f"] + y["g"] + y["f"],
                max(x["mx"], y["mx"]),
                x["sm"] + y["sm"],
            )
            if best is None or stats < best:
                best = stats
                count = 1
                two_smallest = [
                    (x["end"], tuple((c, r) for r, c in zip(x["rings"], x["pos"])),
                     tuple((c, r) for r, c in zip(y["rings"], y["pos"])))
                ]
            elif stats == best:
                count += 1
                key = (
                    x["end"],
                    tuple((c, r) for r, c in zip(x["rings"], x["pos"])),
                    tuple((c, r) for r, c in zip(y["rings"], y["pos"])),
                )
                two_smallest.append(key)
                two_smallest.sort()
                two_smallest = two_smallest[:2]
    if best is None:
        return None, ra, rb
    return (best, count, two_smallest), ra, rb


# --------------------------------------------------------------------------- #
# 基础构造
# --------------------------------------------------------------------------- #


def extract_series(chron, start, rings, gaps):
    """从年表造样芯: rings 个匹配环, gaps 为跨度内跳过的年表相对位(缺环)。"""
    span = rings + len(gaps)
    out = []
    gs = set(gaps)
    for t in range(span):
        if t in gs:
            continue
        out.append(chron[start + t])
    return out


def test_different_feasible_ends_no_common():
    chron = [100 + i % 7 * 3 for i in range(30)]
    sa = chron[5:17]  # 12 环
    sb = chron[9:21]  # 12 环
    # 限额 0/0、容差 0: A 终年 {16,23}, B 终年 {13,20,27}, 无交集
    res = joint_align(chron, sa, sb, [0] * 12, [0] * 12, 0, 0, 0, 0)
    assert isinstance(res, NoSolution)
    assert res.reason == "no_common_end_year"
    assert res.evidence_a.feasible_alone and res.evidence_b.feasible_alone
    assert res.evidence_a.optimal_end_indices == [16, 23]
    assert res.evidence_b.optimal_end_indices == [13, 20, 27]


def test_common_end_unique():
    chron = [100 + (i * 37 % 51) for i in range(30)]
    # A: 12 环终止于索引 19; B: 10 环也终止于索引 19
    sa = chron[8:20]
    sb = chron[10:20]
    res = joint_align(chron, sa, sb, [0] * 12, [0] * 10)
    assert not isinstance(res, NoSolution)
    pa, pb = res.witnesses[0]
    assert pa.end_index == pb.end_index == 19
    assert res.total_skips == 0
    assert res.max_diff == 0 and res.sum_diff == 0
    assert not res.ambiguous
    assert len(res.witnesses) == 1


def test_missing_and_false_rings():
    chron = [50 + (i * 13 % 47) for i in range(40)]
    # A: 10 匹配环, 跨度内跳过 2 个年表位 (缺环), 与 B 共同终止索引 25
    sa = extract_series(chron, 14, 10, gaps=[3, 7])
    assert len(sa) == 10
    # 插入 2 个伪环 (使用年表中不会出现的值, 容差 0)
    sa = sa[:4] + [999, 998] + sa[4:]
    tol = [0] * 12
    res = joint_align(chron, sa, chron[16:26], tol, [0] * 10)
    assert not isinstance(res, NoSolution)
    pa, pb = res.witnesses[0]
    assert pa.end_index == 25 and pb.end_index == 25
    assert pa.missing == 2 and pa.false == 2
    assert pa.max_diff == 0
    assert len(pa.pairs) == 10
    assert not res.ambiguous


def test_min_eight_matches_enforced():
    # 10 环样芯, 若跳过 3 个样芯项只剩 7 匹配 => 非法
    chron = list(range(25))
    sa = list(range(10))
    tol = [100] * 10
    ana = analyze_core(sa, chron, tol, 3, 3)
    # 所有可行终点记录的 f 必须 <= 2
    for end, recs in ana.end_records.items():
        for g, f, mx, sm in recs:
            assert f <= len(sa) - MIN_MATCHES


def test_tolerance_violation_rejected():
    chron = [0] * 25
    sa = [0] * 9 + [5]  # 末环差 5
    res = joint_align(chron, sa, [0] * 10, [0] * 10, [0] * 10)
    assert isinstance(res, NoSolution)
    assert res.evidence_a.reasons == ["no_tolerance_alignment"]


def test_skip_quota_evidence():
    chron = list(range(30))
    # 样芯需要至少 4 个伪环才能对齐 (限额 3)
    sa = [99, 98, 97, 96] + list(range(10))
    sb = list(range(10))
    # 年表中 0..9 在位置 0..9; A 前 4 环必须作为伪环 => 需要 4 > 3
    res = joint_align(chron, sa, sb, [0] * 14, [0] * 10, 3, 3, 3, 3)
    assert isinstance(res, NoSolution)
    assert res.evidence_a.feasible_alone is False
    assert "skip_quota_exceeded" in res.evidence_a.reasons
    assert res.evidence_a.minimum_skips == 4


def test_objective_order_prefers_fewer_skips():
    # 构造: 有跳环可减小差值, 但无跳环对齐本身在容差内 => 必须选 0 跳环
    chron = [0, 10, 1, 9, 2, 8, 3, 7, 4, 6] + [0] * 20
    sa = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    sb = sa[:]
    # 无跳环对齐 (chron 0,2,4,..18 值为 0,1,2,3,4,0,0,0,0,0) 差值大;
    # 但题目规则先最小化跳环数, 所以只要无跳环可行就不得跳环
    tol = [100] * 10
    res = joint_align(chron, sa, sb, tol, tol)
    assert not isinstance(res, NoSolution)
    assert res.total_skips == 0


def test_ambiguity_detected():
    # 常量年表 + 常量样芯, 大容差 => 大量同分映射, 必歧义; 前两份按映射序
    chron = [7] * 30
    sa = [7] * 12
    sb = [7] * 12
    res = joint_align(chron, sa, sb, [0] * 12, [0] * 12)
    assert not isinstance(res, NoSolution)
    assert res.ambiguous
    assert len(res.witnesses) == 2
    w1, w2 = res.witnesses
    k1 = (w1[0].key(), w1[1].key())
    k2 = (w2[0].key(), w2[1].key())
    assert k1 < k2
    # 0 跳环时每个终年仅一种放置; 歧义来自不同终年 => 终年不同
    assert w1[0].end_index != w2[0].end_index


def test_witness_order_within_end():
    # 同一终年内存在多个 0 差值映射 => 见证按映射序
    chron = [5] * 30
    sa = [5] * 10
    sb = [5] * 10
    res = joint_align(chron, sa, sb, [0] * 10, [0] * 10)
    assert res.ambiguous
    pa1, pb1 = res.witnesses[0]
    pa2, pb2 = res.witnesses[1]
    # 不同终年; 终年更小者排前
    assert pa1.end_index < pa2.end_index


def test_enumerate_paths_matches_brute():
    sample = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
    chron = [3, 0, 1, 4, 1, 5, 9, 0, 2, 6, 5, 3, 8, 7, 9, 3, 2, 3, 8, 4,
             0, 1, 2, 5, 7, 6, 0, 1]
    tol = [1] * 10
    end = 11
    # 枚举 g=1,f=0 目标 (mx,sm) 不限 (用足够大的目标)
    paths = list(enumerate_paths(sample, chron, tol, end, 1, 0, 100, 1000))
    brute = [
        p for p in brute_placements(sample, chron, tol, 1, 0)
        if p["end"] == end and p["g"] == 1
    ]
    assert len(paths) == len(brute)
    # 键序
    keys = [p.key() for p in paths]
    assert keys == sorted(keys)
    for p in paths:
        assert p.missing == 1 and p.false == 0


def test_enumerate_paths_with_false_rings_brute():
    sample = [9, 3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 0]
    chron = [3, 0, 1, 4, 1, 5, 9, 0, 2, 6, 5, 3, 8, 7, 9, 3, 2, 3, 8, 4]
    tol = [2] * 12
    end = 11
    paths = list(enumerate_paths(sample, chron, tol, end, 0, 2, 100, 1000))
    brute = [
        p for p in brute_placements(sample, chron, tol, 0, 2)
        if p["end"] == end and p["f"] == 2
    ]
    assert len(paths) == len(brute)
    keys = [p.key() for p in paths]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------- #
# 随机对拍
# --------------------------------------------------------------------------- #


def test_random_vs_bruteforce():
    import random

    rng = random.Random(20261001)
    for trial in range(60):
        m = rng.randint(10, 16)  # 小规模对拍
        chron = [rng.randint(0, 9) for _ in range(m)]
        na = rng.randint(8, 10)
        nb = rng.randint(8, 10)
        sa = [rng.randint(0, 9) for _ in range(na)]
        sb = [rng.randint(0, 9) for _ in range(nb)]
        ta = [rng.randint(0, 3) for _ in range(na)]
        tb = [rng.randint(0, 3) for _ in range(nb)]
        caps = (1, 1, 1, 1) if trial % 2 else (2, 2, 2, 2)

        expected, _, _ = brute_joint(chron, sa, sb, ta, tb, *caps)
        res = joint_align(chron, sa, sb, ta, tb, *caps)

        if expected is None:
            assert isinstance(res, NoSolution), trial
            continue
        best, count, two_smallest = expected
        assert not isinstance(res, NoSolution), trial
        assert (res.total_skips, res.max_diff, res.sum_diff) == best, trial
        assert res.ambiguous == (count >= 2), (trial, res.ambiguous, count)
        pa, pb = res.witnesses[0]
        assert (pa.end_index, pa.key(), pb.key()) == two_smallest[0], trial
        if res.ambiguous:
            pa2, pb2 = res.witnesses[1]
            assert (pa2.end_index, pa2.key(), pb2.key()) == two_smallest[1], trial


def test_random_high_caps_vs_bruteforce():
    """满额 3 缺环/伪环 + 中等容差: 覆盖跨 Pareto 记录的见证排序。"""
    import random

    rng = random.Random(424242)
    caps = (3, 3, 3, 3)
    for trial in range(30):
        m = rng.randint(14, 18)
        chron = [rng.randint(0, 9) for _ in range(m)]
        na = rng.randint(10, 11)
        nb = rng.randint(10, 11)
        sa = [rng.randint(0, 9) for _ in range(na)]
        sb = [rng.randint(0, 9) for _ in range(nb)]
        ta = [rng.randint(1, 6) for _ in range(na)]
        tb = [rng.randint(1, 6) for _ in range(nb)]

        expected, _, _ = brute_joint(chron, sa, sb, ta, tb, *caps)
        res = joint_align(chron, sa, sb, ta, tb, *caps)
        if expected is None:
            assert isinstance(res, NoSolution), trial
            continue
        best, count, two_smallest = expected
        assert not isinstance(res, NoSolution), trial
        assert (res.total_skips, res.max_diff, res.sum_diff) == best, trial
        assert res.ambiguous == (count >= 2), (trial, res.ambiguous, count)
        pa, pb = res.witnesses[0]
        assert (pa.end_index, pa.key(), pb.key()) == two_smallest[0], trial
        if res.ambiguous:
            pa2, pb2 = res.witnesses[1]
            assert (pa2.end_index, pa2.key(), pb2.key()) == two_smallest[1], trial


def test_independent_evidence_feasible():
    chron = list(range(25))
    sa = list(range(5, 15))
    ev = independent_evidence(sa, chron, [0] * 10, 3, 3)
    assert ev.feasible_alone
    assert ev.minimum_skips == 0
    assert ev.best_placement.end_index == 14
