@echo off
REM Título: sincronización diaria de licencias de maternidad para el Programador de tareas de Windows.
REM Nota: en "Iniciar en" hay que poner esta carpeta para que encuentre el .env.
REM El código de salida es el de main.py (0 correcto, 1 configuración, 2 SQL, 3 Nodum).
REM En producción dejar SYNC_PRODUCTION=1.
cd /d "%~dp0"
py -3 main.py
exit /b %ERRORLEVEL%
