@echo off
set "PYTHONW=%~dp0venv\Scripts\pythonw.exe"
set "APP=%~dp0src\hardware_compare_gui.py"

if not exist "%PYTHONW%" (
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Не найден pythonw.exe в python_proto\venv. Сообщите об этом ассистенту.', 'QuietRadius — ошибка')"
    exit /b 1
)

start "" "%PYTHONW%" "%APP%"
