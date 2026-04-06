FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1
CMD exec gunicorn --bind :${PORT:-8000} --workers 4 --threads 8 --worker-class gthread --timeout 300 --access-logfile - --error-logfile - app:app
