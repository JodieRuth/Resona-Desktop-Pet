import sys
import json
import importlib.util
import configparser
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout, 
                             QSlider, QSpinBox, QDoubleSpinBox, QLineEdit, QLabel, QGroupBox, QCheckBox)
from PySide6.QtCore import Qt, QTimer

class SensorMocker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Resona 全量传感器模拟器 (DEBUG MODE)")
        self.resize(500, 800)
        self.project_root = Path(__file__).parent.parent
        self.mock_file = self.project_root / "TEMP" / "mock_data.json"
        self.mock_file.parent.mkdir(exist_ok=True)
        
        self.plugin_controls = {}
        self.init_ui()
        self.load_plugins()

        self.timer = QTimer()
        self.timer.timeout.connect(self.save_mock_data)
        self.timer.start(200) 

    def load_plugins(self):
        config = configparser.ConfigParser(interpolation=None)
        config.read(self.project_root / "config.cfg", encoding="utf-8")
        if not config.getboolean("General", "plugins_enabled", fallback=False):
            return

        active_pack = config.get("General", "active_pack", fallback="")
        if not active_pack: return
        
        pack_json_path = self.project_root / "packs" / active_pack / "pack.json"
        if not pack_json_path.exists(): return
        
        with open(pack_json_path, "r", encoding="utf-8") as f:
            pack_data = json.load(f)
        
        plugin_dir_rel = pack_data.get("logic", {}).get("plugins")
        if not plugin_dir_rel: return
        
        plugin_dir = self.project_root / "packs" / active_pack / plugin_dir_rel
        if not plugin_dir.exists(): return

        plugin_group = QGroupBox("外部插件状态模拟")
        plugin_layout = QFormLayout(plugin_group)
        
        for f in plugin_dir.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "INFO"):
                    info = module.INFO
                    pid = info.get("id")
                    if pid:
                        name = info.get("name", pid)
                        cb = QCheckBox("是否成立 (Bool)")
                        le = QLineEdit(); le.setPlaceholderText("状态描述 (Str)")
                        sb = QDoubleSpinBox(); sb.setRange(-999999, 999999); sb.setValue(0.0)
                        
                        plugin_layout.addRow(QLabel(f"<b>[{name}]</b>"), QLabel(""))
                        plugin_layout.addRow("判定结果:", cb)
                        plugin_layout.addRow("文本内容:", le)
                        plugin_layout.addRow("数值大小:", sb)
                        
                        self.plugin_controls[pid] = (cb, le, sb)
            except Exception as e:
                print(f"Error loading plugin for mocker: {e}")
        
        if self.plugin_controls:
            self.centralWidget().layout().addWidget(plugin_group)

    def init_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        scroll = QGroupBox("内置传感器模拟器"); scroll_layout = QVBoxLayout(scroll)
        f = QFormLayout()

        
        self.cpu_temp = QDoubleSpinBox(); self.cpu_temp.setRange(0, 110); self.cpu_temp.setValue(45.0)
        self.gpu_temp = QDoubleSpinBox(); self.gpu_temp.setRange(0, 110); self.gpu_temp.setValue(50.0)
        self.cpu_usage = QDoubleSpinBox(); self.cpu_usage.setRange(0, 100); self.cpu_usage.setValue(10.0)
        self.gpu_usage = QDoubleSpinBox(); self.gpu_usage.setRange(0, 100); self.gpu_usage.setValue(5.0)
        
        
        self.idle_sec = QSpinBox(); self.idle_sec.setRange(0, 86400); self.idle_sec.setValue(0)
        self.fullscreen = QCheckBox("全屏模式运行中")
        self.clip = QLineEdit(); self.clip.setPlaceholderText("伪造剪贴板...")
        self.music_title = QLineEdit(); self.music_title.setPlaceholderText("歌名 - 歌手 (网易云模式)")
        
        
        self.win_pname = QLineEdit(); self.win_pname.setText("explorer.exe")
        self.win_title = QLineEdit(); self.win_title.setText("桌面")
        self.win_url = QLineEdit(); self.win_url.setPlaceholderText("https://...")
        
        
        self.weather = QLineEdit(); self.weather.setText("晴")
        self.mock_date = QLineEdit(); self.mock_date.setPlaceholderText("MM-DD (如 05-20), 留空则用系统时间")
        self.mock_time = QLineEdit(); self.mock_time.setPlaceholderText("HH:MM (如 23:30), 留空则用系统时间")

        self.process_uptime = QSpinBox(); self.process_uptime.setRange(0, 999999); self.process_uptime.setValue(120)
        self.battery_level = QSpinBox(); self.battery_level.setRange(0, 100); self.battery_level.setValue(80)
        self.battery_charging = QCheckBox("正在充电")
        self.file_drop_path = QLineEdit(); self.file_drop_path.setPlaceholderText("拖入的文件路径 (如 C:\\Users\\test.txt)")
        self.file_drop_ext = QLineEdit(); self.file_drop_ext.setPlaceholderText("文件后缀 (如 .txt, .png)")

        f.addRow("CPU 温度:", self.cpu_temp); f.addRow("GPU 温度:", self.gpu_temp)
        f.addRow("CPU 占用:", self.cpu_usage); f.addRow("GPU 占用:", self.gpu_usage)
        f.addRow("闲置时间(s):", self.idle_sec); f.addRow(self.fullscreen)
        f.addRow("剪贴板内容:", self.clip)
        f.addRow("正在播放(音乐):", self.music_title)
        f.addRow("活跃进程名:", self.win_pname); f.addRow("窗口标题:", self.win_title); f.addRow("浏览器 URL:", self.win_url)
        f.addRow("当前天气:", self.weather); f.addRow("伪造日期:", self.mock_date); f.addRow("伪造时间:", self.mock_time)
        f.addRow("进程存活时间(s):", self.process_uptime)
        f.addRow("电池电量(%):", self.battery_level); f.addRow(self.battery_charging)
        f.addRow("拖入文件路径:", self.file_drop_path); f.addRow("拖入文件后缀:", self.file_drop_ext)
        
        scroll_layout.addLayout(f); layout.addWidget(scroll)
        self.status = QLabel("状态: 模拟数据已实时映射"); layout.addWidget(self.status)

    def save_mock_data(self):
        plugin_mock = {}
        for pid, (cb, le, sb) in self.plugin_controls.items():
            plugin_mock[pid] = [cb.isChecked(), le.text(), sb.value()]

        data = {
            "cpu_temp": self.cpu_temp.value(), "gpu_temp": self.gpu_temp.value(),
            "cpu_usage": self.cpu_usage.value(), "gpu_usage": self.gpu_usage.value(),
            "idle_sec": self.idle_sec.value(), "is_fullscreen": self.fullscreen.isChecked(),
            "clip_text": self.clip.text(), "music_title": self.music_title.text(),
            "win_pname": self.win_pname.text().lower(),
            "win_title": self.win_title.text(), "win_url": self.win_url.text(),
            "weather": {"condition": self.weather.text()},
            "date": self.mock_date.text(), "time": self.mock_time.text(),
            "process_uptime": self.process_uptime.value(),
            "battery": {"level": self.battery_level.value(), "charging": self.battery_charging.isChecked()},
            "file_drop": {
                "path": self.file_drop_path.text(),
                "name": Path(self.file_drop_path.text()).name if self.file_drop_path.text() else "",
                "ext": Path(self.file_drop_path.text()).suffix.lower() if self.file_drop_path.text() else self.file_drop_ext.text().lower()
            },
            "plugins": plugin_mock
        }
        with open(self.mock_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    app = QApplication(sys.argv); w = SensorMocker(); w.show(); sys.exit(app.exec())
