@echo off
rem Build AnimalCrossing.exe (the mod launcher) with w64devkit (i686): build.cmd <path to w64devkit\bin>
setlocal
set BIN=%~1
if "%BIN%"=="" set BIN=..\..\..\asset_import_work\toolchain\w64devkit\bin
set PATH=%BIN%;%PATH%
"%BIN%\windres.exe" launcher.rc -O coff -o launcher.res || exit /b 1
"%BIN%\gcc.exe" -O2 -municode -mwindows -o AnimalCrossing.exe launcher.c launcher.res -lcomctl32 -lole32 -lshell32 -luuid || exit /b 1
echo built AnimalCrossing.exe
