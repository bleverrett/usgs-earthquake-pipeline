FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg
WORKDIR /app
COPY requirements.lock .
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && python -m pip check
COPY . .
CMD ["python", "main.py"]