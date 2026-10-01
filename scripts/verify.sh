#!/usr/bin/env sh
# verify 一次性服务入口: 代码测试 -> 应用构建检查 -> 两芯联合对齐 API 冒烟。
# 依赖 compose 的 depends_on(service_healthy), 运行到此处时 app 必然已健康。
set -eu

cd /srv

echo "== [1/3] 代码测试 =="
python -m pytest -q

echo "== [2/3] 应用构建检查: compileall + 模块导入 =="
python -m compileall -q app
python -c "import app.main; print('app import ok')"

echo "== [3/3] 两芯联合对齐 API 冒烟 =="
python scripts/smoke.py

echo "== VERIFY PASSED =="
