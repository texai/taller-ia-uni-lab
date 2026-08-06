FROM python:3.12-slim

WORKDIR /app

# La interfaz corre el agente en vivo, asi que necesita sus dependencias. Se
# instalan desde el mismo archivo que usa el contenedor del agente para que no
# existan dos listas que se puedan desincronizar.
COPY agente/requirements.txt ./requirements-agente.txt
COPY ui/requirements.txt ./requirements-ui.txt
RUN pip install --no-cache-dir -r requirements-agente.txt -r requirements-ui.txt

COPY agente/ ./agente/
COPY ui/ ./ui/

ENV PYTHONPATH=/app
ENV RUTA_MEMORIA=/memoria

EXPOSE 8501

CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
