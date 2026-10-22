@echo off
 echo Stops only this GUI and its client; saved sessions remain.
 echo Pending submissions may have unknown results. Check before replaying.
 choice /C YN /N /M "Stop H2 now? [Y/N] "
 if errorlevel 2 exit /b 0
 wsl -d HexaUdon -u root --exec systemctl stop hexa-udon-gui-h2.service
 if errorlevel 1 pause
