#!/usr/bin/env python

import sys
import argparse
import configparser
from pathlib import Path

project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from resona_desktop_pet.backend.sovits_server import run_server


def load_config(project_root: Path) -> dict:
    config_path = project_root / "config.cfg"
    config = configparser.ConfigParser(interpolation=None)
    
    if config_path.exists():
        config.read(config_path, encoding="utf-8")
    
    def get_value(section: str, key: str, fallback, value_type=str):
        try:
            if value_type == bool:
                return config.getboolean(section, key, fallback=fallback)
            elif value_type == int:
                return config.getint(section, key, fallback=fallback)
            elif value_type == float:
                return config.getfloat(section, key, fallback=fallback)
            else:
                return config.get(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    return {
        "device": get_value("SoVITS", "device", "cuda"),
        "api_port": get_value("SoVITS", "api_port", 9880, int),
        "server_port": get_value("SoVITS", "server_port", 9876, int),
        "server_host": get_value("SoVITS", "server_host", "127.0.0.1"),
        "temperature": get_value("SoVITS", "temperature", 1.0, float),
        "top_p": get_value("SoVITS", "top_p", 1.0, float),
        "top_k": get_value("SoVITS", "top_k", 15, int),
        "speed": get_value("SoVITS", "speed", 1.0, float),
        "model_version": get_value("SoVITS", "model_version", "v2Pro"),
        "text_split_method": get_value("SoVITS", "text_split_method", "cut5"),
        "fragment_interval": get_value("SoVITS", "fragment_interval", 0.25, float),
        "timeout": get_value("SoVITS", "api_timeout", 120, int),
        "default_pack": get_value("SoVITS", "default_pack", None),
    }


def main():
    parser = argparse.ArgumentParser(
        description="SoVITS WebSocket Server - Share TTS service across multiple clients",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_sovits_server.py
    python run_sovits_server.py --port 9876 --device cuda
    python run_sovits_server.py --no-broadcast
    python run_sovits_server.py --project-root D:/Resona-Desktop-Pet

Config file (config.cfg) is automatically loaded:
    [SoVITS]
    device = cuda
    api_port = 9880
    server_port = 9876
        """
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory (default: script location)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="WebSocket server port (default: from config or 9876)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cuda", "cpu"],
        help="Device to use for inference (default: from config or cuda)"
    )
    parser.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Disable UDP broadcast for auto-discovery"
    )
    parser.add_argument(
        "--sovits-api-port",
        type=int,
        default=None,
        help="SoVITS API port (default: from config or 9880)"
    )
    parser.add_argument(
        "--default-pack",
        type=str,
        default=None,
        help="Default pack ID to preload (default: from config or auto-select first valid)"
    )

    args = parser.parse_args()

    root = Path(args.project_root) if args.project_root else project_root
    config = load_config(root)

    port = args.port if args.port is not None else config["server_port"]
    device = args.device if args.device is not None else config["device"]
    sovits_api_port = args.sovits_api_port if args.sovits_api_port is not None else config["api_port"]
    broadcast_enabled = not args.no_broadcast
    default_pack = args.default_pack if args.default_pack is not None else config["default_pack"]

    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"sovits_server_{timestamp}.log"

    print("=" * 60)
    print("SoVITS WebSocket Server")
    print("=" * 60)
    print(f"Project Root: {root}")
    print(f"WebSocket Port: {port}")
    print(f"SoVITS API Port: {sovits_api_port}")
    print(f"Device: {device}")
    print(f"Broadcast: {'Enabled' if broadcast_enabled else 'Disabled'}")
    print(f"Default Pack: {default_pack or 'auto-select'}")
    print(f"Log File: {log_file}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop the server.\n")

    try:
        run_server(
            project_root=str(root),
            port=port,
            device=device,
            broadcast_enabled=broadcast_enabled,
            sovits_api_port=sovits_api_port,
            log_file=log_file,
            default_pack=default_pack
        )
    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
    except Exception as e:
        print(f"\n[Server] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
