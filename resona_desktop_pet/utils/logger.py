import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logging(
    project_root: Path,
    log_dir: Path = None,
    timestamp: Optional[str] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG
) -> logging.Logger:
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if log_dir is None:
        log_dir = project_root / "logs"
    session_log_dir = log_dir / timestamp
    session_log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(lambda record: record.name != 'LLM-Detail')
    root_logger.addHandler(console_handler)

    main_handler = logging.FileHandler(
        session_log_dir / "app.log",
        encoding='utf-8',
        mode='a'
    )
    main_handler.setLevel(file_level)
    main_handler.setFormatter(formatter)
    main_handler.addFilter(lambda record: record.name != 'LLM-Detail')
    root_logger.addHandler(main_handler)

    modules_config = {
        'LLM': 'llm.log',
        'LLM-Detail': 'llm.log',  
        'LLM-Info': 'llm.log',    
        'TTS': 'tts.log',
        'STT': 'stt.log',
        'MCP': 'mcp.log',
        'SoVITS': 'sovits.log',
        'SoVITS-Server': 'sovits.log',
        'Behavior': 'behavior.log',
        'Cleanup': 'cleanup.log',
    }

    for module_name, filename in modules_config.items():
        handler = logging.FileHandler(
            session_log_dir / filename,
            encoding='utf-8',
            mode='a'
        )
        handler.setLevel(file_level)
        handler.setFormatter(formatter)
        # Filter to only accept logs from this module
        handler.addFilter(
            lambda record, name=module_name: record.name == name
        )
        root_logger.addHandler(handler)

    # Log startup message
    root_logger.info(f"Logging initialized. Session log directory: {session_log_dir}")

    # Set LiteLLM log level to WARNING to avoid DEBUG/INFO spam
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)

    # Set websockets log level to INFO to avoid DEBUG spam (keepalive pings/pongs)
    logging.getLogger("websockets").setLevel(logging.INFO)
    logging.getLogger("websockets.server").setLevel(logging.INFO)
    logging.getLogger("websockets.client").setLevel(logging.INFO)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    Args:
        name: Logger name (e.g., 'LLM', 'TTS', 'Behavior')

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Convenience functions for quick logging
def debug(msg: str, module: str = "App"):
    """Log debug message."""
    logging.getLogger(module).debug(msg)


def info(msg: str, module: str = "App"):
    """Log info message."""
    logging.getLogger(module).info(msg)


def warning(msg: str, module: str = "App"):
    """Log warning message."""
    logging.getLogger(module).warning(msg)


def error(msg: str, module: str = "App"):
    """Log error message."""
    logging.getLogger(module).error(msg)


def critical(msg: str, module: str = "App"):
    """Log critical message."""
    logging.getLogger(module).critical(msg)
