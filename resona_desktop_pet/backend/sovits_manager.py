import os
import sys
import subprocess
import time
import requests
import threading
import re
from pathlib import Path
from typing import Optional
import signal
import psutil
from ..cleanup_manager import register_cleanup, register_pid

class SoVITSManager:
    def __init__(self, project_root: Path, port: int = 9880, device: str = "cuda", model_version: str = "v2"):
        self.project_root = project_root
        self.port = port
        self.device = device
        self.model_version = model_version
        self.process: Optional[subprocess.Popen] = None
        self.api_url = f"http://127.0.0.1:{port}"
        register_cleanup(self.stop)
        gpt_sovits_root = project_root / "GPT-SoVITS"
        api_files = list(gpt_sovits_root.rglob("api_v2.py"))
        if api_files:
            self.api_script = api_files[-1]
            self.gpt_sovits_dir = self.api_script.parent
        else:
            self.gpt_sovits_dir = gpt_sovits_root
            self.api_script = self.gpt_sovits_dir / "api_v2.py"
        try: self.rel_api_script = os.path.relpath(self.api_script, self.gpt_sovits_dir)
        except: self.rel_api_script = str(self.api_script)
        self.config_file = self.gpt_sovits_dir / "configs" / "tts_infer.yaml"
        
    def is_running(self) -> bool:
        try:
            response = requests.get(f"{self.api_url}/", timeout=2)
            return response.status_code == 200 or response.status_code == 404
        except Exception: return False
    
    def start(self, timeout: int = 60, kill_existing: bool = False) -> bool:
        if self.is_running():
            if kill_existing:
                self._kill_process_on_port(self.port)
                time.sleep(2)
            else: return True
        
        if sys.platform == "win32":
            try:
                runtime_dir = self.gpt_sovits_dir / "runtime"
                sp_dir = runtime_dir / "Lib" / "site-packages"
                if not sp_dir.exists(): sp_dir = runtime_dir / "lib" / "site-packages"
                if sp_dir.exists():
                    pth_path = sp_dir / "resona_dist_fix.pth"
                    fix_code = "import os; p = os.path.join(sitedir, 'torch', 'lib'); os.add_dll_directory(p) if os.path.exists(p) else None\n"
                    with open(pth_path, "w", encoding="utf-8") as f: f.write(fix_code)
            except: pass

        if not self.api_script.exists(): return False
        if not self.config_file.exists(): return False
        actual_config_file = self.config_file
        pack_id = "Resona_Default"
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(self.project_root / "config.cfg", encoding="utf-8")
            pack_id = cfg.get("General", "active_pack", fallback="Resona_Default")
        except: pass
        
        pack_dir = self.project_root / "packs" / pack_id
        if not pack_dir.exists():
            found = False
            for subdir in (self.project_root / "packs").iterdir():
                if subdir.is_dir():
                    pack_json = subdir / "pack.json"
                    if pack_json.exists():
                        try:
                            import json
                            with open(pack_json, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                info = data.get("pack_info", {})
                                if info.get("id") == pack_id or data.get("id") == pack_id:
                                    pack_dir = subdir
                                    found = True
                                    break
                        except: pass
            if not found:
                print(f"[SoVITS] Warning: Pack ID '{pack_id}' not found in any directory.")
                
        pack_model_dir = pack_dir / "models" / "sovits"
        if self.device == "cuda":
            try:
                override_path = self.project_root / "TEMP" / f"tts_infer_override_{pack_id}.yaml"
                override_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_file, "r", encoding="utf-8") as f: content = f.read()
                content = content.replace("device: cpu", "device: cuda")
                content = content.replace("is_half: false", "is_half: true")
                bert_abs = (self.gpt_sovits_dir / "GPT_SoVITS" / "pretrained_models" / "chinese-roberta-wwm-ext-large").absolute().as_posix()
                hubert_abs = (self.gpt_sovits_dir / "GPT_SoVITS" / "pretrained_models" / "chinese-hubert-base").absolute().as_posix()
                content = re.sub(r'bert_base_path:.*', f'bert_base_path: {bert_abs}', content)
                content = re.sub(r'cnhuhbert_base_path:.*', f'cnhuhbert_base_path: {hubert_abs}', content)
                content = re.sub(r'cnhubert_base_path:.*', f'cnhubert_base_path: {hubert_abs}', content)
                ckpt_files = list(pack_model_dir.glob("*.ckpt"))
                pth_files = list(pack_model_dir.glob("*.pth"))
                if not (ckpt_files and pth_files):
                    model_dir = self.project_root / "models" / "sovits"
                    ckpt_files = list(model_dir.glob("*.ckpt"))
                    pth_files = list(model_dir.glob("*.pth"))
                if ckpt_files and pth_files:
                    ckpt_file, pth_file = sorted(ckpt_files)[0], sorted(pth_files)[0]
                    abs_ckpt = ckpt_file.absolute().as_posix()
                    abs_pth = pth_file.absolute().as_posix()
                    content = re.sub(r't2s_weights_path:.*', f't2s_weights_path: "{abs_ckpt}"', content)
                    content = re.sub(r'vits_weights_path:.*', f'vits_weights_path: "{abs_pth}"', content)
                    content = re.sub(r'version:.*', f'version: {self.model_version}', content)
                with open(override_path, "w", encoding="utf-8") as f: f.write(content)
                actual_config_file = override_path
            except Exception: pass
        python_exec = sys.executable
        embedded_python = self.gpt_sovits_dir / "runtime" / "python.exe"
        if sys.platform == "win32" and embedded_python.exists(): python_exec = str(embedded_python)
        
        cmd = [python_exec, self.rel_api_script, "-a", "127.0.0.1", "-p", str(self.port), "-c", str(Path(actual_config_file).absolute())]
        try:
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                self.process = subprocess.Popen(cmd, cwd=str(self.gpt_sovits_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, text=True, bufsize=1, encoding='utf-8', errors='replace')
            else:
                self.process = subprocess.Popen(cmd, cwd=str(self.gpt_sovits_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid, text=True, bufsize=1, encoding='utf-8', errors='replace')
            register_pid(self.process.pid)
            if sys.platform == "win32":
                try:
                    import win32job
                    h_job = win32job.CreateJobObject(None, "")
                    info = win32job.QueryInformationJobObject(h_job, win32job.JobObjectExtendedLimitInformation)
                    info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    win32job.SetInformationJobObject(h_job, win32job.JobObjectExtendedLimitInformation, info)
                    win32job.AssignProcessToJobObject(h_job, self.process._handle)
                    self._h_job = h_job
                except Exception: pass
            def stream_output(pipe, prefix):
                try:
                    for line in iter(pipe.readline, ''):
                        if line: print(f"{prefix} {line.strip()}")
                except Exception: pass
            threading.Thread(target=stream_output, args=(self.process.stdout, "[SoVITS]"), daemon=True).start()
            threading.Thread(target=stream_output, args=(self.process.stderr, "[SoVITS Error]"), daemon=True).start()
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.is_running(): return True
                if self.process.poll() is not None: return False
                time.sleep(0.5)
            self.stop()
            return False
        except Exception: return False
    
    def _kill_process_on_port(self, port: int):
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections(kind='inet'):
                    if conn.laddr.port == port: proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): pass

    def stop(self) -> None:
        if self.process is None: return
        try:
            try: requests.post(f"{self.api_url}/control", json={"command": "exit"}, timeout=2)
            except: pass
            try:
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)
                for child in children: child.terminate()
                parent.terminate()
                psutil.wait_procs(children + [parent], timeout=5)
                for p in children + [parent]:
                    try: p.kill()
                    except: pass
            except psutil.NoSuchProcess: pass
            except Exception:
                if self.process.poll() is None:
                    if sys.platform == "win32": subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True)
                    else: os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except Exception: pass
        finally: self.process = None
    
    def restart(self, timeout: int = 60) -> bool:
        self.stop(); time.sleep(2); return self.start(timeout)
    
    def health_check(self) -> dict:
        result = {"running": False, "responsive": False, "error": None}
        if self.process and self.process.poll() is None: result["running"] = True
        if self.is_running(): result["responsive"] = True
        elif result["running"]: result["error"] = "Process running but not responsive"
        else: result["error"] = "Process not running"
        return result
    
    def __del__(self):
        self.stop()
