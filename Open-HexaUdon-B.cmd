@echo off
setlocal
set "PORT=8767"
set "BIN=/home/hexa/release/http-fix-20261016/hexa_udon_B_httpfix"
wsl -d HexaUdon -u root --exec systemctl is-active --quiet hexa-udon-gui-b.service
if errorlevel 1 (
    wsl -d HexaUdon -u root --exec systemd-run --unit=hexa-udon-gui-b --collect --uid=hexa --setenv=HOME=/home/hexa --property=MemoryMax=3G --property=MemorySwapMax=512M --property=CPUAffinity=0-7 --property=Nice=10 --working-directory=/mnt/d/30013-o-udon /usr/bin/python3 -B /mnt/d/30013-o-udon/gui.py --binary %BIN% --port %PORT%
    if errorlevel 1 goto failed
)
powershell -NoProfile -Command "for ($attempt=0; $attempt -lt 20; $attempt++) { try { $null=Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $env:PORT + '/') -TimeoutSec 2; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 goto failed
wsl -d HexaUdon -u root --exec systemctl is-active --quiet hexa-udon-gui-b.service
if errorlevel 1 goto failed
start "" "http://127.0.0.1:%PORT%/"
echo Hexa Udon [Solver B] is running on port %PORT%. Keep this window open or minimized.
wsl -d HexaUdon -u hexa --exec sh -c "while systemctl is-active --quiet hexa-udon-gui-b.service; do sleep 2; done"
exit /b 0
:failed
echo Could not start Hexa Udon B.
pause
exit /b 1
