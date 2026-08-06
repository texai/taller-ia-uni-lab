.DEFAULT_GOAL := ayuda
COMPOSE := docker compose
EN_PLATAFORMA := $(COMPOSE) run --rm plataforma python -m plataforma
EN_AGENTE := $(COMPOSE) run --rm agente python -m agente

.PHONY: ayuda arriba abajo estado logs seed datos entrenar pronosticar metricas \
        agente ui romper reparar mlflow ollama reset

ayuda:  ## Muestra esta ayuda
	@echo "Taller 02 de caso aplicado de IA en industria"
	@echo
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

arriba:  ## Levanta la plataforma y la interfaz
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

agente:  ## Una corrida del agente
	$(EN_AGENTE) run

ui:  ## Abre la interfaz en http://localhost:8501
	$(COMPOSE) up -d ui
	@echo "http://localhost:8501"

romper:  ## Degrada el mundo. Uso: make romper ESCENARIO=sesgo_silencioso
	$(EN_PLATAFORMA) escenario --nombre $(ESCENARIO)
	$(MAKE) pronosticar
	$(MAKE) metricas

reparar:  ## Vuelve al mundo sano
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
