@echo off
wsl -d HexaUdon -u root --exec systemctl is-active --quiet hexa-udon-gui.service
if errorlevel 1 (
    wsl -d HexaUdon -u root --exec systemd-run --unit=hexa-udon-gui --collect --uid=hexa --setenv=HOME=/home/hexa --property=MemoryMax=3G --property=MemorySwapMax=512M --property=CPUAffinity=0-7 --property=Nice=10 --working-directory=/mnt/d/30013-o-udon /usr/bin/python3 -B /mnt/d/30013-o-udon/gui.py --binary /home/hexa/build-release/hexa_udon
    if errorlevel 1 goto failed
)
powershell -NoProfile -Command "for ($attempt=0; $attempt -lt 20; $attempt++) { try { $null=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/' -TimeoutSec 2; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 goto failed
wsl -d HexaUdon -u root --exec systemctl is-active --quiet hexa-udon-gui.service
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8765/"
echo Keep this window open or minimized while playing.
echo Use Stop-HexaUdon.cmd when finished to release resources.
wsl -d HexaUdon -u hexa --exec sh -c "while systemctl is-active --quiet hexa-udon-gui.service; do sleep 2; done"
exit /b 0
:failed
echo Could not start Hexa Udon. Keep this message and ask for help.
pause
exit /b 1
