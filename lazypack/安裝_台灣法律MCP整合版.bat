@echo off
chcp 65001 >nul
title Taiwan Legal MCP Integrated - All-in-one Installer (Portable + Self-diagnose)
if not exist "%~dp0setup_integrated.ps1" ( echo [ERROR] setup_integrated.ps1 not found. Keep all files in the SAME folder. & pause & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_integrated.ps1"
