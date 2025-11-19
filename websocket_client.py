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
import queue


class TwitterAPI:
    """Класс для работы с Twitter API с кэшированием"""
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
            connector=aiohttp.TCPConnector(
                limit=200,
                ttl_dns_cache=600,
                force_close=False,
                enable_cleanup_closed=False
            ),
            timeout=aiohttp.ClientTimeout(total=2.0, connect=0.5)
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    @classmethod
    def is_post_url(cls, url: str) -> bool:
        """Проверяет, является ли URL постом в Twitter"""
        return bool(cls.POST_REGEX.match(url))

    async def get_user_follow_stats(self, username: str) -> dict:
        if username in self._user_cache:
            return self._user_cache[username]
        url = "https://api.twitterapi.io/twitter/user/info"
        headers = {"X-API-Key": self.api_key}
        params = {"userName": username}
        try:
            async with self.session.get(url, headers=headers, params=params, raise_for_status=True) as response:
                data = await response.json(content_type=None)
                if "data" in data:
                    result = {
                        "followers": data["data"].get("followers", 0),
                        "following": data["data"].get("following", 0)
                    }
                    self._user_cache[username] = result
                    return result
                return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

    async def get_community_info(self, community_id: str) -> dict:
        if community_id in self._community_cache:
            return self._community_cache[community_id]
        url = "https://api.twitterapi.io/twitter/community/info"
        headers = {"X-API-Key": self.api_key}
        params = {"community_id": community_id}
        try:
            async with self.session.get(url, headers=headers, params=params, raise_for_status=True) as response:
                community_data = await response.json(content_type=None)
                if "community_info" in community_data:
                    community_info = community_data["community_info"]
                    admin = community_info.get("admin", {})
                    result = {
                        "community_followers": community_info.get("member_count", 0),
                        "admin_username": admin.get("screen_name", "") if admin else "",
                        "admin_followers": admin.get("followers_count", 0) if admin else 0,
                        "admin_following": admin.get("friends_count", 0) if admin else 0
                    } if admin else {"error": "Admin not found"}
                    self._community_cache[community_id] = result
                    return result
                return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

    async def process_twitter_url(self, twitter_url: str) -> dict:
        if self.is_post_url(twitter_url):
            return {"error": "Post URL - skipped", "is_post": True}

        community_match = self.COMMUNITY_REGEX.search(twitter_url)
        if community_match:
            community_id = community_match.group(1)
            return await self.get_community_info(community_id)

        user_match = self.USER_REGEX.search(twitter_url)
        if user_match:
            username = user_match.group(1)
            return await self.get_user_follow_stats(username)

        return {"error": "Invalid URL"}


