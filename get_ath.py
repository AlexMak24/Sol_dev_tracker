
import requests
import json
import time
import base64
import re
from datetime import datetime, timezone

# -------------- CONFIG --------------
AUTH_FILE = r"C:\Users\Alexander\PycharmProjects\SolanaSniperBot\final\auth_data.json"
API_HOST = "https://api.axiom.trade"   # <- оставь один endpoint, меняй при необходимости
PAIR_ADDRESS = "E5dBvGrCbAZL8X3TBaLpE2QUdGFLh8E92uT6Rn9e1PDx"
CURRENCY = "USD"                        # или "USD"
INTERVAL = "15m"
COUNT_BARS = 300
FROM_ISO = "2024-01-01T00:00:00Z"
REQUEST_TIMEOUT = 12
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5
# Если supply не найден, брать это значение (пример из PumpFun, поменяй при нужде)
DEFAULT_SUPPLY = 1319487.100041
# -------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://axiom.trade",
    "Referer": "https://axiom.trade/"
}

# -------------- Token utilities --------------
def load_tokens(path=AUTH_FILE):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    t = data.get("tokens", {})
    return t.get("auth-access-token"), t.get("auth-refresh-token")

def save_tokens(access, refresh, path=AUTH_FILE):
    with open(path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data.setdefault("tokens", {})
        data["tokens"]["auth-access-token"] = access
        data["tokens"]["auth-refresh-token"] = refresh
        f.seek(0)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.truncate()

def decode_jwt_payload(token):
    if not token or "." not in token:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    except Exception:
        return {}

def token_expired(access_token, leeway=10):
    payload = decode_jwt_payload(access_token)
    exp = payload.get("exp")
    if not exp:
        return True
    return int(time.time()) >= (int(exp) - leeway)

def build_refresh_host(api_host):
    # https://api3.axiom.trade -> https://api10.axiom.trade
    m = re.match(r"(https://)api\d+(\.axiom\.trade.*)?", api_host)
    if m:
        suffix = m.group(2) or ""
        return "https://api10" + suffix
    return api_host.replace("api6", "api10").replace("api3", "api10").replace("api2", "api10")

def refresh_access_token(session, refresh_token, api_refresh_host):
    if not refresh_token:
        return None
    url = api_refresh_host.rstrip("/") + "/refresh-access-token"
    try:
        r = session.post(url, headers=HEADERS, cookies={"auth-refresh-token": refresh_token}, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        print("[refresh] request error:", e)
        return None
    if r.status_code == 200:
        # prefer cookie
        new = r.cookies.get("auth-access-token")
        if new:
            return new
        try:
            j = r.json()
            return j.get("accessToken") or j.get("auth-access-token")
        except Exception:
            return None
    else:
        print(f"[refresh] status {r.status_code} body {r.text[:200]}")
        return None

# -------------- HTTP with retries --------------
def request_with_retries(session, method, url, **kwargs):
    attempt = 0
    backoff = BACKOFF_FACTOR
    while attempt < MAX_RETRIES:
        try:
            r = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        except Exception as e:
            attempt += 1
            print(f"[request] exception ({attempt}/{MAX_RETRIES}): {e}. retry {backoff}s")
            time.sleep(backoff)
            backoff *= BACKOFF_FACTOR
            continue
        if r.status_code == 429:
            attempt += 1
            wait = int(r.headers.get("Retry-After") or backoff)
            print(f"[request] 429 RateLimit — waiting {wait}s")
            time.sleep(wait)
            backoff *= BACKOFF_FACTOR
            continue
        if 500 <= r.status_code < 600:
            attempt += 1
            print(f"[request] server {r.status_code} — retry in {backoff}s")
            time.sleep(backoff)
            backoff *= BACKOFF_FACTOR
            continue
        return r
    # final attempt: raise or return last response if exists
    return r

# -------------- Helpers --------------
def iso_to_ms(iso_str):
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)

def now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def try_extract_bars(obj):
    if not obj:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("bars","data","chart","candles","ohlc","result"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []

def fmt_price(x):
    # avoid scientific notation, show up to 8 decimals, strip trailing zeros
    return f"{x:.8f}"

def fmt_marketcap(x):
    # show with 6 decimals and thousand separators
    return f"{x:,.6f}"

# -------------- Main flow --------------
def main():
    # prepare session
    session = requests.Session()
    session.headers.update(HEADERS)

    access, refresh = load_tokens()
    if token_expired(access):
        print("[token] access expired → refreshing")
        api_refresh = build_refresh_host(API_HOST)
        new_access = refresh_access_token(session, refresh, api_refresh)
        if new_access:
            access = new_access
            try:
                save_tokens(access, refresh)
                print("[token] saved new access")
            except Exception as e:
                print("[token] save failed:", e)
        else:
            print("[token] refresh failed — will try request with current tokens (may 401)")

    cookies = {}
    if refresh: cookies["auth-refresh-token"] = refresh
    if access: cookies["auth-access-token"] = access

    # 1) pair-chart
    params = {
        "pairAddress": PAIR_ADDRESS,
        "from": str(iso_to_ms(FROM_ISO)),
        "to": str(now_ms()),
        "currency": CURRENCY,
        "interval": INTERVAL,
        "openTrading": str(iso_to_ms(FROM_ISO)),
        "lastTransactionTime": str(now_ms()),
        "countBars": str(COUNT_BARS),
        "showOutliers": "false",
        "isNew": "false"
    }
    url_chart = API_HOST.rstrip("/") + "/pair-chart"
    r = request_with_retries(session, "GET", url_chart, params=params, cookies=cookies)
    if r is None:
        print("[pair-chart] no response")
        return
    if r.status_code == 401 or r.status_code == 403:
        # try refresh once
        print("[pair-chart] 401/403 — refreshing and retrying")
        new_access = refresh_access_token(session, refresh, build_refresh_host(API_HOST))
        if new_access:
            access = new_access
            cookies["auth-access-token"] = access
            try:
                save_tokens(access, refresh)
            except: pass
            r = request_with_retries(session, "GET", url_chart, params=params, cookies=cookies)
    if r.status_code != 200:
        print(f"[pair-chart] HTTP {r.status_code} {r.text[:400]}")
        return

    try:
        chart_json = r.json()
    except Exception:
        print("[pair-chart] response not json")
        return

    bars = try_extract_bars(chart_json)
    if not bars:
        print("📊 Свечей не найдено.")
        return

    # 2) pair-info -> supply
    url_info = API_HOST.rstrip("/") + "/pair-info"
    r2 = request_with_retries(session, "GET", url_info, params={"pairAddress": PAIR_ADDRESS}, cookies=cookies)
    supply = None
    if r2 and r2.status_code == 200:
        try:
            info = r2.json()
            for key in ("supply","totalSupply","tokenSupply","circulatingSupply","circulating_supply"):
                if key in info and info[key] is not None:
                    try:
                        supply = float(info[key])
                        break
                    except:
                        pass
        except Exception:
            pass

    if supply is None:
        supply = DEFAULT_SUPPLY
        used_default = True
    else:
        used_default = False

    # 3) print table with marketcap per candle
    print(f"\n📊 Всего свечей: {len(bars)}  (supply used: {supply:,} {'(default)' if used_default else ''})\n")
    hdr = f"{'Time':<19} {'Open':>14} {'High':>14} {'Low':>14} {'Close':>14} {'Vol':>12} {'MarketCap':>18}"
    print(hdr)
    print("-" * len(hdr))

    for b in bars:
        # handle formats
        if isinstance(b, (list, tuple)):
            ts = int(b[0])
            o = float(b[1])
            h = float(b[2])
            l = float(b[3])
            c = float(b[4])
            vol = float(b[5]) if len(b) > 5 and b[5] is not None else 0.0
        elif isinstance(b, dict):
            ts = int(b.get("timestamp") or b.get("t") or 0)
            o = float(b.get("o") or b.get("open") or 0.0)
            h = float(b.get("h") or b.get("high") or 0.0)
            l = float(b.get("l") or b.get("low") or 0.0)
            # close may be 'c' or 'close' or 'price'
            c = float(b.get("c") or b.get("close") or b.get("price") or 0.0)
            vol = float(b.get("v") or b.get("volume") or 0.0)
        else:
            continue

        tstr = datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        mc = c * supply if (c is not None) else None
        mc_str = fmt_marketcap(mc) if mc is not None else "N/A"
        print(f"{tstr:<19} {fmt_price(o):>14} {fmt_price(h):>14} {fmt_price(l):>14} {fmt_price(c):>14} {vol:12.6f} {mc_str:>18}")

    # final summary: ATH by close and marketcap
    closes = []
    for b in bars:
        if isinstance(b, (list, tuple)):
            closes.append(float(b[4]))
        elif isinstance(b, dict):
            closes.append(float(b.get("c") or b.get("close") or b.get("price") or 0.0))
    if closes:
        ath_price = max(closes)
        ath_mc = ath_price * supply
        print("\nИтоги:")
        print(f"  ATH price (in window): {fmt_price(ath_price)}")
        print(f"  ATH market cap (approx): {fmt_marketcap(ath_mc)} (price {fmt_price(ath_price)} * supply {supply:,})")

if __name__ == "__main__":
    main()
