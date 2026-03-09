# ----------- Stage 1: Builder -----------
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --user -r requirements.txt

# ----------- Stage 2: Runtime -----------
FROM python:3.12-slim
WORKDIR /app
# Create non-root user
RUN useradd -m appuser
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
COPY app/ ./app/
COPY requirements.txt ./
RUN chown -R appuser:appuser /app /home/appuser/.local
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