class AxiomTracker:
    """Главный класс для отслеживания токенов Axiom"""

    TWITTER_REGEX = re.compile(r'https?://(?:twitter\.com|x\.com)/[^\s]+', re.IGNORECASE)
    DEV_CACHE_DURATION = 300  # 5 минут
    ATH_CACHE_DURATION = 600  # 10 минут для ATH

    def __init__(self, auth_file: str, twitter_api_key: str, avg_tokens_count: int = 10):
        self.auth_file = auth_file
        self.twitter_api_key = twitter_api_key
        self.avg_tokens_count = avg_tokens_count

        # Токены и куки
        self.token = None
        self.refresh_token = None
        self.cookies = None

        # Кэши
        self.uri_cache = {}
        self.update_pulse_cache = {}
        self.dev_mcap_cache = {}
        self.ath_cache = {}  # ← Кэш для ATH
        self.sol_price_cache = {"price": 150.0, "timestamp": 0}

        # Очередь и пулы
        self.pending_queue = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=50)

        # Асинхронные компоненты
        self.event_loop = None
        self.twitter_api = None
        self.dev_session = None

        # WebSocket
        self.ws = None
        self.running = False

        # GUI счетчик
        self.gui_counter = 0

        # HTTP сессия
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Загружаем токены
        self._load_auth_tokens()

    def _load_auth_tokens(self):
        """Загрузка токенов из файла"""
        try:
            with open(self.auth_file, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
            self.token = auth_data["tokens"]["auth-access-token"]
            self.refresh_token = auth_data["tokens"]["auth-refresh-token"]
            self.cookies = f"auth-access-token={self.token}; auth-refresh-token={self.refresh_token}"
            print("✅ Токены загружены")
        except (FileNotFoundError, KeyError) as e:
            print(f"❌ Ошибка загрузки токенов: {e}")
            raise

    def _save_auth_tokens(self):
        """Сохранение токенов в файл"""
        try:
            with open(self.auth_file, "w", encoding="utf-8") as f:
                json.dump({
                    "tokens": {
                        "auth-access-token": self.token,
                        "auth-refresh-token": self.refresh_token
                    }
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения токенов: {e}")

    def _check_token_exp(self, token):
        """Проверка срока действия токена"""
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '===').decode('utf-8'))
            return int(time.time()) <= payload.get('exp', 0)
        except:
            return False

    def _refresh_access_token(self):
        """Обновление access токена"""
        url = "https://api10.axiom.trade/refresh-access-token"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://axiom.trade"
        }
        cookies = {"auth-refresh-token": self.refresh_token, "auth-access-token": self.token}
        try:
            resp = requests.post(url, headers=headers, cookies=cookies, timeout=5)
            resp.raise_for_status()
            if resp.status_code == 200:
                new_access = resp.cookies.get("auth-access-token")
                new_refresh = resp.cookies.get("auth-refresh-token", self.refresh_token)
                if new_access:
                    self.token = new_access
                    self.refresh_token = new_refresh
                    self.cookies = f"auth-access-token={self.token}; auth-refresh-token={self.refresh_token}"
                    self._save_auth_tokens()
                    return True
            return False
        except requests.RequestException as e:
            print(f"⚠️ Ошибка обновления токена: {e}")
            return False

    def _get_sol_price_cached(self):
        """Получение цены SOL с кэшированием"""
        current_time = time.time()
        if current_time - self.sol_price_cache["timestamp"] > 60:
            try:
                resp = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                                    timeout=2)
                if resp.status_code == 200:
                    self.sol_price_cache["price"] = resp.json()['solana']['usd']
                    self.sol_price_cache["timestamp"] = current_time
            except:
                pass
        return self.sol_price_cache["price"]

    def _setup_async_loop(self):
        """Создание event loop в отдельном потоке"""
        self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)

        async def init_apis():
            self.twitter_api = TwitterAPI(self.twitter_api_key)
            await self.twitter_api.__aenter__()

            self.dev_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300),
                headers={
                    'accept': 'application/json',
                    'origin': 'https://axiom.trade',
                    'referer': 'https://axiom.trade/',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                }
            )

        self.event_loop.run_until_complete(init_apis())
        self.event_loop.run_forever()

    def _run_async_task(self, coro):
        """Запуск асинхронной задачи в event loop"""
        if self.event_loop and self.twitter_api:
            future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
            try:
                return future.result(timeout=2.0)
            except:
                return None
        return None

    async def _get_pair_ath_mcap(self, pair_address: str, supply: float) -> dict:
        """Получение ATH market cap для пары с кэшированием"""
        cache_key = f"{pair_address}_{supply}"

        # Проверяем кэш
        if cache_key in self.ath_cache:
            cache_entry = self.ath_cache[cache_key]
            age = time.time() - cache_entry["timestamp"]
            if age < self.ATH_CACHE_DURATION:
                return {
                    "ath_mcap": cache_entry["ath_mcap"],
                    "cached": True,
                    "cache_age": int(age)
                }

        if not self._check_token_exp(self.token):
            if not self._refresh_access_token():
                return {"error": "Auth failed"}

        sol_price = self._get_sol_price_cached()

        # Параметры для получения свечей (30 дней)
        from_ms = int((datetime.now(timezone.utc).timestamp() - 30 * 24 * 3600) * 1000)
        to_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        params = {
            "pairAddress": pair_address,
            "from": str(from_ms),
            "to": str(to_ms),
            "currency": "USD",
            "interval": "15m",
            "openTrading": str(from_ms),
            "lastTransactionTime": str(to_ms),
            "countBars": "300",
            "showOutliers": "false",
            "isNew": "false"
        }

        cookies_dict = {"auth-access-token": self.token, "auth-refresh-token": self.refresh_token}

        try:
            async with self.dev_session.get('https://api.axiom.trade/pair-chart',
                                            params=params,
                                            cookies=cookies_dict,
                                            timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return {"error": f"API error: {resp.status}"}

                data = await resp.json(content_type=None)

                # Извлекаем свечи
                bars = []
                if isinstance(data, list):
                    bars = data
                elif isinstance(data, dict):
                    for k in ("bars", "data", "chart", "candles", "ohlc", "result"):
                        v = data.get(k)
                        if isinstance(v, list):
                            bars = v
                            break

                if not bars:
                    return {"error": "No bars found"}

                # Находим ATH price
                max_price = 0.0
                for bar in bars:
                    if isinstance(bar, (list, tuple)) and len(bar) >= 5:
                        high = float(bar[2]) if bar[2] is not None else 0.0
                        close = float(bar[4]) if bar[4] is not None else 0.0
                        max_price = max(max_price, high, close)
                    elif isinstance(bar, dict):
                        high = float(bar.get("h") or bar.get("high") or 0.0)
                        close = float(bar.get("c") or bar.get("close") or bar.get("price") or 0.0)
                        max_price = max(max_price, high, close)

                if max_price == 0:
                    return {"error": "No valid price data"}

                ath_mcap = max_price * supply

                # Кэшируем
                self.ath_cache[cache_key] = {
                    "ath_mcap": ath_mcap,
                    "timestamp": time.time()
                }

                return {
                    "ath_mcap": ath_mcap,
                    "ath_price": max_price,
                    "cached": False
                }

        except Exception as e:
            return {"error": str(e)}

    async def _get_dev_avg_mcap(self, dev_address: str) -> dict:
        """Получение avg market cap дева + ATH market cap с кэшированием"""
        if dev_address in self.dev_mcap_cache:
            cache_entry = self.dev_mcap_cache[dev_address]
            age = time.time() - cache_entry["timestamp"]
            if age < self.DEV_CACHE_DURATION:
                return {
                    "avg_mcap": cache_entry["avg_mcap"],
                    "avg_ath_mcap": cache_entry.get("avg_ath_mcap", 0),
                    "cached": True,
                    "cache_age": int(age),
                    "tokens_info": cache_entry.get("tokens_info", [])
                }

        if not self._check_token_exp(self.token):
            if not self._refresh_access_token():
                return {"error": "Auth failed"}

        sol_price = self._get_sol_price_cached()
        params = {'devAddress': dev_address}
        cookies_dict = {"auth-access-token": self.token, "auth-refresh-token": self.refresh_token}

        try:
            async with self.dev_session.get('https://api7.axiom.trade/dev-tokens-v2', params=params,
                                            cookies=cookies_dict, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    return {"error": f"API error: {resp.status}"}

                data = await resp.json(content_type=None)

                if 'tokens' not in data or not data['tokens']:
                    return {"error": "No tokens found"}

                tokens = sorted(data['tokens'], key=lambda x: x.get('createdAt', ''), reverse=True)[
                         :self.avg_tokens_count]

                valid_mcaps = []
                tokens_info = []
                MAX_REASONABLE_MCAP = 100_000_000_000

                # Сначала собираем current mcap
                for token in tokens:
                    price_sol = token.get('priceSol', 0)
                    supply = token.get('supply', 0)

                    if not price_sol or not supply:
                        continue
                    if price_sol <= 0 or supply <= 0:
                        continue
                    if price_sol > 1000000 or supply > 1e15:
                        continue

                    mcap = price_sol * supply * sol_price

                    if mcap < 100:
                        continue
                    if mcap > MAX_REASONABLE_MCAP:
                        continue

                    valid_mcaps.append(mcap)

                    tokens_info.append({
                        "pair_address": token.get('pairAddress', 'N/A'),
                        "ticker": token.get('tokenTicker', 'N/A'),
                        "mcap": mcap,
                        "supply": supply,
                        "ath_mcap": 0
                    })

                if not valid_mcaps:
                    return {"error": "No valid tokens"}

                avg_mcap = sum(valid_mcaps) / len(valid_mcaps)

                if avg_mcap > MAX_REASONABLE_MCAP:
                    return {"error": "Invalid data"}

                # ← ПОЛУЧАЕМ ATH ДЛЯ КАЖДОГО ТОКЕНА
                ath_tasks = []
                for token_info in tokens_info:
                    if token_info["pair_address"] != 'N/A':
                        ath_tasks.append(
                            self._get_pair_ath_mcap(token_info["pair_address"], token_info["supply"])
                        )
                    else:
                        ath_tasks.append(asyncio.sleep(0))

                # Параллельно получаем все ATH
                ath_results = await asyncio.gather(*ath_tasks, return_exceptions=True)

                # Заполняем ATH
                valid_ath_mcaps = []
                for i, ath_result in enumerate(ath_results):
                    if isinstance(ath_result, dict) and "ath_mcap" in ath_result:
                        tokens_info[i]["ath_mcap"] = ath_result["ath_mcap"]
                        valid_ath_mcaps.append(ath_result["ath_mcap"])
                    elif isinstance(ath_result, Exception):
                        tokens_info[i]["ath_mcap"] = 0

                # AVG ATH Market Cap
                avg_ath_mcap = sum(valid_ath_mcaps) / len(valid_ath_mcaps) if valid_ath_mcaps else 0

                # Кэшируем
                self.dev_mcap_cache[dev_address] = {
                    "avg_mcap": avg_mcap,
                    "avg_ath_mcap": avg_ath_mcap,
                    "timestamp": time.time(),
                    "valid_tokens": len(valid_mcaps),
                    "tokens_info": tokens_info
                }

                return {
                    "avg_mcap": avg_mcap,
                    "avg_ath_mcap": avg_ath_mcap,
                    "cached": False,
                    "valid_tokens": len(valid_mcaps),
                    "tokens_info": tokens_info
                }

        except Exception as e:
            return {"error": str(e)}

    def _extract_twitter_from_json(self, data):
        """Максимально полное извлечение Twitter из любой JSON структуры"""
        if not data:
            return ''

        def normalize_twitter_url(url):
            if not url:
                return ''
            url = str(url).strip()
            if not url or url.lower() in ['null', 'none', 'n/a', '']:
                return ''
            if 'twitter.com' in url.lower() or 'x.com' in url.lower():
                return url
            url = url.lstrip('@')
            username = re.sub(r'[^A-Za-z0-9_]', '', url)
            if username and len(username) >= 1:
                return f'https://x.com/{username}'
            return ''

        if isinstance(data, dict):
            twitter_keys = [
                'twitter', 'Twitter', 'TWITTER', 'x', 'X',
                'twitterUrl', 'twitter_url', 'TwitterUrl',
                'twitterLink', 'twitter_link', 'TwitterLink',
                'twitterHandle', 'twitter_handle', 'TwitterHandle',
                'twitterUsername', 'twitter_username',
                'social_twitter', 'socialTwitter',
                'handle', 'username'
            ]

            for key in twitter_keys:
                if key in data and data[key]:
                    url = normalize_twitter_url(data[key])
                    if url:
                        return url

            if 'extensions' in data and isinstance(data['extensions'], dict):
                if 'twitter' in data['extensions'] and data['extensions']['twitter']:
                    url = normalize_twitter_url(data['extensions']['twitter'])
                    if url:
                        return url

            parent_keys = [
                'social', 'socials', 'Social', 'Socials',
                'links', 'Links', 'LINKS',
                'urls', 'Urls', 'URLS',
                'external_url', 'externalUrl', 'ExternalUrl',
                'socialLinks', 'social_links', 'SocialLinks',
                'socialMedia', 'social_media', 'SocialMedia',
                'contacts', 'Contacts',
                'extensions', 'Extensions',
                'attributes', 'Attributes'
            ]

            for parent in parent_keys:
                if parent in data:
                    parent_data = data[parent]
                    if isinstance(parent_data, dict):
                        for key in twitter_keys:
                            if key in parent_data and parent_data[key]:
                                url = normalize_twitter_url(parent_data[key])
                                if url:
                                    return url
                    elif isinstance(parent_data, list):
                        for item in parent_data:
                            if isinstance(item, dict):
                                item_type = str(item.get('type', '')).lower()
                                item_name = str(item.get('name', '')).lower()
                                if 'twitter' in item_type or 'twitter' in item_name or 'x' == item_type:
                                    for url_key in ['url', 'value', 'link', 'href', 'address']:
                                        if url_key in item and item[url_key]:
                                            url = normalize_twitter_url(item[url_key])
                                            if url:
                                                return url
                                for key in twitter_keys:
                                    if key in item and item[key]:
                                        url = normalize_twitter_url(item[key])
                                        if url:
                                            return url

            if 'properties' in data and isinstance(data['properties'], dict):
                props = data['properties']
                for key in twitter_keys:
                    if key in props and props[key]:
                        url = normalize_twitter_url(props[key])
                        if url:
                            return url

        json_str = json.dumps(data)
        match = self.TWITTER_REGEX.search(json_str)
        if match:
            return match.group(0)

        username_patterns = [
            r'"twitter[^"]*":\s*"@?([A-Za-z0-9_]{1,15})"',
            r'"x[^"]*":\s*"@?([A-Za-z0-9_]{1,15})"',
            r'"handle[^"]*":\s*"@?([A-Za-z0-9_]{1,15})"',
            r'@([A-Za-z0-9_]{1,15})'
        ]

        for pattern in username_patterns:
            match = re.search(pattern, json_str, re.IGNORECASE)
            if match:
                username = match.group(1)
                if username and username.lower() not in ['null', 'none', 'n', 'a']:
                    return f'https://x.com/{username}'

        return ''

    def _fetch_twitter_from_uri(self, token_uri):
        """Быстрый запрос к token_uri с проверками"""
        if not token_uri or token_uri in self.uri_cache:
            return self.uri_cache.get(token_uri, '')
        if token_uri.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
            self.uri_cache[token_uri] = ''
            return ''
        try:
            resp = self.session.get(token_uri, timeout=1.0)
            resp.raise_for_status()
            if 'application/json' not in resp.headers.get('Content-Type', ''):
                self.uri_cache[token_uri] = ''
                return ''
            data = json.loads(resp.text)
            twitter = self._extract_twitter_from_json(data)
            self.uri_cache[token_uri] = twitter
            return twitter
        except:
            pass
        self.uri_cache[token_uri] = ''
        return ''

    def _output_token_info(self, data, processing_time, source, twitter_stats=None, migrated=None,
                           non_migrated=None, percentage=None, cache_time=0, dev_mcap_info=None):
        """Вывод в КОНСОЛЬ + ЭМИТ В GUI"""
        has_twitter = data['twitter'] and data['twitter'].strip() and data['twitter'] != 'null' and (
                'twitter.com' in data['twitter'] or 'x.com' in data['twitter'])
        is_post = TwitterAPI.is_post_url(data['twitter']) if has_twitter else False

        # === КОНСОЛЬНЫЙ ВЫВОД (FULL) ===
        print("\n" + "=" * 80)
        if has_twitter and not is_post:
            print("ТОКЕН НАЙДЕН С TWITTER!")
        elif is_post:
            print("ТОКЕН С ПОСТОМ TWITTER (ПРОПУЩЕН)")
        else:
            print("НОВЫЙ ТОКЕН")
        print("=" * 80)
        print(f"Token Address:    {data['token_address']}")
        print(f"Pair Address:     {data['pair_address']}")
        print(f"Token Name:       {data['token_name']}")
        print(f"Token Ticker:     {data['token_ticker']}")
        print(f"Deployer:         {data['deployer_address']}")
        print(f"Protocol:         {data['protocol']}")

        if is_post:
            print(f"Twitter:          Post URL (skipped) - {data['twitter']}")
        elif has_twitter:
            print(f"Twitter:          {data['twitter']}")
        else:
            print(f"Twitter:          Not found")

        # ← ВЫВОД DEV STATS + ATH (КОНСОЛЬ С ДЕТАЛЬНОЙ ИНФО)
        if dev_mcap_info:
            if 'error' in dev_mcap_info:
                print(f"Dev Avg MC:       {dev_mcap_info['error']}")
            else:
                cached_str = f" (cached {dev_mcap_info.get('cache_age', 0)}s)" if dev_mcap_info.get('cached') else ""
                valid_tokens_str = f" ({dev_mcap_info.get('valid_tokens', 0)} tokens)" if not dev_mcap_info.get(
                    'cached') else ""
                print(f"Dev Avg MC:       ${dev_mcap_info['avg_mcap']:,.2f}{cached_str}{valid_tokens_str}")
                print(f"Dev Avg ATH MC:   ${dev_mcap_info.get('avg_ath_mcap', 0):,.2f}")

                # Выводим детальный список токенов с ATH (ТОЛЬКО В КОНСОЛЬ)
                if 'tokens_info' in dev_mcap_info and dev_mcap_info['tokens_info']:
                    print("-" * 80)
                    print(f"DEV TOKENS (last {len(dev_mcap_info['tokens_info'])}):")
                    for i, token_info in enumerate(dev_mcap_info['tokens_info'], 1):
                        ath_str = f"${token_info.get('ath_mcap', 0):,.2f}" if token_info.get('ath_mcap',
                                                                                             0) > 0 else "N/A"
                        print(f"  {i}. [{token_info['ticker']}] {token_info['pair_address']}")
                        print(f"     Current MC: ${token_info['mcap']:,.2f} | ATH MC: {ath_str}")
        else:
            print(f"Dev Avg MC:       Loading...")
            print(f"Dev Avg ATH MC:   Loading...")

        if migrated is not None and non_migrated is not None and percentage is not None:
            print(f"Migrated Tokens:  {migrated}")
            print(f"Non-Migrated:     {non_migrated}")
            print(f"Percentage:       {percentage:.2f}%")
        else:
            print("Migrated Tokens:  Waiting...")
            print("Non-Migrated:     Waiting...")
            print("Percentage:       Waiting...")

        if has_twitter and not is_post and twitter_stats and isinstance(twitter_stats, dict) and not twitter_stats.get(
                "error"):
            print("-" * 80)
            print("TWITTER СТАТИСТИКА:")
            if "community_followers" in twitter_stats:
                print(f"   Community Members:    {twitter_stats.get('community_followers', 0):,}")
                if twitter_stats.get('admin_username'):
                    print(f"   Admin:                @{twitter_stats['admin_username']}")
                    print(f"   Admin Followers:      {twitter_stats.get('admin_followers', 0):,}")
                    print(f"   Admin Following:      {twitter_stats.get('admin_following', 0):,}")
            elif "followers" in twitter_stats:
                print(f"   Followers:            {twitter_stats.get('followers', 0):,}")
                print(f"   Following:            {twitter_stats.get('following', 0):,}")

        if cache_time > 0:
            print(f"Cache Lookup:     {cache_time:.6f}s")
        print("-" * 80)
        if has_twitter and not is_post:
            print(f"Twitter Source: {source}")
        print(f"Processing:     {processing_time:.3f}s ({processing_time * 1000:.2f}ms)")
        print("=" * 80 + "\n")

        # === ЭМИТ В GUI (БЕЗ ДЕТАЛЬНОГО СПИСКА ТОКЕНОВ) ===
        try:
            from token_emitter import token_emitter

            # ← ДОБАВЛЯЕМ ВРЕМЯ И AVG ATH
            gui_data = {
                'token_name': data['token_name'],
                'token_ticker': data['token_ticker'],
                'token_address': data['token_address'],
                'deployer_address': data['deployer_address'],
                'twitter': data['twitter'],
                'pair_address': data['pair_address'],
                'twitter_stats': twitter_stats or {},
                'dev_mcap_info': dev_mcap_info or {},
                'migrated': migrated or 0,
                'total': (migrated or 0) + (non_migrated or 0),
                'percentage': round(percentage, 2) if percentage is not None else 0.0,
                'processing_time_ms': int(processing_time * 1000),
                'counter': self.gui_counter + 1,
                # ← НОВЫЕ ПОЛЯ ДЛЯ GUI
                'created_at': data.get('created_at', ''),  # Время создания токена
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Время отправки в GUI
                'avg_ath_mcap': dev_mcap_info.get('avg_ath_mcap',
                                                  0) if dev_mcap_info and 'error' not in dev_mcap_info else 0,
                # AVG ATH
                'avg_tokens_count': self.avg_tokens_count , # Количество токенов для расчета (N)
                'protocol': data.get('protocol', 'unknown')
            }

            gui_data = {k: v for k, v in gui_data.items() if v is not None}
            if 'error' in gui_data.get('dev_mcap_info', {}):
                gui_data['dev_mcap_info'] = {'avg_mcap': 0, 'avg_ath_mcap': 0, 'cached': False}

            self.gui_counter = gui_data['counter']
            token_emitter.new_token.emit(gui_data)
        except ImportError:
            pass

    def _process_pending_tokens(self):
        """Фоновая проверка очереди токенов"""
        while self.running:
            try:
                token_address, data, source, start_time, twitter_stats_future, dev_mcap_future = self.pending_queue.get(
                    timeout=0.05)
                cache_start = time.time()
                update_pulse_data = self.update_pulse_cache.get(token_address) or self.update_pulse_cache.get(
                    data['pair_address'])
                cache_time = time.time() - cache_start
                processing_time = time.time() - start_time

                twitter_stats = None
                if twitter_stats_future:
                    try:
                        twitter_stats = twitter_stats_future.result(timeout=2.0)
                        if twitter_stats:
                            if twitter_stats.get("error") and not twitter_stats.get("is_post"):
                                print(f"Twitter API error: {twitter_stats['error']}")
                        else:
                            twitter_stats = {"error": "API returned None"}
                    except Exception as e:
                        print(f"Twitter stats future error: {e}")
                        twitter_stats = {"error": str(e)}

                dev_mcap_info = None
                if dev_mcap_future:
                    try:
                        dev_mcap_info = dev_mcap_future.result(timeout=10.0)  # ← Увеличили для ATH
                    except:
                        pass

                if update_pulse_data and len(update_pulse_data) > 41:
                    migrated = update_pulse_data[33] if update_pulse_data[33] is not None else 0
                    total = update_pulse_data[41] if update_pulse_data[41] is not None else 0
                    non_migrated = total - migrated if total >= migrated else 0
                    percentage = (migrated / total * 100) if total > 0 else 0
                    self._output_token_info(data, processing_time, source, twitter_stats, migrated, non_migrated,
                                            percentage, cache_time, dev_mcap_info)
                elif processing_time > 0.7:
                    self._output_token_info(data, processing_time, source, twitter_stats, cache_time=cache_time,
                                            dev_mcap_info=dev_mcap_info)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ Error in process_pending_tokens: {e}")

    def _process_new_pairs(self, content, created_at):
        """Обработка new_pairs с dev avg market cap + ATH"""
        start_time = time.time()
        try:
            token_address = content.get('token_address', '')
            pair_address = content.get('pair_address', '')
            protocol = content.get('protocol', 'unknown')
            if not token_address:
                return

            data = {
                'token_address': token_address,
                'pair_address': pair_address,
                'token_name': content.get('token_name', ''),
                'token_ticker': content.get('token_ticker', ''),
                'deployer_address': content.get('deployer_address', ''),
                'twitter': content.get('twitter', ''),
                'token_uri': content.get('token_uri', ''),
                'created_at': created_at,
                '__start_time': start_time,
                'protocol': protocol
            }

            twitter_direct = data['twitter']
            uri_future = None
            twitter_stats = None
            twitter = twitter_direct
            source = 'new_pairs (direct)'

            # Twitter обработка
            if data['token_uri'] and data['token_uri'].strip():
                uri_future = self.executor.submit(self._fetch_twitter_from_uri, data['token_uri'])

            if twitter_direct and twitter_direct.strip() and twitter_direct != 'null' and (
                    'twitter.com' in twitter_direct or 'x.com' in twitter_direct):
                if not TwitterAPI.is_post_url(twitter_direct):
                    twitter_stats = self._run_async_task(self.twitter_api.process_twitter_url(twitter_direct))
                    if twitter_stats:
                        if twitter_stats.get("error") and not twitter_stats.get("is_post"):
                            print(f"Twitter API error: {twitter_stats['error']}")
                    else:
                        twitter_stats = {"error": "API returned None"}
                else:
                    twitter_stats = {"error": "Post URL - skipped", "is_post": True}
            else:
                if uri_future:
                    try:
                        twitter_from_uri = uri_future.result(timeout=1.1)
                        if twitter_from_uri and not TwitterAPI.is_post_url(twitter_from_uri):
                            twitter = twitter_from_uri
                            source = 'token_uri'
                            twitter_stats = self._run_async_task(self.twitter_api.process_twitter_url(twitter_from_uri))
                            if twitter_stats:
                                if twitter_stats.get("error") and not twitter_stats.get("is_post"):
                                    print(f"Twitter API error: {twitter_stats['error']}")
                            else:
                                twitter_stats = {"error": "API returned None"}
                        elif twitter_from_uri and TwitterAPI.is_post_url(twitter_from_uri):
                            twitter = twitter_from_uri
                            source = 'token_uri (post)'
                            twitter_stats = {"error": "Post URL - skipped", "is_post": True}
                    except Exception as e:
                        print(f"Token URI error: {e}")

            data['twitter'] = twitter if twitter and twitter.strip() and twitter != 'null' else ''

            # Запускаем проверку dev avg market cap + ATH асинхронно
            dev_mcap_future = asyncio.run_coroutine_threadsafe(
                self._get_dev_avg_mcap(data['deployer_address']),
                self.event_loop
            )

            # Проверяем кэш миграций
            cache_start = time.time()
            update_pulse_data = self.update_pulse_cache.get(token_address) or self.update_pulse_cache.get(pair_address)
            cache_time = time.time() - cache_start
            processing_time = time.time() - start_time

            if update_pulse_data and len(update_pulse_data) > 41:
                migrated = update_pulse_data[33] if update_pulse_data[33] is not None else 0
                total = update_pulse_data[41] if update_pulse_data[41] is not None else 0
                non_migrated = total - migrated if total >= migrated else 0
                percentage = (migrated / total * 100) if total > 0 else 0

                # Ждем dev mcap + ATH
                try:
                    dev_mcap_info = dev_mcap_future.result(timeout=10.0)  # ← Увеличили для ATH
                except:
                    dev_mcap_info = {"error": "Timeout"}

                self._output_token_info(data, processing_time, source, twitter_stats, migrated, non_migrated,
                                        percentage, cache_time, dev_mcap_info)
            else:
                if processing_time < 0.4:
                    twitter_stats_future = None
                    if twitter_stats:
                        twitter_stats_future = asyncio.run_coroutine_threadsafe(
                            self.twitter_api.process_twitter_url(twitter), self.event_loop)
                    self.executor.submit(lambda: self.pending_queue.put(
                        (token_address, data, source, start_time, twitter_stats_future, dev_mcap_future)))
                else:
                    try:
                        dev_mcap_info = dev_mcap_future.result(timeout=10.0)
                    except:
                        dev_mcap_info = {"error": "Timeout"}
                    self._output_token_info(data, processing_time, source, twitter_stats, cache_time=cache_time,
                                            dev_mcap_info=dev_mcap_info)

        except Exception as e:
            print(f"⚠️ Error in process_new_pairs: {e}")

    def _on_message(self, ws, message):
        """Обработчик сообщений WebSocket"""
        try:
            data = json.loads(message)
            room = data.get("room")
            if room == "new_pairs":
                content = data.get("content")
                if content:
                    created_at = data.get("created_at", "")
                    self.executor.submit(self._process_new_pairs, content, created_at)
            elif room == "update_pulse_v2":
                content = data.get("content", [])
                current_time = time.time()
                for item in content:
                    token_address = item[0] if len(item) > 0 else None
                    pair_address = item[1] if len(item) > 1 else None
                    if token_address and pair_address and len(item) > 30 and item[30]:
                        try:
                            item_time = datetime.fromisoformat(item[30].replace('Z', '+00:00')).timestamp()
                            if current_time - item_time <= 15:
                                self.update_pulse_cache[token_address] = item
                                self.update_pulse_cache[pair_address] = item
                        except:
                            pass
                update_pulse_cache_clean = {k: v for k, v in self.update_pulse_cache.items()
                                            if v[30] and (current_time - datetime.fromisoformat(
                        v[30].replace('Z', '+00:00')).timestamp()) <= 15}
                self.update_pulse_cache.clear()
                self.update_pulse_cache.update(update_pulse_cache_clean)
                while len(self.update_pulse_cache) > 2000:
                    self.update_pulse_cache.pop(next(iter(self.update_pulse_cache)))
        except Exception as e:
            print(f"⚠️ Error in on_message: {e}")

    def _on_error(self, ws, error):
        """Обработчик ошибок WebSocket"""
        if "401" in str(error):
            print("⚠️ 401 - обновляем токен...")
            if self._refresh_access_token():
                print("✅ Переподключение...")
                time.sleep(1)
                self._connect_websocket()
            else:
                print("❌ Ошибка обновления токена")
                self.running = False

    def _on_close(self, ws, close_status_code, close_msg):
        """Обработчик закрытия WebSocket"""
        if self.running:
            print(f"⚠️ WebSocket закрыт: {close_status_code}")
            time.sleep(3)
            self._connect_websocket()

    def _on_open(self, ws):
        """Обработчик открытия WebSocket"""
        print("✅ WebSocket подключён")
        ws.send(json.dumps({"action": "join", "room": "new_pairs"}))
        ws.send(json.dumps({"action": "join", "room": "update_pulse_v2"}))
        print("🚀 Мониторинг запущен\n")

    def _connect_websocket(self):
        """Подключение к WebSocket"""
        if not self._check_token_exp(self.token):
            if not self._refresh_access_token():
                print("❌ Не удалось обновить токен")
                return False

        ws_url = "wss://cluster-global2.axiom.trade/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": self.cookies,
            "Origin": "https://axiom.trade"
        }
        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"⚠️ WebSocket ошибка: {e}")
            if self.running:
                time.sleep(5)
                self._connect_websocket()
        return True

    def start(self):
        """Запуск трекера"""
        if self.running:
            print("⚠️ Трекер уже запущен")
            return

        print("=" * 80)
        print("🚀 AXIOM TRACKER")
        print("=" * 80)
        print("⚡ Мониторинг всех токенов с миграциями")
        print("⚡ Twitter статистика (с фильтрацией постов)")
        print(f"⚡ Dev Avg Market Cap (последние {self.avg_tokens_count} токенов)")
        print(f"⚡ Dev Avg ATH Market Cap (последние {self.avg_tokens_count} токенов)")
        print("⚡ Dev Tokens: Pair Address + Ticker + Current MC + ATH MC")
        print("⚡ 50 параллельных потоков")
        print("⚡ Кэширование (5 мин для dev stats, 10 мин для ATH)")
        print("=" * 80)

        self.running = True

        # Запускаем async loop в отдельном потоке
        print("🔄 Инициализация Twitter API и Dev API...")
        async_thread = Thread(target=self._setup_async_loop, daemon=True)
        async_thread.start()
        time.sleep(2)
        print("✅ APIs готовы к работе\n")

        # Запускаем обработчик очереди
        pending_thread = Thread(target=self._process_pending_tokens, daemon=True)
        pending_thread.start()

        # Подключаемся к WebSocket
        self._connect_websocket()

    def stop(self):
        """Остановка трекера"""
        print("\n🛑 Остановка трекера...")
        self.running = False
        if self.ws:
            self.ws.close()
        if self.event_loop:
            self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.executor.shutdown(wait=False)
        print("✅ Трекер остановлен")


if __name__ == "__main__":
    # Пример использования
    AUTH_FILE = "auth_data.json"
    TWITTER_API_KEY = "new1_d84d121d635d4b2aa0680a22e25c08d2"

    tracker = AxiomTracker(
        auth_file=AUTH_FILE,
        twitter_api_key=TWITTER_API_KEY,
        avg_tokens_count=10  # Количество токенов для расчета avg market cap + ATH
    )

    try:
        tracker.start()
    except KeyboardInterrupt:
        tracker.stop()
