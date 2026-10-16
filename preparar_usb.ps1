# Copia el proyecto y los paquetes a la USB de Ubuntu (hecha con Rufus).
#
#   powershell -ExecutionPolicy Bypass -File preparar_usb.ps1 -Unidad E:
#
# Deja en la USB la carpeta complexnet\ con:
#   arrancar_nodo.sh, setup_adhoc.sh   (con finales de linea de Linux)
#   complexnet-api\                    (sin logs ni caches)
#   paquetes\*.deb                     (lo que el Linux en vivo no trae)
# Se puede correr las veces que haga falta: actualiza lo que cambio.
# Los pasos completos estan en PREPARAR_USB.md.

param(
    [Parameter(Mandatory = $true)][string]$Unidad
)

$ErrorActionPreference = "Stop"
$Raiz = $PSScriptRoot
$Unidad = $Unidad.TrimEnd("\", ":") + ":"
$Destino = Join-Path $Unidad "complexnet"

function Fallar($texto) {
    Write-Host ""
    Write-Host "ERROR: $texto" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$Unidad\")) {
    Fallar "no existe la unidad $Unidad. Mira la letra de la USB en el Explorador de archivos."
}
if (-not (Test-Path "$Unidad\casper")) {
    Write-Host "OJO: $Unidad no parece una USB de Ubuntu hecha con Rufus (no tiene la carpeta casper)." -ForegroundColor Yellow
    Write-Host "     Se copia igual, pero revisa el paso 2 de PREPARAR_USB.md." -ForegroundColor Yellow
}

Write-Host "== copiando el proyecto a $Destino =="
New-Item -ItemType Directory -Force -Path $Destino | Out-Null

robocopy (Join-Path $Raiz "complexnet-api") (Join-Path $Destino "complexnet-api") /MIR /XD logs __pycache__ .pytest_cache /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fallar "robocopy no pudo copiar complexnet-api (codigo $LASTEXITCODE)." }

foreach ($script in @("arrancar_nodo.sh", "setup_adhoc.sh")) {
    $texto = [System.IO.File]::ReadAllText((Join-Path $Raiz $script))
    $texto = $texto -replace "`r`n", "`n"
    $sinBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $Destino $script), $texto, $sinBom)
}

Write-Host "== copiando los paquetes =="
$Paquetes = Join-Path $Raiz "paquetes"
$DestinoPaquetes = Join-Path $Destino "paquetes"
New-Item -ItemType Directory -Force -Path $DestinoPaquetes | Out-Null
if (Test-Path $Paquetes) {
    Copy-Item (Join-Path $Paquetes "*.deb") $DestinoPaquetes -Force
}

$faltan = @()
foreach ($p in @("batctl", "iw", "python3-psutil")) {
    if (-not (Get-ChildItem $DestinoPaquetes -Filter "${p}_*.deb" -ErrorAction SilentlyContinue)) {
        $faltan += $p
    }
}

Write-Host ""
Get-ChildItem $DestinoPaquetes -Filter *.deb | ForEach-Object { Write-Host "  $($_.Name)" }
if ($faltan.Count -gt 0) {
    Write-Host ""
    Write-Host "OJO: faltan estos paquetes en la USB: $($faltan -join ', ')" -ForegroundColor Yellow
    Write-Host "     Descargalos con el paso 3 de PREPARAR_USB.md y vuelve a correr este script." -ForegroundColor Yellow
}

$libre = [math]::Round((Get-PSDrive $Unidad.TrimEnd(":")).Free / 1GB, 1)
Write-Host ""
Write-Host "Listo. La USB quedo con complexnet\ ($libre GB libres)." -ForegroundColor Green
Write-Host "En cada computador, despues de arrancar con toram:"
Write-Host "  sudo bash /media/ubuntu/COMPLEXNET/complexnet/arrancar_nodo.sh N"
