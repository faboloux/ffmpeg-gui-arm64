#!/bin/bash
set -e

# 初始化配置文件（首次启动）
if [ ! -f /config/ffmpeg-gui/config.json ]; then
    echo "创建默认配置文件..."
    mkdir -p /config/ffmpeg-gui
    cp /app/config.json.template /config/ffmpeg-gui/config.json
fi

# 设置权限
chmod +x /app/ffmpeg_gui.py

# 启动应用
echo "启动FFmpeg视频转换工具..."
cd /app
python3 /app/ffmpeg_gui.py
