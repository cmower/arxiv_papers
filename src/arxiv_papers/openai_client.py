import os
import json
from pathlib import Path
from openai import OpenAI
from typing import Any


OPENAI_CONFIG_PATH = Path(__file__).parent / "openai_config.json"


def setup_client() -> OpenAI:
    config = OPENAI_CONFIG_PATH
    cfg: dict[str, Any] = {}
    if config.exists():
        cfg = json.loads(config.read_text(encoding="utf-8"))

    api_key = cfg.get("api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing API key. Put it in config JSON as 'api_key' or set OPENAI_API_KEY."
        )

    kwargs: dict[str, Any] = {"api_key": api_key}
    if "base_url" in cfg:
        kwargs["base_url"] = cfg["base_url"]
    if "organization" in cfg:
        kwargs["organization"] = cfg["organization"]
    if "project" in cfg:
        kwargs["project"] = cfg["project"]

    return OpenAI(**kwargs)
