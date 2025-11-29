# axiom_tracker.py — РАБОЧАЯ ВЕРСИЯ (29.11.2025) — БЕЗ ОШИБОК
import ujson as json
import websocket
import ssl
import time
import base64
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re
import asyncio
import aiohttp
from threading import Thread


class TwitterAPI:
    _community_cache = {}
    _user_cache = {}
    COMMUNITY_REGEX = re.compile(r'https?://(?:twitter\.com|x\.com)/i/communities/(\d+)', re.IGNORECASE)
    USER_REGEX = re.compile(r'https?://(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)(?:\?|/status|$)', re.IGNORECASE)
    POST_REGEX = re.compile(r'https?://(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/status/\d+', re.IGNORECASE)

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=200, ttl_dns_cache=600, force_close=False, enable_cleanup_closed=False),
            timeout=aiohttp.ClientTimeout(total=2.0, connect=0.5)
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    @classmethod
    def is_post_url(cls, url: str) -> bool:
        return bool(cls.POST_REGEX.match(url))

    async def process_twitter_url(self, twitter_url: str) -> dict:
        if self.is_post_url(twitter_url):
            return {"error": "Post URL - skipped", "is_post": True}

        community_match = self.COMMUNITY_REGEX.search(twitter_url)
        if community_match:
            community_id = community_match.group(1)
            if community_id in self._community_cache:
                return self._community_cache[community_id]
            url = "https://api.twitterapi.io/twitter/community/info"
            headers = {"X-API-Key": self.api_key}
            params = {"community_id": community_id}
            try:
                async with self.session.get(url, headers=headers, params=params, raise_for_status=True) as resp:
                    data = await resp.json(content_type=None)
                    if "community_info" in data:
                        info = data["community_info"]
                        admin = info.get("admin", {})
                        result = {
                            "community_followers": info.get("member_count", 0),
                            "admin_username": admin.get("screen_name", "") if admin else "",
                            "admin_followers": admin.get("followers_count", 0) if admin else 0,
                            "admin_following": admin.get("friends_count", 0) if admin else 0
                        }
                        self._community_cache[community_id] = result
                        return result
            except:
                pass

        user_match = self.USER_REGEX.search(twitter_url)
        if user_match:
            username = user_match.group(1)
            if username in self._user_cache:
                return self._user_cache[username]
            url = "https://api.twitterapi.io/twitter/user/info"
            headers = {"X-API-Key": self.api_key}
            params = {"userName": username}
            try:
                async with self.session.get(url, headers=headers, params=params, raise_for_status=True) as resp:
                    data = await resp.json(content_type=None)
                    if "data" in data:
                        d = data["data"]
                        result = {"followers": d.get("followers", 0), "following": d.get("following", 0)}
                        self._user_cache[username] = result
                        return result
            except:
                pass
        return {"error": "Invalid URL"}


