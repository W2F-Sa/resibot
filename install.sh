#!/usr/bin/env bash
# ============================================================
#  resibot installer
#  نصب با یک دستور:
#    bash <(curl -fsSL https://raw.githubusercontent.com/W2F-Sa/resibot/main/install.sh)
#
#  - مقادیر را به‌صورت تعاملی می‌پرسد (نیازی به ساخت دستی .env نیست)
#  - سرویس systemd می‌سازد و ربات را اجرا می‌کند
#  - هنگام اجرای مجدد، دیتابیس و داده‌ها حفظ می‌شوند
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/W2F-Sa/resibot.git"
INSTALL_DIR="/opt/resibot"
SERVICE_NAME="resibot"
PY_MIN_MINOR=10   # حداقل پایتون 3.10

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
bold()  { printf "\033[1m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "این اسکریپت باید با کاربر root اجرا شود. (sudo bash ...)"
  exit 1
fi

bold "==> نصب پیش‌نیازها"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git python3 python3-venv python3-pip curl
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y git python3 python3-pip curl
elif command -v yum >/dev/null 2>&1; then
  yum install -y git python3 python3-pip curl
else
  red "مدیر بسته‌ی پشتیبانی‌شده پیدا نشد (apt/dnf/yum). پیش‌نیازها را دستی نصب کنید."
fi

# بررسی نسخه پایتون
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
if [[ "$PY_MINOR" -lt "$PY_MIN_MINOR" ]]; then
  red "پایتون 3.${PY_MIN_MINOR}+ لازم است. نسخه‌ی فعلی: 3.${PY_MINOR}"
  exit 1
fi

bold "==> دریافت/به‌روزرسانی کد"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

bold "==> ساخت محیط مجازی و نصب وابستگی‌ها"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------
#  پرسیدن مقادیر (در صورت نبود .env)
# ---------------------------------------------------------------
ENV_FILE="$INSTALL_DIR/.env"

ask() {  # ask VAR "پرسش" "default"
  local __var="$1" __prompt="$2" __default="${3:-}" __val=""
  if [[ -n "$__default" ]]; then
    read -rp "$__prompt [$__default]: " __val </dev/tty || true
    __val="${__val:-$__default}"
  else
    read -rp "$__prompt: " __val </dev/tty || true
  fi
  printf -v "$__var" '%s' "$__val"
}

ask_secret() {  # ask_secret VAR "پرسش"
  local __var="$1" __prompt="$2" __val=""
  read -rsp "$__prompt: " __val </dev/tty || true
  echo
  printf -v "$__var" '%s' "$__val"
}

if [[ -f "$ENV_FILE" ]]; then
  green "فایل .env موجود است."
  read -rp "می‌خواهید مقادیر را دوباره وارد کنید؟ (y/N): " RECONF </dev/tty || true
  RECONF="${RECONF:-N}"
else
  RECONF="y"
fi

if [[ "$RECONF" =~ ^[Yy]$ ]]; then
  bold "==> پیکربندی resibot (مقادیر را وارد کنید)"

  ask BOT_TOKEN "توکن ربات تلگرام (از @BotFather)"
  ask ADMIN_ID "آیدی عددی ادمین" "7084999553"

  echo
  bold "— اطلاعات پنل 3x-ui —"
  ask PANEL_BASE_URL "آدرس کامل پنل همراه با مسیر (مثل https://دامنه:2053/abc)"
  echo "نکته: یوزرنیم/پسورد پنل برای مدیریت اوتباند و تنظیمات لازم است."
  echo "توکن API اختیاری است و فقط برای مسیرهای /panel/api/* استفاده می‌شود."
  ask PANEL_USERNAME "یوزرنیم پنل"
  ask_secret PANEL_PASSWORD "پسورد پنل"
  ask_secret PANEL_API_TOKEN "توکن API پنل (اختیاری - برای رد شدن خالی بگذارید و Enter بزنید)"

  echo
  bold "— سرور و اینباند —"
  ask SERVER_IP "IP یا دامنه‌ی سرور (داخل لینک کانفیگ نمایش داده می‌شود)"
  ask INBOUND_SNI "SNI" "irsp.mahandevs.com"
  ask INBOUND_HOST "Host Header" "irsp.mahandevs.com"
  ask INBOUND_PATH "Path" "/get"

  echo
  bold "— SmartProxy (اوتباند) —"
  ask SMARTPROXY_USER_BASE "بخش پایه‌ی یوزرنیم (مثلاً smart-myrRsidFntpraGNS)"
  ask_secret SMARTPROXY_PASSWORD "پسورد SmartProxy"
  ask SMARTPROXY_LIFE "مدت ماندگاری IP به دقیقه (1..1440)" "120"

  echo
  bold "— قوانین فروش و قیمت‌ها —"
  ask MIN_VOLUME_GB "حداقل حجم خرید (گیگابایت)" "5"
  ask RENEW_MIN_VOLUME_GB "حداقل حجم تمدید (گیگابایت)" "5"
  ask CONFIG_DURATION_DAYS "مدت اعتبار هر کانفیگ (روز)" "30"
  ask WALLET_CURRENCY "واحد پول کیف پول" "تومان"
  ask TOMAN_PER_USD "نرخ هر دلار/تتر به تومان" "175000"
  ask PRICE_PER_GB "قیمت رزیدنتال عادی (هر گیگ)" "2.9"
  ask RESELLER_PRICE_PER_GB "قیمت رزیدنتال همکار (هر گیگ)" "2.0"
  ask V2RAY_PRICE_PER_GB "قیمت V2Ray عادی (هر گیگ)" "1.5"
  ask V2RAY_RESELLER_PRICE_PER_GB "قیمت V2Ray همکار (هر گیگ)" "1.0"
  ask RESELLER_MIN_BALANCE "حداقل موجودی همکار v2ray" "5000000"

  echo
  bold "— درگاه پرداخت NowPayments (برای شارژ کیف پول) —"
  ask NOWPAYMENTS_API_KEY "NowPayments API Key" "WYVJA75-C4AMHZA-GTH583W-MD9GR9R"
  ask NOWPAYMENTS_IPN_SECRET "NowPayments IPN Secret" "A8+fRQbTiIxxmmQcMa20zBT7sg1BcTN+"
  ask NOWPAYMENTS_PUBLIC_KEY "NowPayments Public Key" "62869df6-47c1-4cf5-a446-47c405fccbab"
  ask NOWPAYMENTS_PRICE_CURRENCY "ارز قیمت‌گذاری درگاه (مثل usd)" "usd"
  ask PUBLIC_BASE_URL "آدرس عمومی برای IPN (مثل https://دامنه:8090)"
  ask IPN_PORT "پورت سرور IPN" "8090"

  bold "==> نوشتن فایل .env"
  cat > "$ENV_FILE" <<EOF
BOT_TOKEN=${BOT_TOKEN}
ADMIN_ID=${ADMIN_ID}

PANEL_BASE_URL=${PANEL_BASE_URL}
PANEL_API_TOKEN=${PANEL_API_TOKEN}
PANEL_USERNAME=${PANEL_USERNAME}
PANEL_PASSWORD=${PANEL_PASSWORD}

SERVER_IP=${SERVER_IP}
INBOUND_SNI=${INBOUND_SNI}
INBOUND_HOST=${INBOUND_HOST}
INBOUND_PATH=${INBOUND_PATH}
INBOUND_ALPN=h2
INBOUND_FINGERPRINT=chrome
INBOUND_SC_MAX_EACH_POST_BYTES=5000000
PORT_RANGE_MIN=10000
PORT_RANGE_MAX=60000

# فالبک‌های اختیاری (اگر تنظیمات پنل خوانده نشد)
PANEL_CERT_FILE=
PANEL_KEY_FILE=
SUB_PORT=2096
SUB_PATH=/sub/
SUB_SECURE=true

SMARTPROXY_HOST=proxy.smartproxy.net
SMARTPROXY_PORT=3120
SMARTPROXY_USER_BASE=${SMARTPROXY_USER_BASE}
SMARTPROXY_PASSWORD=${SMARTPROXY_PASSWORD}
SMARTPROXY_LIFE=${SMARTPROXY_LIFE}

BRAND_NAME=w2f
BRAND_FULL=Way To Freedom

MIN_VOLUME_GB=${MIN_VOLUME_GB}
RENEW_MIN_VOLUME_GB=${RENEW_MIN_VOLUME_GB}
CONFIG_DURATION_DAYS=${CONFIG_DURATION_DAYS}

WALLET_CURRENCY=${WALLET_CURRENCY}
TOMAN_PER_USD=${TOMAN_PER_USD}
PRICE_PER_GB=${PRICE_PER_GB}
RESELLER_PRICE_PER_GB=${RESELLER_PRICE_PER_GB}
V2RAY_PRICE_PER_GB=${V2RAY_PRICE_PER_GB}
V2RAY_RESELLER_PRICE_PER_GB=${V2RAY_RESELLER_PRICE_PER_GB}
RESELLER_MIN_BALANCE=${RESELLER_MIN_BALANCE}

NOWPAYMENTS_API_KEY=${NOWPAYMENTS_API_KEY}
NOWPAYMENTS_IPN_SECRET=${NOWPAYMENTS_IPN_SECRET}
NOWPAYMENTS_PUBLIC_KEY=${NOWPAYMENTS_PUBLIC_KEY}
NOWPAYMENTS_PRICE_CURRENCY=${NOWPAYMENTS_PRICE_CURRENCY}
NOWPAYMENTS_PAY_CURRENCY=usdttrc20
PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
IPN_HOST=0.0.0.0
IPN_PORT=${IPN_PORT}

DB_PATH=data/resibot.db
EOF
  chmod 600 "$ENV_FILE"
fi

# ---------------------------------------------------------------
#  systemd
# ---------------------------------------------------------------
bold "==> ساخت سرویس systemd"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
sed "s#__INSTALL_DIR__#${INSTALL_DIR}#g" "$INSTALL_DIR/resibot.service" > "$SERVICE_PATH"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"

sleep 2
bold "==> وضعیت سرویس:"
systemctl --no-pager --lines=15 status "$SERVICE_NAME" || true

green ""
green "✅ نصب کامل شد!"
green "مشاهده‌ی لاگ زنده:   journalctl -u ${SERVICE_NAME} -f"
green "ری‌استارت:           systemctl restart ${SERVICE_NAME}"
green "آپدیت بدون از دست رفتن دیتابیس:   bash ${INSTALL_DIR}/update.sh"
