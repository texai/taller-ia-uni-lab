FROM python:3.12-slim

WORKDIR /app

COPY plataforma/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY plataforma/ ./plataforma/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV RUTA_DATOS=/datos

EXPOSE 8000

# --reload porque ./plataforma viene montada desde el disco de quien lo corre:
# sin esto uvicorn sirve para siempre el codigo con el que arranco el
# contenedor, y despues de un `git pull` la API responde 404 a rutas que ya
# existen en el archivo. Averiguar eso en clase cuesta mas que el watcher.
CMD ["uvicorn", "plataforma.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/plataforma"]
