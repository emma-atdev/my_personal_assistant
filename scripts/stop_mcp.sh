#!/bin/bash
# MCP 서버 + ngrok 터널을 종료한다.

echo "MCP 서버 종료 중..."
pkill -f "mcp_server/main.py" && echo "MCP 서버 종료됨" || echo "MCP 서버가 실행 중이 아닙니다"

echo "ngrok 종료 중..."
pkill -f "ngrok" && echo "ngrok 종료됨" || echo "ngrok이 실행 중이 아닙니다"
