import aiohttp
import asyncio
import json
import time
import base64
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict

# -------------- CONFIG --------------
AUTH_FILE = r"C:\Users\Alexander\PycharmProjects\SolanaSniperBot\final\auth_data.json"
API_HOST = "https://api.axiom.trade"
CURRENCY = "USD"
INTERVAL = "15m"
COUNT_BARS = 300
FROM_ISO = "2024-01-01T00:00:00Z"
REQUEST_TIMEOUT = 12
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5
DEFAULT_SUPPLY = 1319487.100041
MAX_CONCURRENT = 10  # Максимум одновременных запросов
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
    m = re.match(r"(https://)api\d+(\.axiom\.trade.*)?", api_host)
    if m:
        suffix = m.group(2) or ""
        return "https://api10" + suffix
    return api_host.replace("api6", "api10").replace("api3", "api10").replace("api2", "api10")


async def refresh_access_token(session: aiohttp.ClientSession, refresh_token, api_refresh_host):
    if not refresh_token:
        return None
    url = api_refresh_host.rstrip("/") + "/refresh-access-token"
    try:
        async with session.post(
                url,
                headers=HEADERS,
                cookies={"auth-refresh-token": refresh_token},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as r:
            if r.status == 200:
                # prefer cookie
                new = r.cookies.get("auth-access-token")
                if new:
                    return new.value
                try:
                    j = await r.json()
                    return j.get("accessToken") or j.get("auth-access-token")
                except Exception:
                    return None
            else:
                text = await r.text()
                print(f"[refresh] status {r.status} body {text[:200]}")
                return None
    except Exception as e:
        print("[refresh] request error:", e)
        return None


# -------------- HTTP with retries --------------
async def request_with_retries(session: aiohttp.ClientSession, method, url, **kwargs):
    attempt = 0
    backoff = BACKOFF_FACTOR
    last_response = None

    while attempt < MAX_RETRIES:
        try:
            async with session.request(
                    method,
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    **kwargs
            ) as r:
                if r.status == 429:
                    attempt += 1
                    wait = int(r.headers.get("Retry-After", backoff))
                    print(f"[request] 429 RateLimit — waiting {wait}s")
                    await asyncio.sleep(wait)
                    backoff *= BACKOFF_FACTOR
                    continue

                if 500 <= r.status < 600:
                    attempt += 1
                    print(f"[request] server {r.status} — retry in {backoff}s")
                    await asyncio.sleep(backoff)
                    backoff *= BACKOFF_FACTOR
                    continue

                # Читаем response перед выходом из context manager
                status = r.status
                text = await r.text()
                headers = r.headers

                class Response:
                    def __init__(self, status, text, headers):
                        self.status = status
                        self.text = text
                        self.headers = headers

                    def json(self):
                        return json.loads(self.text)

                return Response(status, text, headers)

        except asyncio.TimeoutError:
            attempt += 1
            print(f"[request] timeout ({attempt}/{MAX_RETRIES}). retry {backoff}s")
            await asyncio.sleep(backoff)
            backoff *= BACKOFF_FACTOR
            continue
        except Exception as e:
            attempt += 1
            print(f"[request] exception ({attempt}/{MAX_RETRIES}): {e}. retry {backoff}s")
            await asyncio.sleep(backoff)
            backoff *= BACKOFF_FACTOR
            continue

    return last_response


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
        for k in ("bars", "data", "chart", "candles", "ohlc", "result"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []


def fmt_price(x):
    return f"{x:.8f}"


def fmt_marketcap(x):
    return f"{x:,.6f}"


# -------------- Main async functions --------------
async def get_token_ath(
        session: aiohttp.ClientSession,
        pair_address: str,
        cookies: dict,
        access_token: str,
        refresh_token: str
) -> Dict:
    """Получает ATH для одного токена"""

    params = {
        "pairAddress": pair_address,
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
    r = await request_with_retries(session, "GET", url_chart, params=params, cookies=cookies)

    if r is None:
        return {"pair": pair_address, "error": "no response"}

    if r.status == 401 or r.status == 403:
        print(f"[{pair_address[:8]}...] 401/403 — refreshing and retrying")
        new_access = await refresh_access_token(session, refresh_token, build_refresh_host(API_HOST))
        if new_access:
            cookies["auth-access-token"] = new_access
            try:
                save_tokens(new_access, refresh_token)
            except:
                pass
            r = await request_with_retries(session, "GET", url_chart, params=params, cookies=cookies)

    if r.status != 200:
        return {"pair": pair_address, "error": f"HTTP {r.status}"}

    try:
        chart_json = r.json()
    except Exception:
        return {"pair": pair_address, "error": "response not json"}

    bars = try_extract_bars(chart_json)
    if not bars:
        return {"pair": pair_address, "error": "no bars found"}

    # Get supply
    url_info = API_HOST.rstrip("/") + "/pair-info"
    r2 = await request_with_retries(session, "GET", url_info, params={"pairAddress": pair_address}, cookies=cookies)

    supply = None
    if r2 and r2.status == 200:
        try:
            info = r2.json()
            for key in ("supply", "totalSupply", "tokenSupply", "circulatingSupply", "circulating_supply"):
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

    # Calculate ATH
    closes = []
    for b in bars:
        if isinstance(b, (list, tuple)):
            closes.append(float(b[4]))
        elif isinstance(b, dict):
            closes.append(float(b.get("c") or b.get("close") or b.get("price") or 0.0))

    if not closes:
        return {"pair": pair_address, "error": "no close prices"}

    ath_price = max(closes)
    ath_mc = ath_price * supply
    current_price = closes[-1]
    current_mc = current_price * supply

    return {
        "pair": pair_address,
        "ath_price": ath_price,
        "ath_marketcap": ath_mc,
        "current_price": current_price,
        "current_marketcap": current_mc,
        "supply": supply,
        "bars_count": len(bars)
    }


async def get_multiple_ath(pair_addresses: List[str]) -> List[Dict]:
    """Получает ATH для нескольких токенов параллельно"""

    # Load tokens once
    access, refresh = load_tokens()
    if token_expired(access):
        print("[token] access expired → refreshing")
        async with aiohttp.ClientSession(headers=HEADERS) as temp_session:
            api_refresh = build_refresh_host(API_HOST)
            new_access = await refresh_access_token(temp_session, refresh, api_refresh)
            if new_access:
                access = new_access
                try:
                    save_tokens(access, refresh)
                    print("[token] saved new access")
                except Exception as e:
                    print("[token] save failed:", e)

    cookies = {}
    if refresh:
        cookies["auth-refresh-token"] = refresh
    if access:
        cookies["auth-access-token"] = access

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def bounded_get_ath(session, pair):
        async with semaphore:
            return await get_token_ath(session, pair, cookies.copy(), access, refresh)

    # Run all requests concurrently
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [bounded_get_ath(session, pair) for pair in pair_addresses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "pair": pair_addresses[i],
                "error": str(result)
            })
        else:
            processed_results.append(result)

    return processed_results


# -------------- User-friendly functions --------------
async def get_avg_ath(pair_addresses: List[str]) -> Dict:
    """Получает средний ATH для списка токенов"""
    results = await get_multiple_ath(pair_addresses)

    valid_results = [r for r in results if "error" not in r]

    if not valid_results:
        return {
            "avg_ath_price": 0,
            "avg_ath_marketcap": 0,
            "successful": 0,
            "failed": len(results),
            "results": results
        }

    avg_ath_price = sum(r["ath_price"] for r in valid_results) / len(valid_results)
    avg_ath_mc = sum(r["ath_marketcap"] for r in valid_results) / len(valid_results)

    return {
        "avg_ath_price": avg_ath_price,
        "avg_ath_marketcap": avg_ath_mc,
        "successful": len(valid_results),
        "failed": len(results) - len(valid_results),
        "results": results
    }


def print_results(results: List[Dict]):
    """Красиво выводит результаты"""
    print("\n" + "=" * 100)
    print(f"{'Pair Address':<50} {'ATH Price':>15} {'ATH MarketCap':>20} {'Status'}")
    print("=" * 100)

    for r in results:
        pair_short = r["pair"][:12] + "..." + r["pair"][-8:]
        if "error" in r:
            print(f"{pair_short:<50} {'ERROR':<15} {'N/A':<20} {r['error']}")
        else:
            print(f"{pair_short:<50} {fmt_price(r['ath_price']):>15} {fmt_marketcap(r['ath_marketcap']):>20} ✓")

    print("=" * 100)


# -------------- Example usage --------------
async def main():
    # Пример: список адресов токенов для проверки
    pair_addresses = [
        "CSsUMyMXndptPpdQ8jfKZFBgtK1PaQLrFir5JdCvo58o",
        "HpxFyBtTmZb6w72YD8AfJDH3hWsWBQzJSLPTRcKhG29N"
        # Добавь сюда больше адресов
    ]

    print(f"🚀 Запрашиваю данные для {len(pair_addresses)} токенов...")
    start_time = time.time()

    # Получаем средний ATH
    result = await get_avg_ath(pair_addresses)

    elapsed = time.time() - start_time

    # Выводим результаты
    print_results(result["results"])

    print(f"\n📊 ИТОГИ:")
    print(f"   Средний ATH Price: {fmt_price(result['avg_ath_price'])}")
    print(f"   Средний ATH MarketCap: {fmt_marketcap(result['avg_ath_marketcap'])}")
    print(f"   Успешно: {result['successful']}/{result['successful'] + result['failed']}")
    print(f"   ⏱️  Время выполнения: {elapsed:.2f}s")
    print(f"   ⚡ Скорость: {len(pair_addresses) / elapsed:.2f} токенов/сек\n")


if __name__ == "__main__":
    asyncio.run(main())