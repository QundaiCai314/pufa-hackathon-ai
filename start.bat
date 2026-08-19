@echo off
chcp 65001 >nul
echo ========================================
echo    氢璞 AI 智能助手 - Docker 启动脚本
echo ========================================
echo.

:: 检查 Docker 是否安装
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Docker！
    echo.
    echo 请先安装 Docker Desktop:
    echo https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

echo [1/4] 检查 Docker 状态...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker Desktop 未启动！
    echo.
    echo 请先启动 Docker Desktop，然后重新运行此脚本。
    echo.
    pause
    exit /b 1
)
echo      ✓ Docker 运行正常

echo.
echo [2/4] 检查 .env 文件...
if not exist ".env" (
    echo [警告] .env 文件不存在，从模板复制...
    copy .env.example .env
    echo.
    echo ⚠️  请编辑 .env 文件，填入你的 OpenAI API Key！
    echo.
    pause
)
echo      ✓ 配置文件存在

echo.
echo [3/4] 启动所有服务...
echo      (首次启动需要下载镜像，大约需要 5-10 分钟)
echo.
docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务启动失败！
    echo.
    echo 请查看错误信息，或运行以下命令查看详细日志：
    echo docker-compose logs
    echo.
    pause
    exit /b 1
)

echo.
echo [4/4] 等待服务就绪...
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo          🎉 启动成功！
echo ========================================
echo.
echo 前端地址:  http://localhost:3000
echo 后端 API:  http://localhost:8000/docs
echo Qdrant:   http://localhost:6333/dashboard
echo.
echo ----------------------------------------
echo 常用命令:
echo   查看日志: docker-compose logs -f
echo   停止服务: docker-compose down
echo   重启服务: docker-compose restart
echo ----------------------------------------
echo.
echo 按任意键打开前端页面...
pause >nul

start http://localhost:3000

echo.
echo 按任意键关闭此窗口...
pause >nul
