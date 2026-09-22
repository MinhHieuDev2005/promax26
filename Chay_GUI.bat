@echo off
chcp 65001 >nul
title HEXUDON PROCON 2026 - GUI CONTROL CENTER

echo ========================================================
echo       HEXUDON PROCON 2026 - GUI CONTROL CENTER
echo ========================================================
echo Dang khoi dong giao dien do hoa, vui long cho...
echo.

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    py -3 "%~dp0gui.py"
) else (
    python "%~dp0gui.py"
)

if errorlevel 1 (
    echo.
    echo [LOI] Chuong trinh bi dung dot ngot hoac co loi xay ra.
    pause
)
