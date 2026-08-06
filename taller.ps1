<#
.SYNOPSIS
    Los comandos del taller, para Windows. Equivalente al Makefile.

.DESCRIPTION
    macOS y Linux usan `make`. Windows no lo trae, y obligar a veinte personas
    a montar WSL2 antes de la clase es una forma cara de perder la primera
    hora. Este script hace exactamente lo mismo desde PowerShell, con Docker
    Desktop y nada mas.

    Las dos rutas corren los mismos contenedores y producen los mismos
    resultados: `make arriba` y `.\taller.ps1 arriba` son el mismo comando.

.EXAMPLE
    .\taller.ps1                      # lista los comandos
    .\taller.ps1 arriba
    .\taller.ps1 seed
    .\taller.ps1 verificar
    .\taller.ps1 agente --verboso
    .\taller.ps1 romper sesgo_silencioso
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Comando = 'ayuda',

    # Todo lo que venga despues se pasa tal cual al comando de adentro.
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Resto
)

$ErrorActionPreference = 'Stop'

# Corre siempre desde la carpeta del script, no desde donde se invoco.
Set-Location -Path $PSScriptRoot

# --------------------------------------------------------------------------

function Get-Compose {
    <#  Compose v2 es un plugin ("docker compose"); v1 es un binario aparte
        ("docker-compose"). Detectamos cual hay para no obligar a nadie a
        reinstalar Docker el sabado por la manana. #>
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "No encuentro Docker." -ForegroundColor Red
        Write-Host "Instala Docker Desktop:  https://www.docker.com/products/docker-desktop/"
        Write-Host ""
        exit 1
    }

    # Que el CLIENTE exista no significa que el MOTOR este vivo: `docker` y
    # `docker compose version` responden perfectamente con Docker Desktop
    # cerrado. Sin esta comprobacion, el primer comando real falla con un
    # mensaje sobre un named pipe que no le dice nada a nadie.
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Docker Desktop no esta corriendo." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  1. Abrelo desde el menu Inicio"
        Write-Host "  2. Espera a que el icono de la ballena deje de moverse"
        Write-Host "  3. Vuelve a correr este comando"
        Write-Host ""
        exit 1
    }

    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) { return @('docker', 'compose') }

    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        return @('docker-compose')
    }

    Write-Host ""
    Write-Host "No encuentro Docker Compose." -ForegroundColor Red
    Write-Host "Instala Docker Desktop, que lo trae incluido:"
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    Write-Host "Verifica luego con:  docker compose version"
    Write-Host ""
    exit 1
}

# Se resuelve la primera vez que hace falta, no al arrancar: asi `.\taller.ps1`
# sin argumentos muestra la ayuda aunque todavia no tengas Docker instalado,
# que es justo el momento en que mas falta hace leerla.
$script:COMPOSE = $null

