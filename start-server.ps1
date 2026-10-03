$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -u (Join-Path $PSScriptRoot 'webapp.py')
