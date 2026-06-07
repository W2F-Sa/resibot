"""ساخت payload اینباند VLESS xhttp TLS مطابق نمونه‌ی موردنظر و لینک ساب.

نمونه‌ی لینک هدف:
vless://UUID@SERVER:PORT?encryption=none&security=tls&sni=irsp.mahandevs.com
&fp=chrome&alpn=h2&insecure=1&allowInsecure=1&type=xhttp&host=irsp.mahandevs.com
&path=%2Fget&mode=auto&extra={...}#REMARK

برای SSL از گواهی خود پنل استفاده می‌کنیم ("Set as panel") تا هنگام اتصال
خطای گواهی نگیریم.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class InboundSpec:
    sni: str
    host: str
    path: str
    alpn: str                 # مثل "h2"
    fingerprint: str          # مثل "chrome"
    sc_max_each_post_bytes: int
    cert_file: str = ""       # از پنل (webCertFile)
    key_file: str = ""        # از پنل (webKeyFile)


def build_stream_settings(spec: InboundSpec) -> dict[str, Any]:
    """streamSettings مربوط به xhttp + tls."""
    alpn_list = [a.strip() for a in spec.alpn.split(",") if a.strip()] or ["h2"]

    tls_settings: dict[str, Any] = {
        "serverName": spec.sni,
        "minVersion": "1.2",
        "maxVersion": "1.3",
        "cipherSuites": "",
        "rejectUnknownSni": False,
        "disableSystemRoot": False,
        "enableSessionResumption": False,
        "alpn": alpn_list,
        "settings": {
            "allowInsecure": True,
            "fingerprint": spec.fingerprint,
        },
    }
    # "Set as panel": گواهی پنل را به اینباند می‌دهیم تا SSL بدون خطا کار کند
    if spec.cert_file and spec.key_file:
        tls_settings["certificates"] = [
            {
                "certificateFile": spec.cert_file,
                "keyFile": spec.key_file,
                "ocspStapling": 3600,
                "oneTimeLoading": False,
                "usage": "encipherment",
            }
        ]
    else:
        tls_settings["certificates"] = []

    xhttp_settings: dict[str, Any] = {
        "path": spec.path,
        "host": spec.host,
        "mode": "auto",
        "scMaxEachPostBytes": str(spec.sc_max_each_post_bytes),
        "xPaddingBytes": "100-1000",
    }

    return {
        "network": "xhttp",
        "security": "tls",
        "externalProxy": [],
        "tlsSettings": tls_settings,
        "xhttpSettings": xhttp_settings,
    }


def build_client(
    uuid: str,
    email: str,
    sub_id: str,
    total_bytes: int,
    expiry_ms: int,
) -> dict[str, Any]:
    """یک کلاینت VLESS با محدودیت حجم و انقضا می‌سازد."""
    return {
        "id": uuid,
        "flow": "",
        "email": email,
        "limitIp": 0,
        "totalGB": int(total_bytes),
        "expiryTime": int(expiry_ms),
        "enable": True,
        "tgId": "",
        "subId": sub_id,
        "comment": "",
        "reset": 0,
    }


def build_inbound_payload(
    *,
    remark: str,
    port: int,
    spec: InboundSpec,
    client: dict[str, Any],
) -> dict[str, Any]:
    """payload کامل برای POST /panel/api/inbounds/add."""
    settings = {
        "clients": [client],
        "decryption": "none",
        "fallbacks": [],
    }
    sniffing = {
        "enabled": False,
        "destOverride": ["http", "tls", "quic", "fakedns"],
        "metadataOnly": False,
        "routeOnly": False,
    }
    return {
        "up": 0,
        "down": 0,
        "total": 0,
        "remark": remark,
        "enable": True,
        "expiryTime": 0,
        "listen": "",
        "port": int(port),
        "protocol": "vless",
        "settings": json.dumps(settings),
        "streamSettings": json.dumps(build_stream_settings(spec)),
        "sniffing": json.dumps(sniffing),
        "allocate": json.dumps({"strategy": "always", "refresh": 5, "concurrency": 3}),
    }


def build_sub_link(sub_base_url: str, sub_path: str, sub_id: str) -> str:
    """لینک اشتراک (subscription) را می‌سازد: {base}{subPath}{subId}"""
    base = sub_base_url.rstrip("/")
    path = "/" + sub_path.strip("/") + "/"
    return f"{base}{path}{sub_id}"


def build_vless_link(
    *,
    uuid: str,
    server: str,
    port: int,
    sni: str,
    host: str,
    path: str,
    alpn: str,
    fingerprint: str,
    sc_max_each_post_bytes: int,
    remark: str,
) -> str:
    """لینک vless را دقیقاً مطابق الگوی موردنظر می‌سازد (با insecure/allowInsecure).

    چون SNI ممکن است با گواهی سرور یکی نباشد، insecure=1&allowInsecure=1 لازم است
    تا کلاینت موقع اتصال خطای TLS نگیرد.
    """
    from urllib.parse import quote

    extra = json.dumps(
        {"mode": "auto", "scMaxEachPostBytes": str(sc_max_each_post_bytes)},
        separators=(",", ":"),
    )
    alpn_q = quote(alpn, safe="")
    query = (
        "encryption=none"
        "&security=tls"
        f"&sni={quote(sni, safe='')}"
        f"&fp={quote(fingerprint, safe='')}"
        f"&alpn={alpn_q}"
        "&insecure=1"
        "&allowInsecure=1"
        "&type=xhttp"
        f"&host={quote(host, safe='')}"
        f"&path={quote(path, safe='')}"
        "&mode=auto"
        f"&extra={quote(extra, safe='')}"
    )
    fragment = quote(remark, safe="")
    return f"vless://{uuid}@{server}:{port}?{query}#{fragment}"
