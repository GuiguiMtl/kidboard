<#
.SYNOPSIS
  Push this repo to the Pi, and pull the generated layout back.

.EXAMPLE
  .\deploy.ps1 -Target pi@raspberrypi.local
  .\deploy.ps1 -Target pi@raspberrypi.local -Restart
  .\deploy.ps1 -Target pi@raspberrypi.local -PullLayout

.NOTES
  The key mapping is produced on the Pi by tools/map_keys.py and is the one
  artefact here you cannot regenerate without sitting at the keyboard. -PullLayout
  copies it back into this repo so it ends up in git.
#>
param(
  [Parameter(Mandatory = $true)][string]$Target,
  [string]$RemoteDir = "kidboard",
  [switch]$Restart,
  [switch]$PullLayout
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

if ($PullLayout) {
  New-Item -ItemType Directory -Force -Path (Join-Path $repo "layouts") | Out-Null
  Write-Host "Pulling layout from $Target..." -ForegroundColor Cyan
  scp "${Target}:${RemoteDir}/layouts/blackwidow_v3.json" (Join-Path $repo "layouts\blackwidow_v3.json")
  Write-Host "Pulled. Commit it - it is hours of manual mapping." -ForegroundColor Green
  exit 0
}

$archive = Join-Path $env:TEMP "kidboard-deploy.tar.gz"
Write-Host "Packing..." -ForegroundColor Cyan
Push-Location $repo
try {
  # Do not ship the layout: the Pi's copy is the authoritative one.
  tar --exclude=.git --exclude=__pycache__ --exclude=.venv `
      --exclude=layouts/blackwidow_v3.json `
      -czf $archive .
} finally {
  Pop-Location
}

Write-Host "Copying to $Target..." -ForegroundColor Cyan
scp $archive "${Target}:/tmp/kidboard-deploy.tar.gz"

$remote = @"
set -e
mkdir -p ~/$RemoteDir
tar xzf /tmp/kidboard-deploy.tar.gz -C ~/$RemoteDir
rm -f /tmp/kidboard-deploy.tar.gz
chmod +x ~/$RemoteDir/setup/install.sh ~/$RemoteDir/tools/*.py
echo "deployed to ~/$RemoteDir"
"@
ssh $Target $remote

if ($Restart) {
  Write-Host "Restarting service..." -ForegroundColor Cyan
  ssh $Target "sudo systemctl restart kidboard && sleep 1 && systemctl --no-pager --lines=15 status kidboard"
}

Remove-Item $archive -Force
Write-Host "Done." -ForegroundColor Green
