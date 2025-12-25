# 适配ARM64架构（拾光坞N3）的FFmpeg GUI镜像
FROM jlesage/baseimage-gui:alpine-3.19-v3.1.3-arm64v8

# 环境变量（适配中文/拾光坞屏幕）
ENV LANG=zh_CN.UTF-8 \
    DISPLAY_WIDTH=1280 \
    DISPLAY_HEIGHT=720 \
    KEEP_APP_RUNNING=1 \
    ENABLE_CJK_FONT=1 \
    APP_NAME="FFmpeg视频转换工具" \
    TZ=Asia/Shanghai

# 安装依赖（ARM64版FFmpeg+AV1+PyQt5）
RUN apk add --no-cache \
    # Python+GUI依赖
    python3 py3-pip py3-pyqt5 py3-pyqt5-sip \
    # FFmpeg及编码库（AV1/H.265/H.264/VP9）
    ffmpeg ffmpeg-libs libaom x265 x264 libvpx opus lame flac \
    # 基础工具
    bash coreutils tzdata && \
    # 清理缓存
    rm -rf /var/cache/apk/* /root/.cache/pip

# 创建目录结构
RUN mkdir -p /app /config/ffmpeg-gui
WORKDIR /app

# 复制应用文件
COPY startapp.sh /app/
COPY config.json.template /app/
COPY ffmpeg_gui.py /app/

# 设置权限
RUN chmod +x /app/startapp.sh /app/ffmpeg_gui.py

# 暴露端口（Web访问5800，VNC5900）
EXPOSE 5800 5900

# 启动命令
CMD ["/app/startapp.sh"]
