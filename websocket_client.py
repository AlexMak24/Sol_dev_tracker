# websocket_client.py
import time
import random
from threading import Thread
from token_emitter import token_emitter


class FakeWebSocket:
    """Фейковый WebSocket для тестирования фильтрации — генерирует тестовые токены каждые 2 секунды"""

    def __init__(self):
        self.running = False
        self.counter = 0

    def start(self):
        self.running = True
        Thread(target=self._generate_fake_tokens, daemon=True).start()
        print("Fake WebSocket запущен — генерируем тестовые токены")

    def stop(self):
        self.running = False
        print("Fake WebSocket остановлен")

    def _generate_fake_tokens(self):
        fake_tokens = [
            {
                'counter': 0,  # Будет перезаписан
                'token_name': 'MMTFinance',
                'token_ticker': 'MMT',
                'token_address': '8Zww28z3jox4g4KAC5oW2E7e7FP7mZatLGngFisXpump',
                'deployer_address': 'BuFx2AWWih9ATbNdRu5bBDkESWq6AXsVrH8Di74Y9Vzh',
                'twitter': 'https://x.com/MMTFinance',
                'pair_address': '3wbHAP3gZESL4us8xymzLc539VouTUxCuWVBVaik89r5',
                'twitter_stats': {
                    'followers': 353124,
                    'following': 330
                },
                'dev_mcap_info': {
                    'avg_mcap': 368626.38,
                    'cached': True
                },
                'migrated': 1,
                'total': 1,
                'percentage': 100.0,
                'processing_time_ms': random.randint(500, 1000)
            },
            {
                'counter': 0,
                'token_name': 'in a world full of privacy',
                'token_ticker': 'bob',
                'token_address': '8Zww28z3jox4g4KAC5oW2E7e7FP7mZatLGngFisXpump',
                'deployer_address': '2aKq19s7GJsqZFPudSwktPXLKqACSQjT9crQnSf8e6x1',
                'twitter': 'https://x.com/i/communities/1985699372466610294',
                'pair_address': 'Ha2ayYBXGdcp1Wh1jUK57ERUwM6KFAF56LeFKaJhyMxT',
                'twitter_stats': {
                    'community_followers': 1,
                    'admin_username': 'MeyerDoria54152',
                    'admin_followers': 84,
                    'admin_following': 53
                },
                'dev_mcap_info': {
                    'avg_mcap': 4514.17,
                    'cached': False
                },
                'migrated': 1,
                'total': 137,
                'percentage': 0.73,
                'processing_time_ms': random.randint(500, 1000)
            },
            # Добавляем больше фейковых для теста фильтрации
            {
                'counter': 0,
                'token_name': 'TestToken1',
                'token_ticker': 'TT1',
                'token_address': 'FakeAddr1',
                'deployer_address': 'FakeDeployer1',
                'twitter': 'https://x.com/Test1',
                'pair_address': 'FakePair1',
                'twitter_stats': {
                    'followers': 1000,
                    'following': 200
                },
                'dev_mcap_info': {
                    'avg_mcap': 10000,
                    'cached': False
                },
                'migrated': 5,
                'total': 10,
                'percentage': 50.0,
                'processing_time_ms': random.randint(500, 1000)
            },
            {
                'counter': 0,
                'token_name': 'TestToken2',
                'token_ticker': 'TT2',
                'token_address': 'FakeAddr2',
                'deployer_address': 'FakeDeployer2',
                'twitter': 'https://x.com/i/communities/12345',
                'pair_address': 'FakePair2',
                'twitter_stats': {
                    'community_followers': 500,
                    'admin_username': 'AdminTest',
                    'admin_followers': 2000,
                    'admin_following': 100
                },
                'dev_mcap_info': {
                    'avg_mcap': 500000,
                    'cached': True
                },
                'migrated': 0,
                'total': 5,
                'percentage': 0.0,
                'processing_time_ms': random.randint(500, 1000)
            },
            {
                'counter': 0,
                'token_name': 'TestToken3',
                'token_ticker': 'TT3',
                'token_address': 'FakeAddr3',
                'deployer_address': 'FakeDeployer3',
                'twitter': '',
                'pair_address': 'FakePair3',
                'twitter_stats': {},
                'dev_mcap_info': {
                    'avg_mcap': 1000,
                    'cached': False
                },
                'migrated': 10,
                'total': 20,
                'percentage': 50.0,
                'processing_time_ms': random.randint(500, 1000)
            }
        ]

        while self.running:
            # Выбираем случайный фейковый токен
            token_data = random.choice(fake_tokens).copy()
            self.counter += 1
            token_data['counter'] = self.counter

            # Эмитим в GUI
            token_emitter.new_token.emit(token_data)
            print(f"Fake Token #{self.counter} emitted: {token_data['token_name']}")

            time.sleep(2)  # Каждые 2 секунды для теста