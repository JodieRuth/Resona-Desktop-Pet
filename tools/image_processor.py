import sys
import os
from pathlib import Path
from PIL import Image

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720

def process_file(file_path):
    if not file_path.lower().endswith('.png'):
        return

    try:
        with Image.open(file_path) as img:
            img = img.convert("RGBA")
            orig_w, orig_h = img.size

            scale = min(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h, 1.0)
            if scale < 1.0:
                new_size = (int(orig_w * scale), int(orig_h * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                w, h = new_size
            else:
                w, h = orig_w, orig_h

            canvas = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
            
            x = (TARGET_WIDTH - w) // 2
            y = TARGET_HEIGHT - h
            
            canvas.paste(img, (x, y), img)

            output_dir = Path(file_path).parent / "processed_1280x720"
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / Path(file_path).name
            
            canvas.save(output_path, "PNG")
            print(f"Processed: {Path(file_path).name} -> {output_path}")

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: Drag and drop folders or .png files onto this script.")
        input("\nPress Enter to exit...")
        return

    paths = sys.argv[1:]
    
    for p in paths:
        path = Path(p)
        if path.is_dir():
            print(f"Scanning directory: {path}")
            for file in path.glob("*.png"):
                process_file(str(file))
        elif path.is_file():
            process_file(str(path))
        else:
            print(f"Invalid path: {p}")

    print("\nAll tasks completed.")
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
