# 木构文物两芯联合树轮定年服务

同一根梁材的两支树芯**共同对入**地区年表，避免两支分别寻找最佳位置后得到
互相矛盾的砍伐年代。

## 规则与目标

- 两支样芯的**末环都必须匹配**，且落在年表的**同一日历年**（共同终年）。
- **缺环**：样芯跨度内跳过年表项；**伪环**：跳过样芯项（含首条匹配之前的环）。
  每支缺环、伪环各最多 3 个（可在请求中下调到 0–3），每支至少匹配 8 环。
- 每次匹配要求 `|样芯指数 − 年表指数| ≤ 该环容差`（逐环容差）。
- 优化按字典序依次最小化：
  1. 两芯缺环与伪环总数；
  2. 全部匹配的最大绝对差值；
  3. 全部匹配绝对差值之和。
- 对全部同优映射判定 **唯一 / 歧义**，返回共同终年、逐环映射、跳过项，以及
  按映射序列 `(年表位, 样芯环)` 稳定字典序的**前两份见证**。

无法满足时：

- 某支在限额 / 最少匹配环数 / 容差下无法对入；
- 两支各自可行但可行终年集合不相交（无共同终年）；

服务返回 `409 no_solution`，并附两支样芯的独立证据（独立可行终年、独立最少
跳环数、限额放宽后的最优映射或无解原因）。

## 接口

`POST /api/dendro/align`

```json
{
  "chronology": [/* 25–60 个整数生长指数 */],
  "chron_start_year": 1900,
  "core_a": {
    "sample": [/* 10–24 环整数指数, 索引 0 为最内环(最早年) */],
    "tolerance": [/* 与 sample 等长的非负逐环容差 */],
    "missing_ring_limit": 3,
    "false_ring_limit": 3
  },
  "core_b": { "...": "同 core_a" }
}
```

成功 `200`：`end_year`（共同终年）、`mapping`（逐环匹配、缺环年份、伪环环号）、
`unique / ambiguity`、`total_skips / max_diff / sum_diff`、`witnesses`（1 或 2 份）。

无解 `409`：`reason`（`no_common_end_year` / `core_infeasible_under_limits`）
及 `evidence_a`、`evidence_b`。

入参越界返回 `422 validation_error` 与明确的中文错误信息。

健康检查：`GET /health` → `{"status":"ok"}`（另有 `/docs` Swagger 页面）。

## 运行

宿主机端口通过 `HOST_PORT` 配置（默认 8000）：

```bash
HOST_PORT=18000 docker compose up -d --build app
curl http://localhost:18000/health
```

## 一次性 verify 服务

`verify` 在 `app` **健康之后**才启动，依次执行：

1. 代码测试（`pytest`）；
2. 应用构建检查（字节码编译 + 应用导入）；
3. 两芯联合对齐 API 冒烟（成功唯一 / 歧义双见证 / 无解决据 / 校验错误）；

并以容器退出码报告成败：

```bash
docker compose build
docker compose run --rm verify   # 退出码 0 成功, 非 0 失败
```

## 本地开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --port 8000
```

## 目录

```
app/alignment.py   单芯 Pareto-DP、两芯联合寻优、键序见证枚举、无解证据
app/schemas.py     请求/响应模型与边界校验
app/main.py        FastAPI 路由与结果序列化
tests/             算法对拍(含暴力枚举)与 HTTP 层测试
scripts/smoke.py   容器内 API 冒烟
scripts/verify.sh  verify 一次性服务入口
```
