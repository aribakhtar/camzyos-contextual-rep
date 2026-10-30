param([ValidateRange(1, 120)][int]$DatabaseWaitSeconds = 45)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create .venv and install the project first; see README.md.'
}

# Wait for the configured database, without changing credentials or choosing a
# different database. The caller starts portable Neo4j, Docker, or their own instance.
$databaseCheck = @'
import sys
import time
from camzyos import graph
from camzyos.settings import settings
cfg = settings()
deadline = time.monotonic() + int(sys.argv[1])
while True:
    if graph.status(cfg):
        break
    if time.monotonic() >= deadline:
        raise SystemExit('Neo4j is not ready. Start the configured database and check its credentials.')
    time.sleep(1)
'@
Write-Output 'Waiting for the configured Neo4j database...'
& $projectPython -c $databaseCheck $DatabaseWaitSeconds
if ($LASTEXITCODE -ne 0) {
    throw 'Preparation stopped before indexing. Streamlit will not start.'
}

function Invoke-PreparationStep([string[]]$CliArguments) {
    & $projectPython -m camzyos.cli @CliArguments
    if ($LASTEXITCODE -ne 0) {
        throw ('Preparation failed at ' + $CliArguments[0] + '. Streamlit will not start.')
    }
}

Write-Output 'Preparing PDFs: parse, clean, chunk, embed, and verify the eligible index...'
Invoke-PreparationStep -CliArguments @('build')
Write-Output 'Indexing every bundled PDF for isolated retrieval and extraction testing...'
Invoke-PreparationStep -CliArguments @('index-all')
Invoke-PreparationStep -CliArguments @('doctor', '--strict', '--all-documents')
Write-Output 'Preparing isolated HCP memory (unchanged seeds are reused)...'
Invoke-PreparationStep -CliArguments @('seed')
Write-Output 'RAG preparation complete; chat may now start.'
