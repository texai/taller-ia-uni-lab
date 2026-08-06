FROM python:3.12-slim

WORKDIR /app

COPY agente/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agente/ ./agente/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV RUTA_MEMORIA=/memoria

# El agente se construye durante el taller.
CMD ["sleep", "infinity"]
