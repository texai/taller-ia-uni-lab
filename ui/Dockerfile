FROM python:3.12-slim

WORKDIR /app

COPY ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agente/ ./agente/
COPY ui/ ./ui/

ENV PYTHONPATH=/app
ENV RUTA_MEMORIA=/memoria

EXPOSE 8501

CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
