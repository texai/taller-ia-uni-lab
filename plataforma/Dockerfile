FROM python:3.12-slim

WORKDIR /app

COPY plataforma/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY plataforma/ ./plataforma/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV RUTA_DATOS=/datos

EXPOSE 8000

CMD ["uvicorn", "plataforma.api:app", "--host", "0.0.0.0", "--port", "8000"]
