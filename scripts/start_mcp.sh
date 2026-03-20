#!/bin/bash
# MCP 서버 + ngrok 터널을 백그라운드로 실행한다.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

echo "MCP 서버 시작 중..."
cd "$PROJECT_DIR" && uv run --env-file "$ENV_FILE" python mcp_server/main.py \
  > "$LOG_DIR/mcp_server.log" 2>&1 &
MCP_PID=$!
echo "MCP 서버 PID: $MCP_PID"

sleep 2

echo "ngrok 터널 시작 중..."
ngrok http 8002 --domain=nonlisting-abbigail-convergently.ngrok-free.dev \
  > "$LOG_DIR/ngrok.log" 2>&1 &
NGROK_PID=$!
echo "ngrok PID: $NGROK_PID"

echo ""
echo "실행 완료!"
echo "MCP 서버: http://localhost:8002"
echo "ngrok:    https://nonlisting-abbigail-convergently.ngrok-free.dev"
echo ""
echo "종료하려면: $SCRIPT_DIR/stop_mcp.sh"
