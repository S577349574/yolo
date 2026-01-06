@echo off
echo ====================================
echo     开始打包 YOLOv8 项目
echo ====================================
echo.

call .venv\Scripts\activate.bat

echo [1/3] 清理旧文件...
if exist main.exe del /f /q main.exe
if exist main.dist rmdir /s /q main.dist
if exist main.build rmdir /s /q main.build
if exist main.onefile-build rmdir /s /q main.onefile-build

echo [2/3] 开始编译...
nuitka --standalone --onefile ^
  --windows-console-mode=force ^
  --assume-yes-for-downloads ^
  --include-package=lupa ^
  --include-package-data=lupa ^
  --nofollow-import-to=pytest ^
  --nofollow-import-to=scipy ^
  --nofollow-import-to=tkinter ^
  main.py 2>&1

REM 添加了 2>&1，将 stderr 合并到 stdout

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 编译失败！错误代码: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] 打包完成！
echo.
echo 生成文件: main.exe
dir main.exe
echo.
echo ====================================
echo     打包成功完成！
echo ====================================
pause
