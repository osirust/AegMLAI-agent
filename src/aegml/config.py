"""Explicit configuration, with an offline default and no dotenv side effects."""

import ipaddress
import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    base_url: str = "http://localhost:11434/v1"
    model: str = ""
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 60.0
    max_tokens: int = 1200

    def __post_init__(self) -> None:
        if self.provider not in {"mock", "chat_completions"}:
            raise ValueError("AEGML_PROVIDER: ожидается mock или chat_completions")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 300:
            raise ValueError("AEGML_TIMEOUT_SECONDS: требуется число в (0, 300]")
        if not 1 <= self.max_tokens <= 8192:
            raise ValueError("AEGML_MAX_TOKENS: требуется целое число от 1 до 8192")
        if self.provider == "mock":
            return
        if not self.model.strip():
            raise ValueError("Для chat_completions задайте AEGML_MODEL")
        try:
            url = urlsplit(self.base_url)
            port = url.port
            del port
            host = url.hostname
            loopback = host == "localhost"
            if host and not loopback:
                try:
                    loopback = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    loopback = False
            valid = (
                url.scheme in {"http", "https"} and host
                and url.username is None and url.password is None
                and not url.query and not url.fragment
                and not any(c.isspace() for c in self.base_url)
            )
            if not valid or (url.scheme == "http" and not loopback):
                raise ValueError
        except ValueError:
            raise ValueError(
                "AEGML_BASE_URL: нужен HTTPS URL без credentials/query/fragment; "
                "HTTP разрешён для localhost/loopback"
            ) from None

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            timeout = float(os.environ.get("AEGML_TIMEOUT_SECONDS", "60"))
            tokens = int(os.environ.get("AEGML_MAX_TOKENS", "1200"))
        except ValueError:
            raise ValueError("Неверное число в AEGML_TIMEOUT_SECONDS или AEGML_MAX_TOKENS") from None
        return cls(
            provider=os.environ.get("AEGML_PROVIDER", "mock"),
            base_url=os.environ.get("AEGML_BASE_URL", "http://localhost:11434/v1"),
            model=os.environ.get("AEGML_MODEL", ""),
            api_key=os.environ.get("AEGML_API_KEY", ""),
            timeout_seconds=timeout,
            max_tokens=tokens,
        )

    def public_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url if self.provider != "mock" else None,
            "model": self.model if self.provider != "mock" else "offline-demo",
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
        }
