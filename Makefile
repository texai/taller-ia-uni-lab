.DEFAULT_GOAL := ayuda

# Compose v2 es un plugin de docker ("docker compose"); v1 es un binario
# aparte ("docker-compose"). Detectamos cual existe para no obligar a nadie a
# reinstalar Docker el sabado por la manana.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" \
                   || (command -v docker-compose >/dev/null 2>&1 && echo "docker-compose") \
                   || echo "NO_COMPOSE")

ifeq ($(COMPOSE),NO_COMPOSE)
$(warning )
$(warning No encuentro Docker Compose. Instala Docker Desktop, que lo trae incluido:)
$(warning   https://www.docker.com/products/docker-desktop/)
$(warning Verifica luego con:  docker compose version)
$(warning )
$(error Falta Docker Compose)
endif
EN_PLATAFORMA := $(COMPOSE) run --rm plataforma python -m plataforma
EN_AGENTE := $(COMPOSE) run --rm agente python -m agente

.PHONY: ayuda arriba abajo estado logs seed datos entrenar pronosticar metricas \
        agente pelado memoria actuar ui romper reparar mlflow ollama reset

ayuda:  ## Muestra esta ayuda
	@echo "Taller 02 de caso aplicado de IA en industria"
	@echo
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

arriba:  ## Levanta la plataforma y la interfaz
	@docker info >/dev/null 2>&1 || ( \
	  echo ""; \
	  echo "Docker no esta corriendo."; \
	  echo "Abre Docker Desktop, espera a que termine de arrancar, y reintenta."; \
	  echo ""; \
	  exit 1 )
	# Construye las TRES imagenes, no solo las dos que se levantan. El
	# contenedor del agente no corre como servicio, asi que sin esto su
	# construccion queda pendiente y le cae encima al alumno la primera vez que
	# lo usa -- que es en plena clase, no durante el trabajo previo.
	$(COMPOSE) build
	$(COMPOSE) up -d plataforma ui

abajo:  ## Apaga todo
	$(COMPOSE) down

estado:  ## Que esta corriendo
	$(COMPOSE) ps

logs:  ## Sigue los logs (SERVICIO=agente para uno solo)
	$(COMPOSE) logs -f $(SERVICIO)

seed:  ## Pipeline completo: datos, entrenamiento, pronostico y metricas
	$(EN_PLATAFORMA) seed

datos:  ## Genera el historico de ventas
	$(EN_PLATAFORMA) datos

entrenar:  ## Entrena los 192 modelos
	$(EN_PLATAFORMA) entrenar

pronosticar:  ## Corre el job batch de pronostico
	$(EN_PLATAFORMA) pronosticar

metricas:  ## Cruza pronostico contra realidad
	$(EN_PLATAFORMA) metricas

agente:  ## Una ejecucion del agente. ARGS="--verboso --fecha 2026-08-08"
	$(EN_AGENTE) run $(ARGS)

pelado:  ## El bucle ReAct del reto 3: un LLM con herramientas y nada mas
	$(EN_AGENTE) pelado $(ARGS)

memoria:  ## Que recuerda el agente. ARGS="--limpiar" para borrarla
	$(EN_AGENTE) memoria $(ARGS)

actuar:  ## Ejecucion CON permiso para reentrenar de verdad. Ojo con lo que pides
	$(COMPOSE) run --rm -e EJECUTAR_ACCIONES=1 agente python -m agente run $(ARGS)

verificar:  ## Comprueba que todo funciona. ARGS="--con-llm" para la version completa
	$(COMPOSE) run --rm agente python -m retos.verificar $(ARGS)

ui:  ## Abre la interfaz en http://localhost:8501
	$(COMPOSE) up -d ui
	@echo "http://localhost:8501"

romper:  ## Degrada los datos, rompe el mundo. Uso: make romper ESCENARIO=sesgo_silencioso
	$(EN_PLATAFORMA) escenario --nombre $(ESCENARIO)
	$(MAKE) pronosticar
	$(MAKE) metricas

reparar:  ## Regenera los datos limpios, vuelve al mundo sano
	$(EN_PLATAFORMA) datos
	$(MAKE) pronosticar
	$(MAKE) metricas

mlflow:  ## Registro de modelos en http://localhost:5000
	$(COMPOSE) --profile mlflow up -d mlflow
	@echo "http://localhost:5000"

ollama:  ## Modelo local, para quien no tenga llave
	$(COMPOSE) --profile local up -d ollama
	$(COMPOSE) exec ollama ollama pull qwen2.5:3b-instruct

reset:  ## Boton de panico: borra todo y reconstruye desde cero
	$(COMPOSE) down -v
	$(COMPOSE) up -d plataforma ui
	$(MAKE) seed
