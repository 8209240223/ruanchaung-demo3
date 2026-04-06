Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

Write-Host "[orchard] stopping any process on :5000 ..."

$listenPid = $null
try {
  $conn = Get-NetTCPConnection -LocalPort 5000 -State Listen | Select-Object -First 1
  if ($conn) { $listenPid = $conn.OwningProcess }
}
catch {
  $listenPid = $null
}

if (-not $listenPid) {
  try {
    $line = (netstat -ano | Select-String ":5000" | Select-String "LISTENING" | Select-Object -First 1).Line
    if ($line) {
      $listenPid = ($line -split "\s+")[-1]
    }
  }
  catch {
    $listenPid = $null
  }
}

if ($listenPid) {
  Write-Host "[orchard] killing PID $listenPid"
  Stop-Process -Id ([int]$listenPid) -Force
}
else {
  Write-Host "[orchard] no listener found on :5000"
}

Write-Host "[orchard] starting latest backend ..."

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$env:APP_DEBUG = "0"
$env:APP_RELOAD = "0"

py .\app.py

