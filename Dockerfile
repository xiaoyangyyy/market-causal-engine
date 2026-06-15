FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY market_causal_engine ./market_causal_engine
COPY data ./data

RUN pip install --no-cache-dir -e ".[platform,api]"

EXPOSE 8080
CMD ["uvicorn", "market_causal_engine.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
