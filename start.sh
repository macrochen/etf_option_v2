#!/bin/bash

# 定义端口
PORT=5001

# 查找占用端口的进程ID
PID=$(lsof -ti :$PORT)

if [ -n "$PID" ]; then
    echo "Port $PORT is occupied by PID $PID. Killing process..."
    kill -9 $PID
    echo "Process $PID killed."
else
    echo "Port $PORT is free."
fi

# 激活虚拟环境
source .venv/bin/activate

# 启动应用
echo "Starting app.py on port $PORT..."

# 在后台等待3秒，确认端口被监听后再打开浏览器
(
    sleep 3
    if lsof -i :$PORT > /dev/null; then
        echo "Server is running. Opening browser..."
        open "http://127.0.0.1:$PORT"
    else
        echo "Server failed to start or took too long. Browser not opened."
    fi
) &

python app.py