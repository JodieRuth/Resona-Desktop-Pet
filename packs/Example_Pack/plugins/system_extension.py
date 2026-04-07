# D:\GitHub\Resona-Desktop-Pet\packs\Example_Pack\plugins\system_extension.py

import os
import subprocess
import psutil
import logging

logger = logging.getLogger("Plugin")

# 插件元数据：供 TriggerEditor 识别并自动生成 UI
INFO = {
    "id": "sys_ext_v1",
    "name": "系统扩展插件",
    "triggers": [
        {
            "type": "plugin_status", 
            "label": "记事本运行状态",
            "desc": "返回: (是否运行, 进程名, 线程数)"
        }
    ],
    "actions": [
        {
            "type": "force_kill_task", 
            "label": "强制结束进程",
            "params": ["process_name"]
        }
    ]
}

def check_status():
    """
    由主控 BehaviorMonitor 每轮自动调用。
    返回值必须是: (bool, str, float/int)
    """
    try:
        count = 0
        for p in psutil.process_iter(['name']):
            if p.info['name'] == "notepad.exe":
                count += 1
        
        is_running = count > 0
        status_text = "Notepad is active" if is_running else "Idle"
        return (is_running, status_text, float(count))
    except Exception:
        return (False, "error", 0.0)

def execute_action(action_id, params):
    """
    当主控在 action 链中识别到自定义 action 时，调用此函数。
    主控调用后立即继续后续动作，不等待结果。
    """
    if action_id == "force_kill_task":
        # 这里的 params 是一个列表，对应 INFO 里定义的顺序
        p_name = params[0] if params else "notepad.exe"
        try:
            # 执行黑盒逻辑：强制杀死进程
            subprocess.run(f"taskkill /f /im {p_name}", shell=True, capture_output=True)
        except Exception as e:
            logger.warning(f"[Plugin] Failed to kill {p_name}: {e}")
