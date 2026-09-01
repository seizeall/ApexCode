@echo off
chcp 65001 >nul
title Stop ApexCode
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_apexcode.ps1" %*
echo.
pause
