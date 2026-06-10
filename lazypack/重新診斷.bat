@echo off
chcp 65001 >nul
title Taiwan Legal MCP Integrated - Re-diagnose
if not exist "%~dp0diagnose.ps1" ( echo [ERROR] diagnose.ps1 not found. Keep all files in the SAME folder. & pause & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose.ps1"
