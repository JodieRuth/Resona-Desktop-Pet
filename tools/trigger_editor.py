import sys
import json
import importlib.util
import configparser
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QPushButton, QLabel, QGroupBox, QLineEdit, 
                             QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QTreeWidget,
                             QTreeWidgetItem, QFormLayout, QMessageBox, QTextEdit, QStatusBar)
from PySide6.QtCore import Qt
import logging

logger = logging.getLogger("Tools")

TRANSLATIONS = {
    "AND": {"label": "所有条件满足(AND)", "fields": []},
    "OR": {"label": "任一条件满足(OR)", "fields": []},
    "CUMULATIVE": {"label": "累计满足(曾达成即可)", "fields": []},
    "cpu_temp": {"label": "CPU温度(>)", "fields": ["gt"]},
    "gpu_temp": {"label": "GPU温度(>)", "fields": ["gt"]},
    "cpu_usage": {"label": "CPU占用(%)", "fields": ["gt"]},
    "gpu_usage": {"label": "GPU占用(%)", "fields": ["gt"]},
    "idle_duration": {"label": "闲置时长(s)", "fields": ["sec"]},
    "idle_recovery": {"label": "闲置结束(恢复)", "fields": ["sec"]},
    "process_active": {"label": "进程在前台", "fields": ["pnames"]},
    "process_background": {"label": "进程在运行", "fields": ["pnames", "only_new"]},
    "clip_match": {"label": "剪贴板内容匹配", "fields": ["keywords"]},
    "url_match": {"label": "浏览器URL匹配", "fields": ["keywords"]},
    "title_match": {"label": "窗口标题匹配", "fields": ["keywords"]},
    "hover_duration": {"label": "鼠标悬停(s)", "fields": ["sec"]},
    "leave_duration": {"label": "离开时长(s)", "fields": ["sec"]},
    "long_press": {"label": "长按立绘(s)", "fields": ["sec"]},
    "click_count": {"label": "点击连击数", "fields": ["count", "duration"]},
    "physics_acceleration_threshold": {"label": "物理加速度阈值(>)", "fields": ["gt"]},
    "physics_bounce_count": {"label": "物理反弹次数(>=)", "fields": ["count"]},
    "physics_fall_distance": {"label": "物理下落距离(>)", "fields": ["gt"]},
    "physics_window_collision_count": {"label": "窗口碰撞次数(>=)", "fields": ["count"]},
    "fullscreen": {"label": "进入全屏模式", "fields": []},
    "weather_match": {"label": "天气匹配", "fields": ["keywords"]},
    "music_match": {"label": "音乐匹配(网易云)", "fields": ["keywords", "only_on_change"]},
    "date_match": {"label": "日期匹配(MM-DD)", "fields": ["date"]},
    "time_range": {"label": "时间段(HH:MM-HH:MM)", "fields": ["range"]},
    "process_uptime": {"label": "进程存活时间(s)", "fields": ["pname", "gt", "lt", "log"]},
    "battery_level": {"label": "电池电量(%)", "fields": ["gt", "lt", "charging", "log"]},
    "file_drop": {"label": "文件拖入检测(暂不可用)", "fields": ["exts", "name_keywords", "log"]},
    "physics_add_directional_acceleration": {"label": "物理定向加速度", "fields": ["direction", "magnitude"]},
    "physics_disable_temporarily": {"label": "物理临时禁用", "fields": ["sec"]},
    "physics_multiply_forces": {"label": "物理力倍率", "fields": ["multiplier", "sec"]},
    "speak": {"label": "语音台词", "fields": ["text", "emotion", "voice_file"]},
    "delay": {"label": "延迟等待", "fields": ["sec"]},
    "move_to": {"label": "移动位置", "fields": ["pos"]},
    "fade_out": {"label": "虚化/透明度", "fields": ["opacity", "sec", "hover_recovery"]},
    "lock_interaction": {"label": "锁定交互(无法点击)", "fields": ["sec"]},
    "random_group": {"label": "随机动作分支", "fields": ["branches"]},
    "exit_app": {"label": "退出程序", "fields": []},
    "keywords": "关键词列表",
    "pnames": "进程名列表",
    "gt": "大于数值",
    "sec": "秒数",
    "count": "次数",
    "duration": "持续时间(s)",
    "range": "范围",
    "date": "日期",
    "opacity": "透明度",
    "weight": "随机权重",
    "direction": "方向(1-8)",
    "magnitude": "加速度",
    "multiplier": "倍率",
    "only_new": "仅检测新启动",
    "only_on_change": "仅切歌时触发一次",
    "hover_recovery": "悬停恢复时间(s)",
    "text": "文本内容",
    "emotion": "情感标签",
    "voice_file": "音频文件名(可选)",
    "pos": "位置(top_left/bottom_right)",
    "branches": "分支列表(JSON)",
    "plugin_id": "插件ID",
    "expect_bool": "期望布尔值",
    "match_text": "匹配文本(可选)",
    "gt_value": "数值大于(可选)",
    "lt_value": "数值小于(可选)",
    "lt": "小于数值(可选)",
    "log": "触发时打印日志(可选)",
    "exts": "允许的文件后缀列表",
    "name_keywords": "文件名包含的关键词",
    "params": "插件参数列表"
}

