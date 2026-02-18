import base64
import configparser
import io
from pathlib import Path

import requests
from PIL import ImageGrab
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("OcrTools")


def _get_bool(cfg: configparser.ConfigParser, section: str, key: str, fallback: bool) -> bool:
    val = cfg.get(section, key, fallback=str(fallback))
    return val.lower() in ("true", "1", "yes", "on")


def _load_ocr_config(config_path: Path) -> dict:
    cfg = configparser.ConfigParser(interpolation=None)
    if config_path.exists():
        cfg.read(config_path, encoding="utf-8")
    provider = cfg.get("OCR", "provider", fallback="tencent").lower()
    enabled = _get_bool(cfg, "OCR", "enabled", False)
    vlm_enabled = _get_bool(cfg, "OCR", "vlm_enabled", False)
    config = {
        "enabled": enabled,
        "vlm_enabled": vlm_enabled,
        "provider": provider
    }
    if provider == "baidu":
        api_key = cfg.get("OCR", "baidu_api_key", fallback="")
        secret_key = cfg.get("OCR", "baidu_secret_key", fallback="")
        config["api_key"] = api_key
        config["secret_key"] = secret_key
    elif provider == "tencent":
        secret_id = cfg.get("OCR", "tencent_secret_id", fallback="")
        secret_key = cfg.get("OCR", "tencent_secret_key", fallback="")
        config["secret_id"] = secret_id
        config["secret_key"] = secret_key
    else:
        raise RuntimeError(f"Unsupported OCR provider: {provider}")
    return config


def _prepare_image_base64() -> str:
    screenshot = ImageGrab.grab()
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format="PNG")
    return base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")


def _baidu_ocr(image_base64: str, api_key: str, secret_key: str) -> str:
    session = requests.Session()
    session.trust_env = False
    token_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
    token_resp = session.get(token_url, timeout=10)
    if token_resp.status_code != 200:
        raise RuntimeError(token_resp.text)
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(token_resp.text)
    request_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    params = {"image": image_base64}
    headers = {"content-type": "application/x-www-form-urlencoded"}
    ocr_resp = session.post(f"{request_url}?access_token={access_token}", data=params, headers=headers, timeout=15)
    if ocr_resp.status_code != 200:
        raise RuntimeError(ocr_resp.text)
    ocr_data = ocr_resp.json()
    words = [item.get("words", "") for item in ocr_data.get("words_result", [])]
    return "\n".join([w for w in words if w])


def _tencent_ocr(image_base64: str, secret_id: str, secret_key: str) -> str:
    from tencentcloud.common import credential
    from tencentcloud.ocr.v20181119 import ocr_client, models
    cred = credential.Credential(secret_id, secret_key)
    client = ocr_client.OcrClient(cred, "ap-shanghai")
    req = models.GeneralBasicOCRRequest()
    req.ImageBase64 = image_base64
    resp = client.GeneralBasicOCR(req)
    detections = resp.TextDetections or []
    texts = [item.DetectedText for item in detections if getattr(item, "DetectedText", None)]
    return "\n".join(texts)


def _run_ocr(ocr_config: dict) -> str:
    image_base64 = _prepare_image_base64()
    provider = ocr_config.get("provider")
    if provider == "baidu":
        return _baidu_ocr(image_base64, ocr_config["api_key"], ocr_config["secret_key"])
    if provider == "tencent":
        return _tencent_ocr(image_base64, ocr_config["secret_id"], ocr_config["secret_key"])
    raise RuntimeError(f"Unsupported OCR provider: {provider}")


@mcp.tool()
def capture_ocr(config_path: str = "") -> str:
    """Capture the current screen content, perform OCR using the configured provider, and return the text."""
    try:
        root = Path(__file__).resolve().parents[1]
        cfg_path = Path(config_path) if config_path else root / "config.cfg"
        ocr_config = _load_ocr_config(cfg_path)
        provider = ocr_config.get("provider")
        if provider == "baidu":
            if not ocr_config.get("api_key") or not ocr_config.get("secret_key"):
                return "Error: Missing Baidu OCR api_key/secret_key"
        if provider == "tencent":
            if not ocr_config.get("secret_id") or not ocr_config.get("secret_key"):
                return "Error: Missing Tencent OCR secret_id/secret_key"
        return _run_ocr(ocr_config)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    import sys
    try:
        root = Path(__file__).resolve().parents[1]
        cfg_path = root / "config.cfg"
        if cfg_path.exists():
            config = _load_ocr_config(cfg_path)
            if not config.get("enabled", False):
                print(f"OCR not enabled in {cfg_path}, exiting.", file=sys.stderr)
                sys.exit(1)
            
            provider = config.get("provider")
            if provider == "baidu" and (not config.get("api_key") or not config.get("secret_key")):
                print("Missing Baidu API config, exiting.", file=sys.stderr)
                sys.exit(1)
            elif provider == "tencent" and (not config.get("secret_id") or not config.get("secret_key")):
                print("Missing Tencent API config, exiting.", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"Config check failed: {e}", file=sys.stderr)
        sys.exit(1)

    mcp.run()