function Invoke-Compose {
    <#  Recibe UN arreglo, no argumentos sueltos. Con
        ValueFromRemainingArguments, PowerShell intenta enlazar los tokens que
        parecen nombres de parametro -- "-d", "-f", "-e" -- y se los traga en
        silencio: `up -d` terminaba ejecutandose como `up`, dejando los
        contenedores en primer plano. Un arreglo explicito no es ambiguo. #>
    param([string[]]$ComposeArgs)

    if (-not $script:COMPOSE) { $script:COMPOSE = Get-Compose }
    $todos = $script:COMPOSE + $ComposeArgs
    & $todos[0] @($todos[1..($todos.Length - 1)])
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-Plataforma {
    param([string[]]$SubArgs)
    Invoke-Compose (@('run', '--rm', 'plataforma', 'python', '-m', 'plataforma') + $SubArgs)
}

function Invoke-Agente {
    param([string[]]$SubArgs)
    Invoke-Compose (@('run', '--rm', 'agente', 'python', '-m', 'agente') + $SubArgs)
}

$COMANDOS = [ordered]@{
    'arriba'      = 'Levanta la plataforma y la interfaz'
    'abajo'       = 'Apaga todo'
    'estado'      = 'Que esta corriendo'
    'logs'        = 'Sigue los logs'
    'seed'        = 'Pipeline completo: datos, entrenamiento, pronostico y metricas'
    'datos'       = 'Genera el historico de ventas'
    'entrenar'    = 'Entrena los 192 modelos'
    'pronosticar' = 'Corre el job batch de pronostico'
    'metricas'    = 'Cruza pronostico contra realidad'
    'agente'      = 'Una corrida del agente. Acepta --verboso y --fecha'
    'memoria'     = 'Que recuerda el agente. --limpiar para borrarla'
    'actuar'      = 'Corrida CON permiso para reentrenar de verdad'
    'verificar'   = 'Comprueba que todo funciona. --con-llm para la version completa'
    'ui'          = 'Abre la interfaz en http://localhost:8501'
    'romper'      = 'Degrada el mundo. Uso: .\taller.ps1 romper sesgo_silencioso'
    'reparar'     = 'Vuelve al mundo sano'
    'mlflow'      = 'Registro de modelos en http://localhost:5000'
    'ollama'      = 'Modelo local, para quien no tenga llave'
    'reset'       = 'Boton de panico: borra todo y reconstruye desde cero'
}

# --------------------------------------------------------------------------

switch ($Comando) {

    'ayuda' {
        Write-Host ""
        Write-Host "Taller 02 de caso aplicado de IA en industria" -ForegroundColor White
        Write-Host ""
        foreach ($c in $COMANDOS.Keys) {
            Write-Host ("  {0,-14}" -f $c) -ForegroundColor Cyan -NoNewline
            Write-Host $COMANDOS[$c]
        }
        Write-Host ""
        Write-Host "Uso:  .\taller.ps1 <comando> [opciones]" -ForegroundColor DarkGray
        Write-Host ""
    }

    'arriba' {
        # Construye las TRES imagenes, no solo las dos que se levantan. El
        # contenedor del agente no corre como servicio, asi que sin esto su
        # construccion queda pendiente y le cae encima al alumno la primera vez
        # que lo usa -- que es en plena clase, no durante el trabajo previo.
        Invoke-Compose @('build')
        Invoke-Compose @('up', '-d', 'plataforma', 'ui')
    }
    'abajo'       { Invoke-Compose @('down') }
    'estado'      { Invoke-Compose @('ps') }
    'logs'        { Invoke-Compose (@('logs', '-f') + $Resto) }

    'seed'        { Invoke-Plataforma @('seed') }
    'datos'       { Invoke-Plataforma @('datos') }
    'entrenar'    { Invoke-Plataforma @('entrenar') }
    'pronosticar' { Invoke-Plataforma @('pronosticar') }
    'metricas'    { Invoke-Plataforma @('metricas') }

    'agente'      { Invoke-Agente (@('run') + $Resto) }
    'memoria'     { Invoke-Agente (@('memoria') + $Resto) }
    'verificar'   { Invoke-Compose (@('run', '--rm', 'agente', 'python', '-m', 'retos.verificar') + $Resto) }

    'actuar' {
        Invoke-Compose (@('run', '--rm', '-e', 'EJECUTAR_ACCIONES=1', 'agente',
                          'python', '-m', 'agente', 'run') + $Resto)
    }

    'ui' {
        Invoke-Compose @('up', '-d', 'ui')
        Write-Host "http://localhost:8501" -ForegroundColor Cyan
    }

    'romper' {
        if (-not $Resto -or -not $Resto[0]) {
            Write-Host ""
            Write-Host "Falta el escenario." -ForegroundColor Red
            Write-Host "Uso:  .\taller.ps1 romper sesgo_silencioso"
            Write-Host ""
            Write-Host "Escenarios: campana_promocional, sesgo_silencioso, feed_caido, quiebre_stock"
            Write-Host ""
            exit 1
        }
        Invoke-Plataforma @('escenario', '--nombre', $Resto[0])
        Invoke-Plataforma @('pronosticar')
        Invoke-Plataforma @('metricas')
    }

    'reparar' {
        Invoke-Plataforma @('datos')
        Invoke-Plataforma @('pronosticar')
        Invoke-Plataforma @('metricas')
    }

    'mlflow' {
        Invoke-Compose @('--profile', 'mlflow', 'up', '-d', 'mlflow')
        Write-Host "http://localhost:5000" -ForegroundColor Cyan
    }

    'ollama' {
        Invoke-Compose @('--profile', 'local', 'up', '-d', 'ollama')
        Invoke-Compose @('exec', 'ollama', 'ollama', 'pull', 'qwen2.5:3b-instruct')
    }

    'reset' {
        Invoke-Compose @('down', '-v')
        Invoke-Compose @('up', '-d', 'plataforma', 'ui')
        Invoke-Plataforma @('seed')
    }

    default {
        Write-Host ""
        Write-Host "No conozco el comando '$Comando'." -ForegroundColor Red
        Write-Host "Corre  .\taller.ps1  sin argumentos para ver la lista."
        Write-Host ""
        exit 1
    }
}
