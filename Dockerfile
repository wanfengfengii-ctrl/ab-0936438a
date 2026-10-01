FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=8000

WORKDIR /srv

# 系统层无额外依赖; 先装 Python 依赖以利用层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
RUN chmod +x scripts/verify.sh scripts/smoke.py

# 非 root 运行
RUN useradd --create-home --uid 10001 app && chown -R app:app /srv
USER app

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
    CMD python -c "import json,os,urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:%s/health'%os.environ.get('APP_PORT','8000'),timeout=3); sys.exit(0 if json.load(r).get('status')=='ok' else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
