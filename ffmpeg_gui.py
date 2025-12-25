#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FFmpeg视频转换工具 - 适配拾光坞N3 ARM64"""
import os
import sys
import json
import subprocess
import threading
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path

try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
                                QComboBox, QSlider, QCheckBox, QTabWidget, QGroupBox,
                                QTextEdit, QProgressBar, QSplitter, QMessageBox,
                                QSpinBox, QGridLayout, QLineEdit)
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    QT_AVAILABLE = True
except ImportError:
    QMessageBox.critical(None, "错误", "PyQt5未安装！")
    sys.exit(1)

# 配置日志
LOG_DIR = "/config/ffmpeg-gui/logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(f"{LOG_DIR}/ffmpeg_gui_{datetime.now().strftime('%Y%m%d')}.log"),
                              logging.StreamHandler()])
logger = logging.getLogger(__name__)

# 加载配置
CONFIG_PATH = "/config/ffmpeg-gui/config.json"
CONFIG_TEMPLATE_PATH = "/app/config.json.template"

def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        shutil.copy(CONFIG_TEMPLATE_PATH, CONFIG_PATH)
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        with open(CONFIG_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

class FFmpegWorker(QThread):
    """转换工作线程"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, command, input_file, output_file):
        super().__init__()
        self.command = command
        self.input_file = input_file
        self.output_file = output_file
        self.process = None
        self.aborted = False
    
    def run(self):
        try:
            self.status.emit("开始转换...")
            self.log.emit(f"执行命令: {' '.join(self.command)}")
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, 
                                          stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            duration = None
            for line in iter(self.process.stdout.readline, ''):
                if self.aborted:
                    self.process.terminate()
                    self.status.emit("已取消")
                    self.finished.emit(False, "转换取消")
                    return
                self.log.emit(line.strip())
                
                # 解析时长
                if not duration and "Duration:" in line:
                    try:
                        dur_str = line.split("Duration: ")[1].split(",")[0]
                        h, m, s = dur_str.split(":")
                        duration = int(h)*3600 + int(m)*60 + float(s)
                    except:
                        pass
                
                # 解析进度
                if "time=" in line and duration:
                    try:
                        time_str = line.split("time=")[1].split(" ")[0]
                        h, m, s = time_str.split(":")
                        current = int(h)*3600 + int(m)*60 + float(s)
                        self.progress.emit(int(current/duration*100))
                    except:
                        pass
            
            self.process.wait()
            if self.process.returncode == 0:
                self.progress.emit(100)
                self.status.emit("完成")
                self.finished.emit(True, "转换成功")
            else:
                self.status.emit("失败")
                self.finished.emit(False, f"返回码: {self.process.returncode}")
        except Exception as e:
            self.log.emit(f"错误: {e}")
            self.status.emit("错误")
            self.finished.emit(False, str(e))
    
    def stop(self):
        """停止转换"""
        self.aborted = True
        if self.process:
            self.process.terminate()

class TaskItemWidget(QWidget):
    """任务项"""
    def __init__(self, task_id, input_file, output_file):
        super().__init__()
        self.task_id = task_id
        self.input_file = input_file
        self.output_file = output_file
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        
        # 文件信息
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel(f"输入: {os.path.basename(self.input_file)}"))
        self.status_label = QLabel("等待中")
        self.status_label.setAlignment(Qt.AlignRight)
        h_layout.addWidget(self.status_label)
        layout.addLayout(h_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
    
    def update_status(self, status):
        self.status_label.setText(status)
    
    def update_progress(self, progress):
        self.progress_bar.setValue(progress)

class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.tasks = {}
        self.active_tasks = 0
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("FFmpeg视频转换工具（拾光坞N3）")
        self.setMinimumSize(1000, 700)
        
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # 标签页
        tab_widget = QTabWidget()
        
        # 转换标签页
        convert_tab = QWidget()
        self.setup_convert_tab(convert_tab)
        tab_widget.addTab(convert_tab, "视频转换")
        
        # 任务标签页
        task_tab = QWidget()
        self.setup_task_tab(task_tab)
        tab_widget.addTab(task_tab, "任务管理")
        
        main_layout.addWidget(tab_widget)
    
    def setup_convert_tab(self, widget):
        """转换标签页"""
        layout = QVBoxLayout(widget)
        
        # 文件列表 + 预览
        top_layout = QHBoxLayout()
        
        # 文件列表
        file_group = QGroupBox("待转换文件")
        file_layout = QVBoxLayout(file_group)
        
        self.file_list = QListWidget()
        file_layout.addWidget(self.file_list)
        
        # 文件按钮
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("添加文件", clicked=self.add_files))
        btn_layout.addWidget(QPushButton("添加文件夹", clicked=self.add_folder))
        btn_layout.addWidget(QPushButton("移除选中", clicked=self.remove_files))
        btn_layout.addWidget(QPushButton("清空", clicked=self.clear_files))
        file_layout.addLayout(btn_layout)
        top_layout.addWidget(file_group, 1)
        
        # 预览 + 信息
        preview_group = QGroupBox("预览 & 信息")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview = QVideoWidget()
        self.preview.setMinimumSize(320, 240)
        preview_layout.addWidget(self.preview)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(100)
        preview_layout.addWidget(self.info_text)
        top_layout.addWidget(preview_group, 1)
        
        layout.addLayout(top_layout)
        
        # 转换设置
        setting_layout = QHBoxLayout()
        
        # 视频设置
        video_group = QGroupBox("视频设置")
        video_layout = QVBoxLayout(video_group)
        
        # 编码器选择
        video_layout.addWidget(QLabel("视频编码器："))
        self.video_codec = QComboBox()
        for codec in self.config["video_codecs"].keys():
            self.video_codec.addItem(codec)
        self.video_codec.currentTextChanged.connect(self.update_video_params)
        video_layout.addWidget(self.video_codec)
        
        # 编码器参数
        self.video_params_group = QGroupBox("编码器参数")
        self.video_params_layout = QVBoxLayout(self.video_params_group)
        self.update_video_params(self.video_codec.currentText())
        video_layout.addWidget(self.video_params_group)
        
        # 分辨率
        video_layout.addWidget(QLabel("分辨率："))
        self.resolution = QComboBox()
        self.resolution.addItems(self.config["resolutions"])
        self.resolution.currentTextChanged.connect(self.on_res_change)
        video_layout.addWidget(self.resolution)
        
        # 自定义分辨率
        self.custom_res = QWidget()
        res_layout = QHBoxLayout(self.custom_res)
        res_layout.addWidget(QLabel("宽："))
        self.res_w = QSpinBox()
        self.res_w.setRange(1, 1920)
        self.res_w.setValue(1280)
        res_layout.addWidget(self.res_w)
        res_layout.addWidget(QLabel("高："))
        self.res_h = QSpinBox()
        self.res_h.setRange(1, 1080)
        self.res_h.setValue(720)
        res_layout.addWidget(self.res_h)
        self.custom_res.hide()
        video_layout.addWidget(self.custom_res)
        
        setting_layout.addWidget(video_group, 1)
        
        # 音频 + 输出设置
        audio_output_group = QGroupBox("音频 & 输出")
        ao_layout = QVBoxLayout(audio_output_group)
        
        # 音频设置
        ao_layout.addWidget(QLabel("音频编码器："))
        self.audio_codec = QComboBox()
        for codec in self.config["audio_codecs"].keys():
            self.audio_codec.addItem(codec)
        self.audio_codec.currentTextChanged.connect(self.update_audio_params)
        ao_layout.addWidget(self.audio_codec)
        
        # 音频参数
        self.audio_params_group = QGroupBox("音频参数")
        self.audio_params_layout = QVBoxLayout(self.audio_params_group)
        self.update_audio_params(self.audio_codec.currentText())
        ao_layout.addWidget(self.audio_params_group)
        
        # 输出目录
        ao_layout.addWidget(QLabel("输出目录："))
        self.output_dir = QLineEdit(self.config["default_settings"]["output_dir"])
        ao_layout.addWidget(self.output_dir)
        ao_layout.addWidget(QPushButton("浏览", clicked=self.browse_output))
        
        # 其他选项
        self.overwrite = QCheckBox("覆盖已存在文件")
        ao_layout.addWidget(self.overwrite)
        self.copy_audio = QCheckBox("复制原始音频")
        self.copy_audio.stateChanged.connect(self.on_copy_audio)
        ao_layout.addWidget(self.copy_audio)
        
        setting_layout.addWidget(audio_output_group, 1)
        
        layout.addLayout(setting_layout)
        
        # 日志 + 开始按钮
        log_layout = QHBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text, 1)
        
        self.start_btn = QPushButton("开始转换")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.clicked.connect(self.start_convert)
        log_layout.addWidget(self.start_btn, 0)
        
        layout.addLayout(log_layout)
    
    def setup_task_tab(self, widget):
        """任务管理标签页"""
        layout = QVBoxLayout(widget)
        
        self.task_list = QListWidget()
        layout.addWidget(self.task_list)
        
        # 任务按钮
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("取消选中任务", clicked=self.cancel_task))
        btn_layout.addWidget(QPushButton("移除选中任务", clicked=self.remove_task))
        btn_layout.addWidget(QPushButton("清空已完成", clicked=self.clear_finished))
        layout.addLayout(btn_layout)
    
    def update_video_params(self, codec_name):
        """更新视频参数"""
        # 清空现有参数
        for i in reversed(range(self.video_params_layout.count())):
            self.video_params_layout.itemAt(i).widget().deleteLater()
        
        # 添加新参数
        codec = self.config["video_codecs"][codec_name]
        for param in codec["params"]:
            if param["type"] == "slider":
                group = QGroupBox(param["name"])
                h_layout = QHBoxLayout(group)
                
                slider = QSlider(Qt.Horizontal)
                slider.setRange(param["min"], param["max"])
                slider.setValue(param["default"])
                
                spin = QSpinBox()
                spin.setRange(param["min"], param["max"])
                spin.setValue(param["default"])
                
                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
                
                h_layout.addWidget(slider, 1)
                h_layout.addWidget(spin, 0)
                self.video_params_layout.addWidget(group)
                
                # 保存控件引用
                setattr(self, f"video_param_{param['name'].replace(' ', '_')}", slider)
            elif param["type"] == "combobox":
                group = QGroupBox(param["name"])
                h_layout = QHBoxLayout(group)
                
                combo = QComboBox()
                combo.addItems(param["options"])
                combo.setCurrentText(str(param["default"]))
                h_layout.addWidget(combo)
                self.video_params_layout.addWidget(group)
                
                setattr(self, f"video_param_{param['name'].replace(' ', '_')}", combo)
    
    def update_audio_params(self, codec_name):
        """更新音频参数"""
        # 清空现有参数
        for i in reversed(range(self.audio_params_layout.count())):
            self.audio_params_layout.itemAt(i).widget().deleteLater()
        
        # 添加新参数
        codec = self.config["audio_codecs"][codec_name]
        for param in codec["params"]:
            if param["type"] == "combobox":
                group = QGroupBox(param["name"])
                h_layout = QHBoxLayout(group)
                
                combo = QComboBox()
                combo.addItems(param["options"])
                combo.setCurrentText(str(param["default"]))
                h_layout.addWidget(combo)
                self.audio_params_layout.addWidget(group)
                
                setattr(self, f"audio_param_{param['name'].replace(' ', '_')}", combo)
    
    def on_res_change(self, res):
        """分辨率切换"""
        if res == "自定义":
            self.custom_res.show()
        else:
            self.custom_res.hide()
    
    def on_copy_audio(self, state):
        """复制音频切换"""
        self.audio_codec.setEnabled(not state)
        self.audio_params_group.setEnabled(not state)
    
    def browse_output(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir.setText(dir_path)
    
    def add_files(self):
        """添加文件"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", 
                                               "视频文件 (*.mp4 *.mkv *.avi *.mov *.webm);;所有文件 (*.*)")
        for f in files:
            item = QListWidgetItem(os.path.basename(f))
            item.setData(Qt.UserRole, f)
            self.file_list.addItem(item)
    
    def add_folder(self):
        """添加文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            exts = ['.mp4', '.mkv', '.avi', '.mov', '.webm']
            for root, _, files in os.walk(folder):
                for f in files:
                    if any(f.lower().endswith(ext) for ext in exts):
                        path = os.path.join(root, f)
                        item = QListWidgetItem(os.path.basename(path))
                        item.setData(Qt.UserRole, path)
                        self.file_list.addItem(item)
    
    def remove_files(self):
        """移除选中文件"""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
    
    def clear_files(self):
        """清空文件列表"""
        self.file_list.clear()
    
    def build_command(self, input_file, output_file):
        """构建FFmpeg命令"""
        cmd = ["ffmpeg", "-y", "-i", input_file]
        
        # 视频编码器
        codec_name = self.video_codec.currentText()
        codec = self.config["video_codecs"][codec_name]
        cmd.extend(["-c:v", codec["encoder"]])
        
        # 视频参数
        if codec["encoder"] == "libaom-av1":
            cmd.extend(["-crf", str(self.video_param_CRF.value())])
            cmd.extend(["-cpu-used", str(self.video_param_CPU_Used.value())])
            cmd.extend(["-tile-columns", str(self.video_param_Tile_Columns.value())])
            cmd.extend(["-tile-rows", str(self.video_param_Tile_Rows.value())])
            cmd.extend(["-threads", str(self.video_param_Threads.value())])
        elif codec["encoder"] == "libx265":
            cmd.extend(["-crf", str(self.video_param_CRF.value())])
            cmd.extend(["-preset", self.video_param_Preset.currentText()])
            cmd.extend(["-tune", self.video_param_Tune.currentText()])
        elif codec["encoder"] == "libx264":
            cmd.extend(["-crf", str(self.video_param_CRF.value())])
            cmd.extend(["-preset", self.video_param_Preset.currentText()])
        
        # 分辨率
        res = self.resolution.currentText()
        if res != "原始":
            if res == "自定义":
                w = self.res_w.value()
                h = self.res_h.value()
            else:
                w, h = res.split("x")
            cmd.extend(["-vf", f"scale={w}:{h}"])
        
        # 音频
        if self.copy_audio.isChecked():
            cmd.extend(["-c:a", "copy"])
        else:
            audio_codec_name = self.audio_codec.currentText()
            audio_codec = self.config["audio_codecs"][audio_codec_name]
            cmd.extend(["-c:a", audio_codec["encoder"]])
            cmd.extend(["-b:a", self.audio_param_Bitrate.currentText()])
        
        # 输出文件
        cmd.append(output_file)
        return cmd
    
    def start_convert(self):
        """开始转换"""
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "警告", "请先添加文件！")
            return
        
        # 输出目录
        output_dir = self.output_dir.text()
        os.makedirs(output_dir, exist_ok=True)
        
        # 遍历文件
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            input_file = item.data(Qt.UserRole)
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            codec_name = self.video_codec.currentText()
            ext = self.config["video_codecs"][codec_name]["extension"]
            output_file = f"{output_dir}/{base_name}_{codec_name.lower()}.{ext}"
            
            # 检查覆盖
            if os.path.exists(output_file) and not self.overwrite.isChecked():
                QMessageBox.warning(self, "警告", f"{output_file}已存在！")
                continue
            
            # 创建任务
            task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
            cmd = self.build_command(input_file, output_file)
            
            # 添加任务项
            task_widget = TaskItemWidget(task_id, input_file, output_file)
            task_item = QListWidgetItem()
            task_item.setSizeHint(task_widget.sizeHint())
            self.task_list.addItem(task_item)
            self.task_list.setItemWidget(task_item, task_widget)
            
            # 创建工作线程
            worker = FFmpegWorker(cmd, input_file, output_file)
            worker.progress.connect(task_widget.update_progress)
            worker.status.connect(task_widget.update_status)
            worker.log.connect(self.log_text.append)
            worker.finished.connect(lambda s, m, tid=task_id: self.on_task_finish(tid, s, m))
            
            # 保存任务
            self.tasks[task_id] = {"worker": worker, "widget": task_widget, "item": task_item}
            
            # 启动任务（限制并发数）
            max_tasks = self.config["max_concurrent_tasks"]
            if self.active_tasks < max_tasks:
                worker.start()
                self.active_tasks += 1
    
    def on_task_finish(self, task_id, success, msg):
        """任务完成"""
        self.active_tasks -= 1
        # 启动下一个任务
        for tid, task in self.tasks.items():
            if task["worker"].isRunning() == False and task["widget"].status_label.text() == "等待中":
                task["worker"].start()
                self.active_tasks += 1
                break
    
    def cancel_task(self):
        """取消任务"""
        selected = self.task_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "警告", "请选择任务！")
            return
        item = selected[0]
        widget = self.task_list.itemWidget(item)
        task_id = widget.task_id
        if task_id in self.tasks:
            self.tasks[task_id]["worker"].stop()
            widget.update_status("已取消")
    
    def remove_task(self):
        """移除任务"""
        selected = self.task_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "警告", "请选择任务！")
            return
        item = selected[0]
        widget = self.task_list.itemWidget(item)
        task_id = widget.task_id
        if task_id in self.tasks and self.tasks[task_id]["worker"].isRunning() == False:
            self.task_list.takeItem(self.task_list.row(item))
            del self.tasks[task_id]
    
    def clear_finished(self):
        """清空已完成任务"""
        to_remove = []
        for task_id, task in self.tasks.items():
            status = task["widget"].status_label.text()
            if status in ["完成", "失败", "已取消"]:
                to_remove.append(task_id)
        for tid in to_remove:
            self.task_list.takeItem(self.task_list.row(self.tasks[tid]["item"]))
            del self.tasks[tid]

def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
