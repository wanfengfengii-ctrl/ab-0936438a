"""一次性冒烟: 命中健康检查 + 两芯联合对齐成功/歧义/无解/校验错误。

由 verify 容器在 app 服务健康后运行, 任一步失败即以非零退出码退出。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("APP_URL", "http://app:8000").rstrip("/")


def request(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        print(f"[SMOKE] FAIL: {name} {detail}")
        sys.exit(1)
    print(f"[SMOKE] ok: {name}")


def main() -> None:
    code, data = request("GET", "/health")
    check("health 200", code == 200 and data.get("status") == "ok", str(data))

    chron = [100 + (i * 13 % 47) for i in range(30)]
    a = chron[8:20]      # 12 环, 唯一终年索引 19
    b = chron[10:20]     # 10 环, 同一终年
    payload = {
        "chronology": chron,
        "chron_start_year": 1900,
        "core_a": {"sample": a, "tolerance": [0] * 12},
        "core_b": {"sample": b, "tolerance": [0] * 10},
    }
    code, data = request("POST", "/api/dendro/align", payload)
    check("align 200", code == 200, f"status={code} body={data}")
    check("unique optimal", data["status"] == "optimal" and data["unique"] is True)
    check("common end year 1919", data["end_year"] == 1919, str(data.get("end_year")))
    check("zero skips/diffs", data["total_skips"] == 0 and data["sum_diff"] == 0)
    ma, mb = data["mapping"]["core_a"], data["mapping"]["core_b"]
    check(
        "both last rings matched same year",
        ma["matches"][-1]["year"] == mb["matches"][-1]["year"] == 1919,
    )
    check("min matches respected", ma["matched_count"] == 12 and mb["matched_count"] == 10)

    # 歧义: 常量年表/样芯
    amb = {
        "chronology": [7] * 30,
        "chron_start_year": 1900,
        "core_a": {"sample": [7] * 12, "tolerance": [0] * 12},
        "core_b": {"sample": [7] * 12, "tolerance": [0] * 12},
    }
    code, data = request("POST", "/api/dendro/align", amb)
    check("ambiguous 200", code == 200 and data["ambiguity"] == "ambiguous")
    check("two stable witnesses", data["witness_count_returned"] == 2)
    check(
        "witnesses in mapping order",
        data["witnesses"][0]["end_year"] < data["witnesses"][1]["end_year"],
    )

    # 无解: 周期 7 年表, 两芯终年集合不相交
    c7 = [100 + (i % 7) * 3 for i in range(30)]
    nosol = {
        "chronology": c7,
        "chron_start_year": 1900,
        "core_a": {"sample": c7[8:20], "tolerance": [0] * 12,
                   "missing_ring_limit": 0, "false_ring_limit": 0},
        "core_b": {"sample": c7[9:21], "tolerance": [0] * 12,
                   "missing_ring_limit": 0, "false_ring_limit": 0},
    }
    code, data = request("POST", "/api/dendro/align", nosol)
    check("no solution 409", code == 409 and data["status"] == "no_solution")
    check("evidence for both cores", data["evidence_a"]["feasible_alone"] is True
          and data["evidence_b"]["feasible_alone"] is True)
    check("disjoint end sets shown",
          data["evidence_a"]["optimal_end_years_alone"]
          != data["evidence_b"]["optimal_end_years_alone"])

    # 校验错误
    bad = dict(payload, chronology=[1] * 24)
    code, data = request("POST", "/api/dendro/align", bad)
    check("validation 422", code == 422 and data["status"] == "validation_error")

    print("[SMOKE] ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