class AxiomTracker:
    TWITTER_REGEX = re.compile(r'https?://(?:twitter\.com|x\.com)/[^\s]+', re.IGNORECASE)
    DEV_CACHE_DURATION = 300
    ATH_CACHE_DURATION = 600

    def __init__(self, auth_file: str, twitter_api_key: str, avg_tokens_count: int = 10):
        self.auth_file = auth_file
        self.twitter_api_key = twitter_api_key
        self.avg_tokens_count = avg_tokens_count

        self.token = self.refresh_token = self.cookies = None
        self.uri_cache = {}
        self.update_pulse_cache = {}
        self.dev_mcap_cache = {}
        self.ath_cache = {}
        self.sol_price_cache = {"price": 150.0, "timestamp": 0}

        self.executor = ThreadPoolExecutor(max_workers=50)
        self.event_loop = None
        self.twitter_api = None
        self.dev_session = None
        self.ws = None
        self.running = False
        self.gui_counter = 0

        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self._load_auth_tokens()

    def _load_auth_tokens(self):
        try:
            with open(self.auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.token = data["tokens"]["auth-access-token"]
            self.refresh_token = data["tokens"]["auth-refresh-token"]
            self.cookies = f"auth-access-token={self.token}; auth-refresh-token={self.refresh_token}"
            print("Токены загружены")
        except Exception as e:
            print(f"Ошибка загрузки токенов: {e}")
            raise

    def _save_auth_tokens(self):
        try:
            with open(self.auth_file, "w", encoding="utf-8") as f:
                json.dump({"tokens": {"auth-access-token": self.token, "auth-refresh-token": self.refresh_token}}, f, indent=2)
        except:
            pass

    def _check_token_exp(self, token):
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '===').decode())
            return time.time() <= payload.get('exp', 0)
        except:
            return False

    def _refresh_access_token(self):
        url = "https://api10.axiom.trade/refresh-access-token"
        headers = {"Origin": "https://axiom.trade", "Content-Type": "application/json"}
        cookies = {"auth-refresh-token": self.refresh_token}
        try:
            r = requests.post(url, headers=headers, cookies=cookies, timeout=5)
            if r.status_code == 200:
                new_token = r.cookies.get("auth-access-token")
                if new_token:
                    self.token = new_token
                    self.refresh_token = r.cookies.get("auth-refresh-token", self.refresh_token)
                    self.cookies = f"auth-access-token={self.token}; auth-refresh-token={self.refresh_token}"
                    self._save_auth_tokens()
                    return True
        except:
            pass
        return False

    def _get_sol_price_cached(self):
        if time.time() - self.sol_price_cache["timestamp"] > 60:
            try:
                r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=3)
                if r.status_code == 200:
                    self.sol_price_cache = {"price": r.json()['solana']['usd'], "timestamp": time.time()}
            except:
                pass
        return self.sol_price_cache["price"]

    def _setup_async_loop(self):
        self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)

        async def init():
            self.twitter_api = TwitterAPI(self.twitter_api_key)
            await self.twitter_api.__aenter__()
            self.dev_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300),
                headers={'origin': 'https://axiom.trade', 'referer': 'https://axiom.trade/'}
            )
        self.event_loop.run_until_complete(init())
        self.event_loop.run_forever()

    async def _get_pair_ath_mcap(self, pair_address: str, supply: float) -> dict:
        cache_key = f"{pair_address}_{supply}"
        if cache_key in self.ath_cache:
            entry = self.ath_cache[cache_key]
            if time.time() - entry["timestamp"] < self.ATH_CACHE_DURATION:
                return {"ath_mcap": entry["ath_mcap"], "cached": True}

        if not self._check_token_exp(self.token):
            if not self._refresh_access_token():
                return {"error": "Auth failed"}

        from_ms = int((datetime.now(timezone.utc).timestamp() - 30*24*3600)*1000)
        to_ms = int(datetime.now(timezone.utc).timestamp()*1000)
        params = {
            "pairAddress": pair_address, "from": str(from_ms), "to": str(to_ms),
            "currency": "USD", "interval": "15m", "countBars": "300"
        }
        cookies = {"auth-access-token": self.token, "auth-refresh-token": self.refresh_token}

        try:
            async with self.dev_session.get('https://api.axiom.trade/pair-chart', params=params, cookies=cookies, timeout=6) as resp:
                if resp.status != 200:
                    return {"error": "chart error"}
                data = await resp.json(content_type=None)
                bars = []
                if isinstance(data, list):
                    bars = data
                elif isinstance(data, dict):
                    for k in ("bars", "data", "chart", "candles"):
                        if k in data and isinstance(data[k], list):
                            bars = data[k]
                            break
                if not bars:
                    return {"error": "no bars"}

                max_price = 0.0
                for bar in bars:
                    if isinstance(bar, (list, tuple)) and len(bar) >= 5:
                        max_price = max(max_price, float(bar[2] or 0), float(bar[4] or 0))
                    elif isinstance(bar, dict):
                        max_price = max(max_price, float(bar.get("h") or 0), float(bar.get("c") or 0))
                if max_price == 0:
                    return {"error": "zero price"}

                ath_mcap = max_price * supply
                self.ath_cache[cache_key] = {"ath_mcap": ath_mcap, "timestamp": time.time()}
                return {"ath_mcap": ath_mcap, "cached": False}
        except:
            return {"error": "ath request failed"}

    async def _get_dev_avg_mcap(self, dev_address: str) -> dict:
        if dev_address in self.dev_mcap_cache:
            entry = self.dev_mcap_cache[dev_address]
            if time.time() - entry["timestamp"] < self.DEV_CACHE_DURATION:
                return entry["result"]

        if not self._check_token_exp(self.token):
            if not self._refresh_access_token():
                return {"error": "Auth failed"}

        sol_price = self._get_sol_price_cached()
        params = {'devAddress': dev_address}
        cookies = {"auth-access-token": self.token, "auth-refresh-token": self.refresh_token}

        try:
            async with self.dev_session.get('https://api7.axiom.trade/dev-tokens-v2', params=params, cookies=cookies, timeout=5) as resp:
                if resp.status != 200:
                    return {"error": "dev api error"}
                data = await resp.json(content_type=None)
                if 'tokens' not in data or not data['tokens']:
                    return {"error": "no tokens"}

                tokens = sorted(data['tokens'], key=lambda x: x.get('createdAt', ''), reverse=True)[:self.avg_tokens_count]
                valid_mcaps = []
                tokens_info = []

                for t in tokens:
                    price = t.get('priceSol', 0)
                    supply = t.get('supply', 0)
                    if not price or not supply or price <= 0 or supply <= 0:
                        continue
                    mcap = price * supply * sol_price
                    if mcap < 100 or mcap > 1e11:
                        continue
                    valid_mcaps.append(mcap)
                    tokens_info.append({
                        "pair_address": t.get('pairAddress', 'N/A'),
                        "ticker": t.get('tokenTicker', '???'),
                        "mcap": mcap,
                        "supply": supply,
                        "ath_mcap": 0
                    })

                if not valid_mcaps:
                    return {"error": "no valid tokens"}

                avg_mcap = sum(valid_mcaps) / len(valid_mcaps)

                # ATH
                ath_tasks = []
                for ti in tokens_info:
                    if ti["pair_address"] != 'N/A':
                        ath_tasks.append(self._get_pair_ath_mcap(ti["pair_address"], ti["supply"]))
                    else:
                        ath_tasks.append(asyncio.sleep(0))

                ath_results = await asyncio.gather(*ath_tasks, return_exceptions=True)

                valid_ath = []
                for i, res in enumerate(ath_results):
                    if isinstance(res, dict) and "ath_mcap" in res:
                        tokens_info[i]["ath_mcap"] = res["ath_mcap"]
                        valid_ath.append(res["ath_mcap"])

                avg_ath_mcap = sum(valid_ath) / len(valid_ath) if valid_ath else 0

                result = {
                    "avg_mcap": avg_mcap,
                    "avg_ath_mcap": avg_ath_mcap,
                    "cached": False,
                    "valid_tokens": len(valid_mcaps),
                    "tokens_info": tokens_info
                }
                self.dev_mcap_cache[dev_address] = {"result": result, "timestamp": time.time()}
                return result
        except:
            return {"error": "dev request failed"}

    def _fetch_twitter_from_uri(self, uri):
        if not uri or uri in self.uri_cache:
            return self.uri_cache.get(uri, '')
        if uri.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
            self.uri_cache[uri] = ''
            return ''
        try:
            r = self.session.get(uri, timeout=1.5)
            if r.status_code != 200 or 'application/json' not in r.headers.get('Content-Type', ''):
                self.uri_cache[uri] = ''
                return ''
            text = r.text
            match = re.search(r'(https?://(x\.com|twitter\.com)/[A-Za-z0-9_]+)', text)
            if match:
                url = match.group(1)
                self.uri_cache[uri] = url
                return url
        except:
            pass
        self.uri_cache[uri] = ''
        return ''

    def _output_token_info(self, data, processing_time, source, twitter_stats=None,
                           migrated=None, non_migrated=None, percentage=None, cache_time=0, dev_mcap_info=None):
        has_twitter = bool(data.get('twitter') and ('twitter.com' in data['twitter'] or 'x.com' in data['twitter']))
        print("\n" + "="*80)
        print("ТОКЕН НАЙДЕН С TWITTER!" if has_twitter else "НОВЫЙ ТОКЕН")
        print(f"Тикер: {data['token_ticker']} | Twitter: {'Да' if has_twitter else 'Нет'} | Dev MC: {dev_mcap_info.get('avg_mcap', 0):,.0f}$ | ATH: {dev_mcap_info.get('avg_ath_mcap', 0):,.0f}$")
        print(f"Время: {processing_time:.3f}s")
        print("="*80 + "\n")

        try:
            from token_emitter import token_emitter
            gui_data = {
                'token_name': data['token_name'],
                'token_ticker': data['token_ticker'],
                'token_address': data['token_address'],
                'deployer_address': data['deployer_address'],
                'twitter': data.get('twitter', ''),
                'pair_address': data['pair_address'],
                'twitter_stats': twitter_stats or {},
                'dev_mcap_info': dev_mcap_info or {},
                'migrated': migrated or 0,
                'total': (migrated or 0) + (non_migrated or 0),
                'percentage': round(percentage, 2) if percentage is not None else 0,
                'processing_time_ms': int(processing_time * 1000),
                'counter': self.gui_counter + 1,
                'created_at': data.get('created_at', ''),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'avg_ath_mcap': dev_mcap_info.get('avg_ath_mcap', 0) if dev_mcap_info else 0,
                'protocol': data.get('protocol', 'unknown')
            }
            self.gui_counter += 1
            token_emitter.new_token.emit(gui_data)
        except ImportError:
            pass

    def _process_new_pairs(self, content, created_at):
        start_time = time.time()
        try:
            token_address = content.get('token_address', '')
            pair_address = content.get('pair_address', '')
            if not token_address or not pair_address:
                return

            data = {
                'token_address': token_address,
                'pair_address': pair_address,
                'token_name': content.get('token_name', 'Unknown'),
                'token_ticker': content.get('token_ticker', '???'),
                'deployer_address': content.get('deployer_address', ''),
                'twitter': content.get('twitter', '') or '',
                'token_uri': content.get('token_uri', ''),
                'created_at': created_at,
                'protocol': content.get('protocol', 'unknown')
            }

            # Twitter из URI
            if not data['twitter'] and data['token_uri']:
                data['twitter'] = self._fetch_twitter_from_uri(data['token_uri'])

            # Dev MC + ATH — СИНХРОННО, БЕЗ ОШИБОК
            try:
                dev_info = asyncio.run_coroutine_threadsafe(
                    self._get_dev_avg_mcap(data['deployer_address']),
                    self.event_loop
                ).result(timeout=12)
            except Exception as e:
                dev_info = {"error": f"timeout: {e}"}

            # Миграции
            pulse = self.update_pulse_cache.get(token_address) or self.update_pulse_cache.get(pair_address)
            migrated = non_migrated = percentage = None
            if pulse and len(pulse) > 41:
                migrated = pulse[33] or 0
                total = pulse[41] or 0
                percentage = (migrated / total * 100) if total > 0 else 0
                non_migrated = total - migrated

            self._output_token_info(
                data=data,
                processing_time=time.time() - start_time,
                source='new_pairs',
                dev_mcap_info=dev_info,
                migrated=migrated,
                non_migrated=non_migrated,
                percentage=percentage
            )
        except Exception as e:
            print(f"Ошибка обработки токена: {e}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            room = data.get("room")
            if room == "new_pairs" and data.get("content"):
                self.executor.submit(self._process_new_pairs, data["content"], data.get("created_at", ""))
            elif room == "update_pulse_v2":
                content = data.get("content", [])
                now = time.time()
                for item in content:
                    if len(item) <= 30 or not item[30]: continue
                    token_addr = item[0]
                    pair_addr = item[1]
                    try:
                        ts = datetime.fromisoformat(item[30].replace('Z', '+00:00')).timestamp()
                        if now - ts <= 15:
                            self.update_pulse_cache[token_addr] = item
                            self.update_pulse_cache[pair_addr] = item
                    except: pass
                # чистим старое
                to_del = [k for k, v in self.update_pulse_cache.items() if now - datetime.fromisoformat(v[30].replace('Z', '+00:00')).timestamp() > 15]
                for k in to_del:
                    del self.update_pulse_cache[k]
        except Exception as e:
            print(f"on_message error: {e}")

    def _on_open(self, ws):
        print("WebSocket подключён — мониторинг запущен")
        ws.send(json.dumps({"action": "join", "room": "new_pairs"}))
        ws.send(json.dumps({"action": "join", "room": "update_pulse_v2"}))

    def _on_error(self, ws, error):
        if "401" in str(error):
            print("401 — обновляю токен...")
            self._refresh_access_token()

    def _on_close(self, ws, *args):
        if self.running:
            time.sleep(3)
            self._connect_websocket()

    def _connect_websocket(self):
        if not self._check_token_exp(self.token):
            self._refresh_access_token()
        headers = {"Cookie": self.cookies, "Origin": "https://axiom.trade"}
        self.ws = websocket.WebSocketApp(
            "wss://cluster-global2.axiom.trade/",
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)

    def start(self):
        if self.running:
            return
        self.running = True
        print("Запуск Axiom трекера...")
        Thread(target=self._setup_async_loop, daemon=True).start()
        time.sleep(3)
        self._connect_websocket()


if __name__ == "__main__":
    tracker = AxiomTracker("auth_data.json", "new1_d84d121d635d4b2aa0680a22e25c08d2", avg_tokens_count=10)
    try:
        tracker.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tracker.running = False
