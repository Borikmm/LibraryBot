FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && useradd --uid 10001 --create-home librarybot
COPY bot ./bot
COPY migrations ./migrations
COPY assets ./assets
COPY scripts/data ./scripts/data
COPY main.py app.py ./
USER 10001:10001
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/health', timeout=4)" || exit 1
CMD ["python", "main.py"]
