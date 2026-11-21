@echo off
chcp 936 >nul
title EFT 互动地图 - 重启本地服务
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem ------------------------------------------------------------
rem 默认「源码版」：先停止占用端口的旧服务，再启动 tools\serve.py。
rem   双击                    源码版，重启 8787
rem   启动项目.bat 8788       源码版，重启 8788
rem   启动项目.bat source 8790 源码版，重启 8790
rem   启动项目.bat dist       安装包，重启 8787
rem   启动项目.bat dist 8790  安装包，重启 8790
rem ------------------------------------------------------------

set "MODE=source"
set "PORT="
if /i "%~1"=="dist" (
    set "MODE=dist"
    set "PORT=%~2"
) else if /i "%~1"=="source" (
    set "PORT=%~2"
) else (
    set "PORT=%~1"
)
if not defined PORT set "PORT=8787"

echo ============================================================
echo   EFT 互动地图 - 重启本地服务
echo ------------------------------------------------------------
echo   项目目录 : %CD%
if "%MODE%"=="dist" (
    echo   启动模式 : 安装包 dist\EFTMap\EFTMap.exe
) else (
    echo   启动模式 : 源码 tools\serve.py
)
echo   监听端口 : %PORT%
echo ============================================================
echo.

rem ---------- 1. 找 Python（Windows 官方安装器 py -3） ----------
set "PY="
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto try_python
set "PY=py -3"
goto have_py

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_py
python -c "import sys" >nul 2>nul
if errorlevel 1 goto no_py
set "PY=python"
goto have_py

:no_py
echo [失败] 没有找到可用的 Python（已尝试 py -3 和 python）。
echo.
echo   请先安装 Python 3.9 或更高版本，安装时勾选
echo       Add python.exe to PATH
echo   下载地址：https://www.python.org/downloads/
echo.
pause
exit /b 1

:have_py
echo [1/4] Python 可用：%PY%

if "%MODE%"=="dist" goto dist_restart

rem ---------- 2. 源码版：检查入口文件 ----------
if not exist "tools\serve.py" goto no_entry
if not exist "index.html" goto no_entry
echo [2/4] 入口文件检查通过

rem ---------- 3. 端口被占用时，先判断是不是本项目的旧服务 ----------
%PY% -c "import socket,sys; s=socket.socket(); s.settimeout(0.8); r=s.connect_ex(('127.0.0.1',%PORT%)); s.close(); sys.exit(0 if r==0 else 1)"
if errorlevel 1 goto start_source

rem 端口有服务：用 /api/build 的 root 判断是不是本仓库
%PY% -c "import json,sys,os,urllib.request; d=json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:%PORT%/api/build',timeout=3)); root=os.path.normcase(os.path.abspath(d.get('root') or '')); sys.exit(0 if root==os.path.normcase(os.path.abspath(sys.argv[1])) else 1)" "%CD%"
if errorlevel 1 goto port_foreign

rem 是本项目的旧服务：找到 PID 并结束
set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% " ^| findstr /I "LISTENING"') do set "PID=%%P"
if not defined PID goto start_source

echo [3/4] 停止旧服务 PID=!PID! ...
taskkill /PID !PID! /T /F >nul 2>nul

rem 等待端口释放（最多 20 秒）
for /l %%I in (1,1,20) do (
    %PY% -c "import socket,sys; s=socket.socket(); s.settimeout(0.3); r=s.connect_ex(('127.0.0.1',%PORT%)); s.close(); sys.exit(0 if r==0 else 1)"
    if errorlevel 1 goto start_source
    "%SystemRoot%\System32\timeout.exe" /t 1 >nul 2>nul
)
echo [失败] 旧服务没有在 20 秒内退出（PID=!PID!）。
echo        请手动执行：taskkill /PID !PID! /T /F
pause
exit /b 2

rem ---------- 4. 启动源码版 ----------
:start_source
echo [4/4] 启动源码服务...
echo.
echo ------------------------------------------------------------
echo   启动后浏览器会自动打开：http://127.0.0.1:%PORT%/
echo   停止服务：在本窗口按 Ctrl+C，或直接关闭本窗口
echo ------------------------------------------------------------
echo.
%PY% "tools\serve.py" --port %PORT%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto stop_ok
if "%RC%"=="2" goto stop_port
if "%RC%"=="3" goto stop_root
echo [失败] 服务异常退出（退出码 %RC%）。
echo        请把本窗口上方的错误信息一起发出来。
echo.
pause
exit /b %RC%

rem ---------- 安装包模式：先停旧 EFTMap，再启动 ----------
:dist_restart
if not exist "dist\EFTMap\EFTMap.exe" goto no_dist

echo [2/4] 停止旧的 EFTMap 进程...
taskkill /IM EFTMapDesktop.exe /F >nul 2>nul
taskkill /IM EFTMap.exe /T /F >nul 2>nul
"%SystemRoot%\System32\timeout.exe" /t 2 >nul 2>nul

echo [3/4] 启动安装包（托管 dist\EFTMap\_internal 前端）...
start "" "dist\EFTMap\EFTMap.exe" --port %PORT%

echo [4/4] 已启动，端口 %PORT%，浏览器会自动打开。
echo        关闭安装包窗口（或结束 EFTMap.exe 进程）即可停止。
"%SystemRoot%\System32\timeout.exe" /t 8 >nul 2>nul
exit /b 0

:port_foreign
echo [失败] 端口 %PORT% 被其他程序占用，而且不是本项目的服务。
echo        为避免误杀，本次不自动结束它。
echo.
echo        查看占用：netstat -ano ^| findstr :%PORT%
echo        换端口：  启动项目.bat 8788
echo.
pause
exit /b 2

:no_dist
echo [失败] 找不到安装包：%CD%\dist\EFTMap\EFTMap.exe
echo        先构建安装包，或直接双击本脚本使用源码版。
echo.
pause
exit /b 4

:no_entry
echo [失败] 找不到必需的入口文件。
echo        需要同时存在：
echo          %CD%\index.html
echo          %CD%\tools\serve.py
echo.
echo        请确认「启动项目.bat」和项目根目录在同一级。
echo.
pause
exit /b 1

:stop_ok
echo 服务已停止。
echo 下次重启：双击「启动项目.bat」。
echo.
pause
exit /b 0

:stop_port
echo [失败] 端口 %PORT% 被占用。
echo        换一个端口：启动项目.bat 8788
echo        查看占用：  netstat -ano ^| findstr :%PORT%
echo.
pause
exit /b 2

:stop_root
echo [失败] 站点根目录里找不到 index.html。
echo        请确认项目文件完整，没有被移动或删除。
echo.
pause
exit /b 3
