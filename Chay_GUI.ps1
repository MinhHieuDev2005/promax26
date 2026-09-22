# HEXUDON PROCON 2026 - GUI CONTROL CENTER (PowerShell Launcher)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      HEXUDON PROCON 2026 - GUI CONTROL CENTER" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Dang khoi dong giao dien do hoa, vui long cho..." -ForegroundColor Gray

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 "$PSScriptRoot\gui.py"
} else {
    python "$PSScriptRoot\gui.py"
}
