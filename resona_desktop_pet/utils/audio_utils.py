import subprocess
from pathlib import Path
import os

def convert_to_wav(input_path: str, output_path: str, target_sr: int = 16000) -> bool:
    try:
        cmd = [
            "ffmpeg", 
            "-y", 
            "-i", str(input_path), 
            "-ar", str(target_sr), 
            "-ac", "1", 
            "-f", "wav", 
            str(output_path)
        ]
        
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            check=False
        )
        
        if result.returncode != 0:
            print(f"[AudioUtils] FFmpeg conversion failed: {result.stderr.decode('utf-8', errors='ignore')}")
            return False
            
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"[AudioUtils] Output file missing or empty: {output_path}")
            return False
            
        return True
        
    except Exception as e:
        print(f"[AudioUtils] Exception during audio conversion: {e}")
        return False
