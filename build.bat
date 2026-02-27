@echo off
echo Building Music Pause...
pyinstaller --onefile --windowed --name MusicPause app.py
echo.
echo Done! Executable: dist\MusicPause.exe
pause
