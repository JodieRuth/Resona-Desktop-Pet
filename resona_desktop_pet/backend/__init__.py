from .llm_backend import LLMBackend
from .tts_backend import TTSBackend
from .sovits_manager import SoVITSManager
from .sovits_server import SoVITSServer, run_server
from .tts_remote_handler import RemoteTTSHandler
from .mcp_manager import MCPManager

STTBackend = None

def get_stt_backend():
    global STTBackend
    if STTBackend is None:
        from .stt_backend import STTBackend as _STTBackend
        STTBackend = _STTBackend
    return STTBackend

__all__ = ["LLMBackend", "TTSBackend", "get_stt_backend", "STTBackend", "SoVITSManager", "SoVITSServer", "run_server", "RemoteTTSHandler", "MCPManager"]
