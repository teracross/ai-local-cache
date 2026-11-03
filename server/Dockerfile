FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

# Supplied at runtime via docker-compose / root .env
ENV CLOUDFLARE_API_TOKEN="" \
    CLOUDFLARE_ACCOUNT_ID="" \
    CLOUDFLARE_AI_MODEL=""

EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=20 --start-period=5s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
