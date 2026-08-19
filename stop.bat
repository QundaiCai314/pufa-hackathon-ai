@echo off
chcp 65001 >nul
echo ========================================
echo    氢璞 AI 智能助手 - 停止服务
echo ========================================
echo.

echo [1/2] 停止所有服务...
docker-compose down

if %errorlevel% neq 0 (
    echo.
    echo [错误] 停止服务失败！
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] 清理完成
echo.
echo ========================================
echo          ✓ 所有服务已停止
echo ========================================
echo.
echo 数据已保留，下次启动会恢复。
echo.
echo 如需完全清理（包括数据库）：
echo   docker-compose down -v
echo.
pause
