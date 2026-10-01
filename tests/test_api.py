"""HTTP 层测试: 健康检查、成功响应、校验错误、无解证据。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


CHRON = [100 + (i * 13 % 47) for i in range(30)]
# A: 12 环终止于索引 19; B: 10 环也终止于索引 19
A = CHRON[8:20]
B = CHRON[10:20]


def payload(**overrides):
    body = {
        "chronology": CHRON,
        "chron_start_year": 1900,
        "core_a": {"sample": A, "tolerance": [0] * 12},
        "core_b": {"sample": B, "tolerance": [0] * 10},
    }
    body.update(overrides)
    return body


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_align_success_structure():
    r = client.post("/api/dendro/align", json=payload())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "optimal"
    assert data["unique"] is True
    assert data["ambiguity"] == "unique"
    assert data["end_year"] == 1919
    assert data["optimal_end_years"] == [1919]
    assert data["total_skips"] == 0
    assert data["max_diff"] == 0
    assert data["sum_diff"] == 0
    assert data["witness_count_returned"] == 1
    assert len(data["witnesses"]) == 1

    m = data["mapping"]
    assert m["end_year"] == 1919
    assert m["core_a"]["matched_count"] == 12
    assert m["core_b"]["matched_count"] == 10
    assert m["core_a"]["missing_ring_count"] == 0
    assert m["core_a"]["false_ring_count"] == 0
    # 末环匹配
    last_a = m["core_a"]["matches"][-1]
    last_b = m["core_b"]["matches"][-1]
    assert last_a["year"] == last_b["year"] == 1919
    # 逐环映射内容
    assert last_a["sample_value"] == CHRON[19] == last_a["chron_value"]


def test_align_ambiguous_returns_two_witnesses():
    chron = [7] * 30
    body = {
        "chronology": chron,
        "chron_start_year": 1900,
        "core_a": {"sample": [7] * 12, "tolerance": [0] * 12},
        "core_b": {"sample": [7] * 12, "tolerance": [0] * 12},
    }
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["unique"] is False and data["ambiguity"] == "ambiguous"
    assert len(data["witnesses"]) == 2
    assert data["witnesses"][0]["end_year"] < data["witnesses"][1]["end_year"]


def test_chronology_too_short():
    body = payload(chronology=[1] * 24)
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 422
    data = r.json()
    assert data["status"] == "validation_error"
    assert "25" in str(data["errors"])


def test_chronology_too_long():
    r = client.post("/api/dendro/align", json=payload(chronology=[1] * 61))
    assert r.status_code == 422


def test_sample_length_bounds():
    bad_a = {"sample": A[1:], "tolerance": [0] * 11}  # 11 环仍然合法; 改成 9
    bad_a = {"sample": A[:9], "tolerance": [0] * 9}
    body = payload(core_a=bad_a)
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 422


def test_sample_max_length():
    body = payload(
        core_a={"sample": [1] * 25, "tolerance": [0] * 25},
    )
    assert client.post("/api/dendro/align", json=body).status_code == 422
    ok = payload(
        core_a={"sample": [1] * 24, "tolerance": [0] * 24},
    )
    # 24 环本身通过长度校验 (能否对齐是求解层的事)
    assert client.post("/api/dendro/align", json=ok).status_code in (200, 409)


def test_tolerance_length_mismatch():
    body = payload(core_a={"sample": A, "tolerance": [0] * 11})
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 422
    assert "容差" in str(r.json()["errors"])


def test_negative_tolerance_rejected():
    body = payload(core_a={"sample": A, "tolerance": [-1] * 12})
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 422


def test_quota_out_of_range():
    body = payload(core_a={"sample": A, "tolerance": [0] * 12, "missing_ring_limit": 4})
    assert client.post("/api/dendro/align", json=body).status_code == 422
    body = payload(core_b={"sample": B, "tolerance": [0] * 10, "false_ring_limit": -1})
    assert client.post("/api/dendro/align", json=body).status_code == 422


def test_missing_field():
    body = payload()
    del body["core_b"]
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 422


def test_no_solution_common_end_with_evidence():
    # 周期 7 的年表 => 限额 0/0、容差 0 下
    # A(12 环, 8≡1 mod 7) 终年 {12,19,26}; B(9≡2 mod 7) 终年 {13,20,27}
    chron7 = [100 + (i % 7) * 3 for i in range(30)]
    a7 = chron7[8:20]
    b7 = chron7[9:21]
    body = {
        "chronology": chron7,
        "chron_start_year": 1900,
        "core_a": {
            "sample": a7,
            "tolerance": [0] * 12,
            "missing_ring_limit": 0,
            "false_ring_limit": 0,
        },
        "core_b": {
            "sample": b7,
            "tolerance": [0] * 12,
            "missing_ring_limit": 0,
            "false_ring_limit": 0,
        },
    }
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 409
    data = r.json()
    assert data["status"] == "no_solution"
    assert data["reason"] == "no_common_end_year"
    assert data["evidence_a"]["feasible_alone"] is True
    assert data["evidence_b"]["feasible_alone"] is True
    assert data["evidence_a"]["optimal_end_years_alone"] == [1912, 1919, 1926]
    assert data["evidence_b"]["optimal_end_years_alone"] == [1913, 1920, 1927]


def test_no_solution_quota_evidence():
    chron = list(range(30))
    sa = [99, 98, 97, 96] + list(range(10))
    body = {
        "chronology": chron,
        "chron_start_year": 1900,
        "core_a": {"sample": sa, "tolerance": [0] * 14},
        "core_b": {"sample": list(range(10)), "tolerance": [0] * 10},
    }
    r = client.post("/api/dendro/align", json=body)
    assert r.status_code == 409
    data = r.json()
    assert data["reason"] == "core_infeasible_under_limits"
    ev_a = data["evidence_a"]
    assert ev_a["feasible_alone"] is False
    assert "skip_quota_exceeded" in ev_a["infeasible_reasons"]
    assert ev_a["minimum_skips"] == 4
    # 放宽限额后的独立最优映射作为证据
    assert ev_a["independent_mapping"]["matched_count"] == 10
