param([switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create .venv and install the project first; see README.md.'
}
& (Join-Path $PSScriptRoot 'prepare.ps1')
if ($PrepareOnly) {
    Write-Output 'Preparation complete. Streamlit was not started.'
    return
}
& $projectPython -m streamlit run app.py
exit $LASTEXITCODE
