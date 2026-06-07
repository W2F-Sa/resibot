"""تست واحد منطق خالص (بدون نیاز به پنل یا تلگرام)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import xray_config as xc
from bot.inbound import (
    InboundSpec,
    build_client,
    build_inbound_payload,
    build_stream_settings,
    build_sub_link,
)
from bot.proxy import (
    ProxyLocation,
    build_username,
    generate_session,
    normalize_code,
    validate_code,
    validate_session,
)


# ----------------------------- proxy ------------------------------------ #
def test_build_username_full():
    loc = ProxyLocation(area="GB", life=120, session="PzZyPXwOY")
    u = build_username("smart-myrRsidFntpraGNS", loc)
    assert u == "smart-myrRsidFntpraGNS_area-GB_life-120_session-PzZyPXwOY"


def test_build_username_with_state_city():
    loc = ProxyLocation(area="US", state="California", city="NewYork", life=60, session="abcd1234")
    u = build_username("base", loc)
    assert u == "base_area-US_state-California_city-NewYork_life-60_session-abcd1234"


def test_build_username_minimal():
    loc = ProxyLocation(session="zzzz")
    assert build_username("base", loc) == "base_session-zzzz"


def test_life_clamped():
    loc = ProxyLocation(life=99999, session="abcd")
    assert "life-1440" in build_username("b", loc)


def test_generate_session_valid():
    for _ in range(50):
        s = generate_session()
        assert validate_session(s), s


def test_validate_code():
    assert validate_code("US")
    assert validate_code("")
    assert validate_code("New-York")
    assert not validate_code("New York")
    assert not validate_code("a/b")


def test_normalize_code():
    assert normalize_code("  New York ") == "NewYork"


# --------------------------- xray config -------------------------------- #
def test_outbound_and_routing_roundtrip():
    cfg = {"outbounds": [{"tag": "direct", "protocol": "freedom"}], "routing": {"rules": []}}
    ob = xc.build_smartproxy_outbound("out-5", "proxy.smartproxy.net", 3120, "user", "pass")
    xc.upsert_outbound(cfg, ob)
    xc.upsert_routing_rule(cfg, "inbound-8081", "out-5")

    assert xc.get_outbound(cfg, "out-5")["protocol"] == "http"
    assert cfg["outbounds"][-1]["settings"]["servers"][0]["users"][0]["user"] == "user"
    assert cfg["routing"]["rules"][0]["outboundTag"] == "out-5"
    assert cfg["routing"]["rules"][0]["inboundTag"] == ["inbound-8081"]


def test_upsert_replaces_same_tag():
    cfg = {"outbounds": [], "routing": {"rules": []}}
    xc.upsert_outbound(cfg, {"tag": "out-1", "v": 1})
    xc.upsert_outbound(cfg, {"tag": "out-1", "v": 2})
    assert len(cfg["outbounds"]) == 1
    assert cfg["outbounds"][0]["v"] == 2


def test_routing_rule_no_duplicate():
    cfg = {"outbounds": [], "routing": {"rules": []}}
    xc.upsert_routing_rule(cfg, "inbound-1", "out-1")
    xc.upsert_routing_rule(cfg, "inbound-1", "out-2")
    rules = [r for r in cfg["routing"]["rules"] if "inbound-1" in r.get("inboundTag", [])]
    assert len(rules) == 1
    assert rules[0]["outboundTag"] == "out-2"


def test_cleanup_removes_both():
    cfg = {"outbounds": [], "routing": {"rules": []}}
    xc.upsert_outbound(cfg, xc.build_smartproxy_outbound("out-9", "h", 1, "u", "p"))
    xc.upsert_routing_rule(cfg, "inbound-9", "out-9")
    xc.cleanup_config_for(cfg, "inbound-9", "out-9")
    assert xc.get_outbound(cfg, "out-9") is None
    assert all("inbound-9" not in r.get("inboundTag", []) for r in cfg["routing"]["rules"])


# ----------------------------- inbound ---------------------------------- #
def test_stream_settings_xhttp_tls():
    spec = InboundSpec(
        sni="irsp.mahandevs.com", host="irsp.mahandevs.com", path="/get",
        alpn="h2", fingerprint="chrome", sc_max_each_post_bytes=5000000,
        cert_file="/c.pem", key_file="/k.pem",
    )
    ss = build_stream_settings(spec)
    assert ss["network"] == "xhttp"
    assert ss["security"] == "tls"
    assert ss["tlsSettings"]["serverName"] == "irsp.mahandevs.com"
    assert ss["tlsSettings"]["alpn"] == ["h2"]
    assert ss["tlsSettings"]["settings"]["fingerprint"] == "chrome"
    assert ss["tlsSettings"]["certificates"][0]["certificateFile"] == "/c.pem"
    assert ss["xhttpSettings"]["path"] == "/get"
    assert ss["xhttpSettings"]["host"] == "irsp.mahandevs.com"
    assert ss["xhttpSettings"]["scMaxEachPostBytes"] == "5000000"


def test_inbound_payload_serializable():
    spec = InboundSpec("s", "h", "/get", "h2", "chrome", 5000000)
    client = build_client("uuid-1", "user1", "sub1", 5 * 1024**3, 1735689600000)
    payload = build_inbound_payload(remark="r", port=12345, spec=spec, client=client)
    assert payload["protocol"] == "vless"
    assert payload["port"] == 12345
    # settings/streamSettings باید JSON معتبر باشند
    s = json.loads(payload["settings"])
    assert s["clients"][0]["id"] == "uuid-1"
    assert s["clients"][0]["totalGB"] == 5 * 1024**3
    assert s["decryption"] == "none"
    json.loads(payload["streamSettings"])
    json.loads(payload["sniffing"])


def test_sub_link():
    assert build_sub_link("https://h.com:2096", "/sub/", "abc") == "https://h.com:2096/sub/abc"
    assert build_sub_link("https://h.com:2096/", "sub", "abc") == "https://h.com:2096/sub/abc"



# --------------------------- NowPayments IPN --------------------------- #
import hashlib as _hashlib
import hmac as _hmac

from bot.nowpayments import verify_ipn_signature, _sorted_json


def _sign(payload, secret):
    msg = _sorted_json(payload).encode()
    return _hmac.new(secret.encode(), msg, _hashlib.sha512).hexdigest()


def test_ipn_signature_valid():
    payload = {"payment_status": "finished", "order_id": "w2f-1-abc", "price_amount": 10, "pay_currency": "btc"}
    sig = _sign(payload, "secret-key")
    assert verify_ipn_signature(payload, sig, "secret-key") is True


def test_ipn_signature_invalid():
    payload = {"payment_status": "finished", "order_id": "x"}
    sig = _sign(payload, "secret-key")
    # کلید اشتباه
    assert verify_ipn_signature(payload, sig, "wrong-key") is False
    # امضای دستکاری‌شده
    assert verify_ipn_signature(payload, "deadbeef", "secret-key") is False
    # ورودی خالی
    assert verify_ipn_signature(payload, "", "secret-key") is False


def test_ipn_sorted_json_is_compact_and_sorted():
    assert _sorted_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


# --------------------------- pricing / payer --------------------------- #
import os as _os
import tempfile as _tempfile

from bot.config import Settings
from bot.database import (
    Database as _DB,
    PRODUCT_RESIDENTIAL,
    PRODUCT_V2RAY,
    ROLE_ADMIN,
    ROLE_RESIDENTIAL_RESELLER,
    ROLE_USER,
    ROLE_V2RAY_RESELLER,
)
from bot.service import Service


def _make_service():
    cfg = Settings()
    cfg.price_per_gb = 3.0
    cfg.reseller_price_per_gb = 2.0
    cfg.v2ray_price_per_gb = 1.5
    cfg.v2ray_reseller_price_per_gb = 1.0
    db = _DB(_os.path.join(_tempfile.mkdtemp(), "t.db"))
    svc = Service(cfg, db, None)
    svc.seed_settings()
    return svc, db


def test_price_tiers():
    svc, _ = _make_service()
    assert svc.price_per_gb_for(ROLE_USER, PRODUCT_RESIDENTIAL) == 3.0
    assert svc.price_per_gb_for(ROLE_RESIDENTIAL_RESELLER, PRODUCT_RESIDENTIAL) == 2.0
    assert svc.price_per_gb_for(ROLE_V2RAY_RESELLER, PRODUCT_V2RAY) == 1.0
    assert svc.price_per_gb_for(ROLE_USER, PRODUCT_V2RAY) == 1.5
    assert svc.quote(ROLE_RESIDENTIAL_RESELLER, PRODUCT_RESIDENTIAL, 10) == 20.0


def test_payer_for():
    assert Service._payer_for(ROLE_ADMIN) == "admin"
    assert Service._payer_for(ROLE_RESIDENTIAL_RESELLER) == "postpaid"
    assert Service._payer_for(ROLE_V2RAY_RESELLER) == "wallet"
    assert Service._payer_for(ROLE_USER) == "wallet"


def test_wallet_atomic_deduct():
    svc, db = _make_service()
    db.add_balance(123, 50.0)
    assert db.try_deduct_balance(123, 30.0) is True
    assert db.get_balance(123) == 20.0
    assert db.try_deduct_balance(123, 30.0) is False  # insufficient
    assert db.get_balance(123) == 20.0


def test_payment_credit_once():
    svc, db = _make_service()
    db.create_payment("ord-1", 7, 25.0, "USD")
    first = db.credit_payment_once("ord-1")
    assert first is not None
    second = db.credit_payment_once("ord-1")
    assert second is None  # idempotent


def test_migration_preserves_and_adds():
    # ساخت دیتابیس و افزودن نقش
    svc, db = _make_service()
    db.set_role(999, ROLE_RESIDENTIAL_RESELLER)
    assert db.get_role(999) == ROLE_RESIDENTIAL_RESELLER
