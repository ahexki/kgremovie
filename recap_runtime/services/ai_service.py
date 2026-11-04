"""AI client used by the planner (translation only).

Two providers are supported, both through the google-genai SDK:

  * gemini - Google AI Studio (GEMINI_API_KEY)
  * orynx  - https://orynx.dev, a Gemini-compatible gateway (ORYNX_API_KEY, base URL https://api.orynx.dev)

The planner (recap_planner._configure_gemini_key_pool) builds the fail-over chain and swaps `client`,
`text_model` and the provider while it runs. This class only creates the first client and knows which
proxy belongs to which provider:

  * Gemini : GEMINI_PROXY in the .env wins ("none" = direct). Without it a local v2rayN proxy on
             127.0.0.1:10808 is used when it is running, else direct.
  * Orynx  : direct, unless ORYNX_PROXY is set in the .env.
"""
import os
import socket

from google import genai
from google.genai import types  # noqa: F401  (the planner reads ai_service.types)

_LOCAL_PROXY = "http://127.0.0.1:10808"
ORYNX_DEFAULT_BASE_URL = "https://api.orynx.dev"
_OFF = {"none", "off", "direct", "0"}


def gemini_proxy() -> str:
    configured = str(os.getenv("GEMINI_PROXY") or "").strip()
    if configured:
        return "" if configured.lower() in _OFF else configured
    try:
        with socket.create_connection(("127.0.0.1", 10808), timeout=0.2):
            return _LOCAL_PROXY
    except OSError:
        return ""


def orynx_proxy() -> str:
    configured = str(os.getenv("ORYNX_PROXY") or "").strip()
    return "" if (not configured or configured.lower() in _OFF) else configured


def orynx_base_url() -> str:
    return (str(os.getenv("ORYNX_BASE_URL") or "").strip() or ORYNX_DEFAULT_BASE_URL).rstrip("/")


class AIService:
    def __init__(self):
        gemini_key = os.getenv("GEMINI_API_KEY")
        orynx_key = os.getenv("ORYNX_API_KEY")
        if gemini_key:
            self.provider = "gemini"
            self.api_key = gemini_key
        elif orynx_key:
            self.provider = "orynx"
            self.api_key = orynx_key
        else:
            raise ValueError("⚠️ GEMINI_API_KEY / ORYNX_API_KEY မတွေ့ပါ! .env ဖိုင်ကို စစ်ဆေးပါ။")
        self._proxies = {"gemini": gemini_proxy(), "orynx": orynx_proxy()}
        self._enable_proxy()
        try:
            if self.provider == "orynx":
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(base_url=orynx_base_url()),
                )
                default_model = "gemini-3.8-flash"
            else:
                self.client = genai.Client(api_key=self.api_key)
                default_model = "gemini-3.5-flash"
        finally:
            self._disable_proxy()
        self.text_model = os.getenv("GEMINI_TEXT_MODEL", default_model)

    # --- provider-aware proxy -------------------------------------------------
    @property
    def proxy(self) -> str:
        return self._proxies.get(self.provider, "")

    def set_provider(self, provider: str) -> None:
        """Called by the planner whenever it switches the active fail-over stage."""
        self.provider = provider if provider in self._proxies else "gemini"

    def _enable_proxy(self):
        if self.proxy:
            os.environ["HTTPS_PROXY"] = self.proxy
            os.environ["HTTP_PROXY"] = self.proxy

    def _disable_proxy(self):
        if self.proxy:
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)
