@echo off
echo This stops the GUI and game, but keeps saved sessions.
echo A pending submission may have an unknown result. Check before replaying.
choice /C YN /N /M "Stop Hexa Udon now? [Y/N] "
if errorlevel 2 exit /b 0
wsl --terminate HexaUdon
if errorlevel 1 pause
