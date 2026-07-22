@echo off
cd /d "%~dp0"
echo Uploading app.py to device...
curl.exe -X PUT --data-binary "@app.py" http://192.168.2.164/upload
echo.
pause