EMOTION_TAGS = [
    "<E:smile>", "<E:angry>", "<E:sad>", "<E:serious>", "<E:thinking>",
    "<E:surprised>", "<E:dislike>", "<E:smirk>", "<E:embarrassed>"
]

ACT_TYPES = {k: v for k, v in TRANSLATIONS.items() if k in ["speak", "delay", "random_group", "move_to", "fade_out", "exit_app", "lock_interaction", "physics_add_directional_acceleration", "physics_disable_temporarily", "physics_multiply_forces"]}
COND_TYPES = {k: v for k, v in TRANSLATIONS.items() if isinstance(v, dict) and k not in ACT_TYPES and k not in ["AND", "OR", "CUMULATIVE"]}

class TriggerEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interaction Trigger Editor")
        self.resize(1300, 850)
        self.project_root = Path(__file__).parent.parent
        self.current_triggers = []
        self.selected_index = -1
        self.active_pack_id = ""
        self.editing_item_ref = None
        self.editing_tree_item_ref = None
        self._editing_is_action = None
        self.dynamic_plugin_info = {}
        self.init_ui()
        self.setStatusBar(QStatusBar(self))
        self.scan_packs()
        self.scan_plugins()
        self.refresh_type_combos()
        self.load_data()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        left_panel = QVBoxLayout()
        pack_group = QGroupBox("📦 资源包选择")
        pack_layout = QHBoxLayout(pack_group)
        self.pack_combo = QComboBox()
        self.pack_combo.currentTextChanged.connect(self.on_pack_changed)
        pack_layout.addWidget(self.pack_combo)
        left_panel.addWidget(pack_group)
        left_panel.addWidget(QLabel("触发器列表:"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.on_trigger_selected)
        left_panel.addWidget(self.list_widget)
        btn_add_trigger = QPushButton("➕ 新增触发器")
        btn_add_trigger.clicked.connect(self.add_trigger)
        btn_del_trigger = QPushButton("❌ 删除选中")
        btn_del_trigger.clicked.connect(self.delete_trigger)
        left_panel.addWidget(btn_add_trigger)
        left_panel.addWidget(btn_del_trigger)
        layout.addLayout(left_panel, 1)
        mid_panel = QVBoxLayout()
        base_gb = QGroupBox("1. 触发器基础信息")
        f1 = QFormLayout(base_gb)
        self.id_edit = QLineEdit()
        self.id_edit.textChanged.connect(lambda t: self._update_base_val("id", t))
        self.desc_edit = QLineEdit()
        self.desc_edit.textChanged.connect(lambda t: self._update_base_val("description", t))
        self.logic_box = QComboBox()
        self.logic_box.addItems(["AND", "OR", "CUMULATIVE"])
        self.logic_box.currentTextChanged.connect(lambda t: self._update_base_val("logic", t))
        self.prob_spin = QDoubleSpinBox(); self.prob_spin.setRange(0.0, 1.0); self.prob_spin.setSingleStep(0.05)
        self.prob_spin.valueChanged.connect(lambda v: self._update_base_val("probability", v))
        self.cd_spin = QSpinBox(); self.cd_spin.setRange(0, 99999)
        self.cd_spin.valueChanged.connect(lambda v: self._update_base_val("cooldown", v))
        self.max_spin = QSpinBox(); self.max_spin.setRange(0, 99999)
        self.max_spin.valueChanged.connect(lambda v: self._update_base_val("max_triggers", v))
        self.enabled_cb = QCheckBox("启用此触发器")
        self.enabled_cb.toggled.connect(lambda b: self._update_base_val("enabled", b))
        self.startup_cb = QCheckBox("仅启动时触发一次")
        self.startup_cb.toggled.connect(lambda b: self._update_base_val("startup_only", b))
        f1.addRow("ID:", self.id_edit)
        f1.addRow("规则描述:", self.desc_edit)
        f1.addRow("判定逻辑:", self.logic_box)
        f1.addRow("触发概率:", self.prob_spin)
        f1.addRow("冷却间隔:", self.cd_spin)
        f1.addRow("每日上限:", self.max_spin)
        f1.addRow(self.startup_cb)
        f1.addRow(self.enabled_cb)
        mid_panel.addWidget(base_gb)
        cond_gb = QGroupBox("2. 触发判定条件 (Conditions)")
        cv = QVBoxLayout(cond_gb)
        self.cond_tree = QTreeWidget(); self.cond_tree.setHeaderLabels(["类型", "详情描述"])
        self.cond_tree.itemClicked.connect(self.on_cond_clicked)
        cv.addWidget(self.cond_tree)
        c_row = QHBoxLayout()
        self.c_type = QComboBox()
        btn_add_c = QPushButton("添加条件"); btn_add_c.clicked.connect(self.add_condition)
        btn_del_c = QPushButton("删除选中"); btn_del_c.clicked.connect(self.delete_condition)
        c_row.addWidget(self.c_type); c_row.addWidget(btn_add_c); c_row.addWidget(btn_del_c)
        cv.addLayout(c_row)
        mid_panel.addWidget(cond_gb)
        act_gb = QGroupBox("3. 响应动作序列 (Actions)")
        av = QVBoxLayout(act_gb)
        self.act_tree = QTreeWidget(); self.act_tree.setHeaderLabels(["动作序列", "摘要"])
        self.act_tree.itemClicked.connect(self.on_act_clicked)
        av.addWidget(self.act_tree)
        a_row = QHBoxLayout()
        self.a_type = QComboBox()
        btn_add_a = QPushButton("插入动作"); btn_add_a.clicked.connect(self.add_action)
        btn_del_a = QPushButton("删除选中"); btn_del_a.clicked.connect(self.delete_action)
        a_row.addWidget(self.a_type); a_row.addWidget(btn_add_a); a_row.addWidget(btn_del_a)
        av.addLayout(a_row)
        mid_panel.addWidget(act_gb)
        btn_save = QPushButton("💾 保存同步 (Save to JSON)")
        btn_save.clicked.connect(self.save_data)
        btn_save.setStyleSheet("background-color: #27ae60; color: white; height: 50px; font-weight: bold;")
        mid_panel.addWidget(btn_save)
        layout.addLayout(mid_panel, 2)
        self.prop_panel = QGroupBox("属性编辑面板")
        self.prop_layout = QVBoxLayout(self.prop_panel)
        self.prop_form = QFormLayout()
        self.prop_layout.addLayout(self.prop_form)
        self.prop_layout.addStretch()
        layout.addWidget(self.prop_panel, 1)

    def scan_plugins(self):
        self.dynamic_plugin_info = {}
        config = configparser.ConfigParser(interpolation=None)
        config.read(self.project_root / "config.cfg", encoding="utf-8")
        if not config.getboolean("General", "plugins_enabled", fallback=False):
            return

        pack_json_path = self.project_root / "packs" / self.active_pack_id / "pack.json"
        if not pack_json_path.exists(): return
        
        with open(pack_json_path, "r", encoding="utf-8") as f:
            pack_data = json.load(f)
        
        plugin_dir_rel = pack_data.get("logic", {}).get("plugins")
        if not plugin_dir_rel: return
        
        plugin_dir = self.project_root / "packs" / self.active_pack_id / plugin_dir_rel
        if not plugin_dir.exists(): return

        for f in plugin_dir.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "INFO"):
                    info = module.INFO
                    pid = info.get("id")
                    if pid:
                        self.dynamic_plugin_info[pid] = info
            except: pass

    def refresh_type_combos(self):
        self.c_type.clear()
        for k in sorted(COND_TYPES.keys()):
            self.c_type.addItem(COND_TYPES[k]["label"], k)
        
        self.c_type.addItem("🧩 通用插件状态检查", "plugin_check")
        for pid, info in self.dynamic_plugin_info.items():
            for t in info.get("triggers", []):
                ttype = t.get("type")
                label = f"🧩 [{info.get('name', pid)}] {t.get('label', ttype)}"
                self.c_type.addItem(label, ttype)

        self.a_type.clear()
        for k in sorted(ACT_TYPES.keys()):
            val = ACT_TYPES[k]
            label = val.get("label", k) if isinstance(val, dict) else val
            self.a_type.addItem(label, k)
        
        for pid, info in self.dynamic_plugin_info.items():
            for act in info.get("actions", []):
                atype = act.get("type")
                label = f"🧩 [{info.get('name', pid)}] {act.get('label', atype)}"
                self.a_type.addItem(label, atype)

    def scan_packs(self):
        packs_dir = self.project_root / "packs"
        if not packs_dir.exists(): return
        self.pack_combo.blockSignals(True)
        self.pack_combo.clear()
        for d in packs_dir.iterdir():
            if d.is_dir() and (d / "pack.json").exists(): self.pack_combo.addItem(d.name)
        idx = self.pack_combo.findText("Resona_Default")
        if idx >= 0: self.pack_combo.setCurrentIndex(idx)
        self.active_pack_id = self.pack_combo.currentText()
        self.pack_combo.blockSignals(False)

    def on_pack_changed(self, pack_id):
        if not pack_id: return
        self.active_pack_id = pack_id
        self.scan_plugins()
        self.refresh_type_combos()
        self.load_data()

    def load_data(self):
        if not self.active_pack_id: return
        path = self.project_root / "packs" / self.active_pack_id / "logic" / "triggers.json"
        self.current_triggers = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as f: self.current_triggers = json.load(f)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.current_triggers = []
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_triggers, f, indent=4, ensure_ascii=False)
        self.refresh_list()
        self.cond_tree.clear(); self.act_tree.clear()

    def save_data(self):
        if not self.active_pack_id: return
        path = self.project_root / "packs" / self.active_pack_id / "logic" / "triggers.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.current_triggers, f, indent=4, ensure_ascii=False)
        self.statusBar().showMessage(f"已成功保存至 {self.active_pack_id}", 3000)

    def auto_save(self):
        if not self.active_pack_id:
            logger.info("自动保存失败: active_pack_id 为空")
            return
        path = self.project_root / "packs" / self.active_pack_id / "logic" / "triggers.json"
        logger.info(f"正在尝试保存到: {path}")
        logger.info(f"当前触发器数据: {self.current_triggers}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"目录已确保存在: {path.parent}")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_triggers, f, indent=4, ensure_ascii=False)
            logger.info(f"数据已成功保存到: {path}")
            logger.info(f"保存的数据长度: {len(self.current_triggers)}")
        except Exception as e:
            logger.info(f"自动保存失败: {e}")
            import traceback
            traceback.print_exc()

    def refresh_list(self):
        self.list_widget.clear()
        for t in self.current_triggers: self.list_widget.addItem(t.get("id", "未命名"))

    def on_trigger_selected(self, index):
        if index < 0: return
        self.selected_index = index
        data = self.current_triggers[index]
        self.id_edit.setText(data.get("id", ""))
        self.desc_edit.setText(data.get("description", ""))
        self.logic_box.setCurrentText(data.get("logic", "AND"))
        self.prob_spin.setValue(data.get("probability", 1.0))
        self.cd_spin.setValue(data.get("cooldown", 5))
        self.max_spin.setValue(data.get("max_triggers", 9999))
        self.startup_cb.setChecked(data.get("startup_only", False))
        self.enabled_cb.setChecked(data.get("enabled", True))
        self.cond_tree.clear()
        self._render_recursive_conds(data.get("conditions", []), self.cond_tree.invisibleRootItem())
        self.cond_tree.expandAll()
        self.act_tree.clear()
        self._render_acts(data.get("actions", []), self.act_tree.invisibleRootItem())
        self.act_tree.expandAll()

        self.editing_item_ref = None
        self.editing_tree_item_ref = None
        self._editing_is_action = None
        while self.prop_form.count():
            w = self.prop_form.takeAt(0).widget()
            if w: w.deleteLater()

    def add_trigger(self):
        self.current_triggers.append({
            "id": "new_trigger",
            "enabled": True,
            "description": "",
            "logic": "AND",
            "probability": 1.0,
            "cooldown": 60,
            "max_triggers": 9999,
            "one_shot_per_pid": False,
            "conditions": [],
            "actions": []
        })
        self.refresh_list()
        self.auto_save()  

    def delete_trigger(self):
        if self.selected_index >= 0:
            del self.current_triggers[self.selected_index]
            self.refresh_list()
            self.auto_save()  

    def _render_recursive_conds(self, conds, parent):
        for c in conds:
            if "logic" in c:
                item = QTreeWidgetItem(parent, [f"【逻辑组】{c['logic']}", ""])
                item.setData(0, Qt.ItemDataRole.UserRole, c)
                logger.info(f"渲染条件组: {c}, ID: {id(c)}")
                self._render_recursive_conds(c.get("conditions", []), item)
            else:
                label = COND_TYPES.get(c["type"], {}).get("label", c["type"])
                if c["type"] == "plugin_check":
                    label = "🧩 通用插件状态检查"
                else:
                    for pid, info in self.dynamic_plugin_info.items():
                        for t in info.get("triggers", []):
                            if t.get("type") == c["type"]:
                                label = f"🧩 [{info.get('name', pid)}] {t.get('label', c['type'])}"
                                break
                item = QTreeWidgetItem(parent, [label, str(c)])
                item.setData(0, Qt.ItemDataRole.UserRole, c)
                logger.info(f"渲染条件: {c}, ID: {id(c)}")

    def _render_acts(self, actions, parent):
        for a in actions:
            raw_type = a["type"]
            label_def = ACT_TYPES.get(raw_type, raw_type)
            label = label_def.get("label", raw_type) if isinstance(label_def, dict) else label_def

            for pid, info in self.dynamic_plugin_info.items():
                for pact in info.get("actions", []):
                    if pact.get("type") == raw_type:
                        label = f"🧩 [{info.get('name', pid)}] {pact.get('label', raw_type)}"
                        break

            item = QTreeWidgetItem(parent, [label, str(a)])
            item.setData(0, Qt.ItemDataRole.UserRole, a)
            logger.info(f"渲染动作: {a}, ID: {id(a)}")

    def on_cond_clicked(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        self._build_prop_editor(data, item, COND_TYPES, is_action=False)

    def on_act_clicked(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        self._build_prop_editor(data, item, TRANSLATIONS, is_action=True)

    def _build_prop_editor(self, data, tree_item, defs, is_action=True):
        while self.prop_form.count():
            w = self.prop_form.takeAt(0).widget()
            if w: w.deleteLater()

        self.editing_item_ref = data
        self.editing_tree_item_ref = tree_item
        self._editing_is_action = is_action

        item_type = data.get("type", data.get("logic"))

        def_source = defs.get(item_type)
        if not def_source and item_type in ACT_TYPES:
             def_source = ACT_TYPES.get(item_type)

        fields = []
        if item_type == "plugin_check":
            fields = ["plugin_id", "expect_bool", "match_text", "gt_value", "lt_value"]
            if "plugin_id" not in data: data["plugin_id"] = ""
            if "expect_bool" not in data: data["expect_bool"] = True
        elif not def_source:
            is_plugin_trigger = False
            for pid, info in self.dynamic_plugin_info.items():
                if any(t.get("type") == item_type for t in info.get("triggers", [])):
                    is_plugin_trigger = True
                    break

            if is_plugin_trigger:
                for pid, info in self.dynamic_plugin_info.items():
                    for trig in info.get("triggers", []):
                        if trig.get("type") == item_type:
                            fields = trig.get("fields", [])
                            if not fields and "params" in trig:
                                fields = trig["params"]
                            break
            else:
                is_plugin_action = False
                for pid, info in self.dynamic_plugin_info.items():
                    for act in info.get("actions", []):
                        if act.get("type") == item_type:
                            is_plugin_action = True
                            fields = act.get("fields", [])
                            if not fields and "params" in act:
                                fields = act["params"]
                            break

                if not is_plugin_action:
                    fields = [key for key in data.keys() if key != "type"]
                else:
                    if not fields:
                        fields = [key for key in data.keys() if key != "type"]
        else:
            fields = def_source.get("fields", []) if isinstance(def_source, dict) else []

        parent_item = tree_item.parent()
        if parent_item:
            index_in_parent = parent_item.indexOfChild(tree_item)
            parent_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
            tree_item.setData(1, Qt.ItemDataRole.UserRole, {"index": index_in_parent, "parent_data": parent_data, "is_action": is_action})
        else:
            root = tree_item.treeWidget().invisibleRootItem()
            index_in_parent = root.indexOfChild(tree_item)
            tree_item.setData(1, Qt.ItemDataRole.UserRole, {"index": index_in_parent, "parent_data": None, "is_action": is_action})

        def update_main_data_structure_by_indices(key, value):
            logger.info(f"通过索引更新主数据结构: key={key}, value={value}")
            index_info = tree_item.data(1, Qt.ItemDataRole.UserRole)
            if not index_info:
                logger.info("错误: 无法获取索引信息")
                return

            index = index_info["index"]
            parent_data = index_info["parent_data"]
            is_action = index_info["is_action"]

            logger.info(f"索引信息: index={index}, parent_data={parent_data}, is_action={is_action}")

            if parent_data:
                for trig_idx, trigger in enumerate(self.current_triggers):
                    if "conditions" in trigger:
                        for cond_idx, condition in enumerate(trigger["conditions"]):
                            if condition is parent_data:
                                if "conditions" in condition and index < len(condition["conditions"]):
                                    condition["conditions"][index][key] = value
                                    logger.info(f"更新嵌套条件[{trig_idx}][{cond_idx}][{index}]的{key}为{value}")
                                    self.auto_save()
                                    return
            else:
                if self.selected_index >= 0 and self.selected_index < len(self.current_triggers):
                    trigger = self.current_triggers[self.selected_index]
                    if is_action:
                        if "actions" in trigger and index < len(trigger["actions"]):
                            trigger["actions"][index][key] = value
                            logger.info(f"更新动作[{self.selected_index}][{index}]的{key}为{value}")
                            self.auto_save()
                            return
                    else:
                        if "conditions" in trigger and index < len(trigger["conditions"]):
                            trigger["conditions"][index][key] = value
                            logger.info(f"更新条件[{self.selected_index}][{index}]的{key}为{value}")
                            self.auto_save()
                            return

            logger.info("警告: 未能根据索引找到要更新的数据")

        for key in fields:
            val = data.get(key)
            if key in ["only_new", "only_on_change"]:
                if val is None: val = False

            label = TRANSLATIONS.get(key, key)
            if key == "emotion":
                combo = QComboBox()
                combo.addItems(EMOTION_TAGS)
                combo.setEditable(True)
                idx = combo.findText(str(val))
                if idx >= 0: combo.setCurrentIndex(idx)
                else: combo.setCurrentText(str(val) if val else EMOTION_TAGS[0])

                def update_emotion(txt, k=key):
                    update_main_data_structure_by_indices(k, txt)
                    data[k] = txt  
                    tree_item.setText(1, str(data))

                combo.currentTextChanged.connect(update_emotion)
                self.prop_form.addRow(f"{label}:", combo)
            elif key == "plugin_id":
                combo = QComboBox()
                combo.addItems(list(self.dynamic_plugin_info.keys()))
                combo.setCurrentText(str(val))

                def update_plugin_id(txt, k=key):
                    update_main_data_structure_by_indices(k, txt)
                    data[k] = txt  
                    tree_item.setText(1, str(data))

                combo.currentTextChanged.connect(update_plugin_id)
                self.prop_form.addRow(f"{label}:", combo)
            elif isinstance(val, bool):
                cb = QCheckBox(); cb.setChecked(val)

                def update_bool(v, k=key):
                    update_main_data_structure_by_indices(k, v)
                    data[k] = v  
                    tree_item.setText(1, str(data))

                cb.toggled.connect(update_bool)
                self.prop_form.addRow(f"{label}:", cb)
            elif key == "voice_file":
                edit = QLineEdit(str(val) if val is not None else "")

                def update_voice_file(txt, k=key):
                    update_main_data_structure_by_indices(k, txt)
                    data[k] = txt  
                    tree_item.setText(1, str(data))

                edit.textChanged.connect(update_voice_file)
                self.prop_form.addRow(f"{label}:", edit)
            elif isinstance(val, list):
                edit = QLineEdit(", ".join([str(x) for x in val]))

                def update_list(txt, k=key):
                    parsed_list = [s.strip() for s in txt.split(",") if s.strip()]
                    update_main_data_structure_by_indices(k, parsed_list)
                    data[k] = parsed_list  
                    tree_item.setText(1, str(data))

                edit.textChanged.connect(update_list)
                self.prop_form.addRow(f"{label}:", edit)
            elif isinstance(val, (int, float)):
                spin = QDoubleSpinBox() if isinstance(val, float) else QSpinBox()
                spin.setRange(-9999, 9999); spin.setValue(val)

                def update_number(v, k=key):
                    update_main_data_structure_by_indices(k, v)
                    data[k] = v  
                    tree_item.setText(1, str(data))

                spin.valueChanged.connect(update_number)
                self.prop_form.addRow(f"{label}:", spin)
            else:
                edit = QLineEdit(str(val) if val is not None else "")

                def update_text(txt, k=key):
                    update_main_data_structure_by_indices(k, txt)
                    data[k] = txt  
                    tree_item.setText(1, str(data))

                edit.textChanged.connect(update_text)
                self.prop_form.addRow(f"{label}:", edit)

    def _update_base_val(self, key, val):
        logger.info(f"更新基础值: key={key}, val={val}, selected_index={self.selected_index}")
        if self.selected_index >= 0:
            logger.info(f"更新前触发器[{self.selected_index}]: {self.current_triggers[self.selected_index]}")
            self.current_triggers[self.selected_index][key] = val
            logger.info(f"更新后触发器[{self.selected_index}]: {self.current_triggers[self.selected_index]}")
            if key == "id": self.refresh_list()
            self.auto_save()  
        else:
            logger.info("警告: selected_index 小于0，无法更新基础值")


    def add_condition(self):
        if self.selected_index < 0: return
        new_c = {"type": self.c_type.currentData()}
        self.current_triggers[self.selected_index]["conditions"].append(new_c)
        self.on_trigger_selected(self.selected_index)
        self.auto_save()  

    def add_action(self):
        if self.selected_index < 0: return
        act_type = self.a_type.currentData()
        new_a = {"type": act_type}

        if act_type == "speak":
            new_a["text"] = ""
            new_a["emotion"] = EMOTION_TAGS[0]
            new_a["voice_file"] = ""
        elif act_type == "delay":
            new_a["sec"] = 5
        elif act_type == "move_to":
            new_a["pos"] = "top_left"
        elif act_type == "fade_out":
            new_a["opacity"] = 0.5
            new_a["sec"] = 1.0
            new_a["hover_recovery"] = True
        elif act_type == "lock_interaction":
            new_a["sec"] = 5.0
        elif act_type == "random_group":
            new_a["branches"] = []
        elif act_type == "physics_add_directional_acceleration":
            new_a["direction"] = 1
            new_a["magnitude"] = 500.0
        elif act_type == "physics_disable_temporarily":
            new_a["sec"] = 1.0
        elif act_type == "physics_multiply_forces":
            new_a["multiplier"] = 2.0
            new_a["sec"] = 1.0

        actions = self.current_triggers[self.selected_index]["actions"]
        actions.append(new_a)

        self.act_tree.clear()
        self._render_acts(actions, self.act_tree.invisibleRootItem())
        self.act_tree.expandAll()

        root = self.act_tree.invisibleRootItem()
        new_item = None
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) is new_a:
                new_item = child
                break

        if new_item:
            self.act_tree.setCurrentItem(new_item)
            self.on_act_clicked(new_item)

        self.auto_save()  

    def delete_condition(self):
        item = self.cond_tree.currentItem()
        if not item: return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        parent_item = item.parent()

        target_list = None
        if parent_item:
            parent_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
            target_list = parent_data.get("conditions")
        else:
            if self.selected_index >= 0:
                target_list = self.current_triggers[self.selected_index]["conditions"]

        if target_list is not None and data in target_list:
            target_list.remove(data)
            self.on_trigger_selected(self.selected_index)
            self.auto_save()  

    def delete_action(self):
        item = self.act_tree.currentItem()
        if not item or self.selected_index < 0: return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        target_list = self.current_triggers[self.selected_index]["actions"]
        if data in target_list:
            target_list.remove(data)
            self.on_trigger_selected(self.selected_index)
            self.auto_save()  

if __name__ == "__main__":
    app = QApplication(sys.argv); ex = TriggerEditor(); ex.show(); sys.exit(app.exec())
