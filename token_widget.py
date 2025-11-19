# token_widget.py
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QFont, QCursor, QColor
from PySide6.QtCore import Qt
import webbrowser
import logging

# Настройка логирования
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class TokenWidget(QFrame):
    """Виджет для отображения одного токена"""

    def __init__(self, token_data, parent=None):
        super().__init__(parent)
        self.token_data = token_data
        self.setup_ui()

    def setup_ui(self):
        """Настройка интерфейса"""
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)

        # ────── Проверки ──────
        has_twitter = bool(
            self.token_data.get('twitter') and
            ('twitter.com' in self.token_data['twitter'] or 'x.com' in self.token_data['twitter'])
        )
        twitter_stats = self.token_data.get('twitter_stats', {})
        has_twitter_stats = has_twitter and twitter_stats and not twitter_stats.get('error')

        # ────── Динамическая высота ──────
        base_height = 220
        if has_twitter:
            base_height += 30
            if has_twitter_stats:
                base_height += 50
                if 'community_followers' in twitter_stats:
                    base_height += 40
        # новые поля (avg_ath + время)
        if (self.token_data.get('avg_ath_mcap', 0) > 0 or
            self.token_data.get('created_at') or
            self.token_data.get('timestamp')):
            base_height += 30
        # ← ДОБАВИЛИ protocol
        if self.token_data.get('protocol') and self.token_data['protocol'] != 'unknown':
            base_height += 25

        self.setFixedHeight(base_height)

        border_color = "#1DA1F2" if has_twitter else "#404040"

        # ────── Общий стиль ──────
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #2b2b2b;
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 10px;
                margin: 3px;
            }}
            QLabel {{
                color: white;
                background: transparent;
                border: none;
            }}
        """)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ────── Левая часть (информация) ──────
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        # ----- Header -----
        header_layout = QHBoxLayout()
        counter_label = QLabel(f"#{self.token_data.get('counter', 0)}")
        counter_label.setStyleSheet("color: #FFA726; font-weight: bold;")
        counter_label.setFont(QFont('Arial', 10))
        header_layout.addWidget(counter_label)

        name_label = QLabel(
            f"<span style='color: white;'> {self.token_data['token_name']}</span> "
            f"<span style='color: white;'>({self.token_data['token_ticker']})</span>"
        )
        name_label.setFont(QFont('Arial', 11, QFont.Bold))
        name_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(name_label)

        header_layout.addStretch()
        info_layout.addLayout(header_layout)

        # ----- Token address -----
        token_addr = self.token_data['token_address']
        token_short = f"{token_addr[:12]}...{token_addr[-8:]}"
        token_label = QLabel(f"📍 Token: {token_short}")
        token_label.setFont(QFont('Courier', 8))
        token_label.setStyleSheet("color: #aaaaaa;")
        token_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(token_label)

        # ----- Deployer -----
        deployer = self.token_data['deployer_address']
        deployer_short = f"{deployer[:12]}...{deployer[-8:]}"
        deployer_label = QLabel(f"👤 Deployer: {deployer_short}")
        deployer_label.setFont(QFont('Courier', 8))
        deployer_label.setStyleSheet("color: #aaaaaa;")
        deployer_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(deployer_label)

        # ----- Protocol (НОВОЕ) -----
        protocol = self.token_data.get('protocol', 'unknown').lower()
        if protocol and protocol != 'unknown':
            # Цвета по протоколу
            protocol_colors = {
                'pumpfun': '#4CAF50',   # зелёный
                'raydium': '#2196F3',   # синий
                'orca': '#9C27B0',      # фиолетовый
                'meteora': '#FF9800',   # оранжевый
                'jupiter': '#673AB7',   # deep purple
            }
            color = protocol_colors.get(protocol, '#FFD700')  # золото по умолчанию
            protocol_display = protocol.title()
            protocol_label = QLabel(f"Protocol: {protocol_display}")
            protocol_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            protocol_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(protocol_label)

        # ----- Processing time -----
        processing_time_ms = self.token_data.get('processing_time_ms', 0)
        if processing_time_ms > 0:
            time_label = QLabel(f"Processing: {processing_time_ms} ms")
            time_label.setFont(QFont('Courier', 7))
            time_label.setStyleSheet(
                "color: #00ff00; background-color: #111111; padding: 2px 6px; border-radius: 3px;")
            info_layout.addWidget(time_label)

        # ----- Twitter -----
        if has_twitter:
            twitter_url = self.token_data['twitter']
            twitter_display = twitter_url if len(twitter_url) <= 45 else twitter_url[:42] + "..."
            twitter_label = QLabel(
                f"<a href='{twitter_url}' style='color: #1DA1F2;'>Twitter: {twitter_display}</a>"
            )
            twitter_label.setFont(QFont('Arial', 8))
            twitter_label.setOpenExternalLinks(True)
            info_layout.addWidget(twitter_label)

            # ----- Twitter stats -----
            if has_twitter_stats:
                separator = QLabel("─" * 50)
                separator.setStyleSheet("color: #444444;")
                separator.setFont(QFont('Arial', 6))
                info_layout.addWidget(separator)

                stats_header = QLabel("TWITTER STATS:")
                stats_header.setStyleSheet("color: #FFD700; font-weight: bold;")
                stats_header.setFont(QFont('Arial', 8))
                info_layout.addWidget(stats_header)

                if 'community_followers' in twitter_stats:
                    community_members = twitter_stats.get('community_followers', 0)
                    community_label = QLabel(f"   Community: {community_members:,} members")
                    community_label.setStyleSheet("color: #90EE90;")
                    community_label.setFont(QFont('Arial', 7))
                    info_layout.addWidget(community_label)

                    admin_username = twitter_stats.get('admin_username', '')
                    if admin_username:
                        admin_label = QLabel(f"   Admin: @{admin_username}")
                        admin_label.setStyleSheet("color: #87CEEB;")
                        admin_label.setFont(QFont('Arial', 7))
                        info_layout.addWidget(admin_label)

                        admin_followers = twitter_stats.get('admin_followers', 0)
                        admin_following = twitter_stats.get('admin_following', 0)
                        admin_stats = QLabel(
                            f"      {admin_followers:,} followers | {admin_following:,} following"
                        )
                        admin_stats.setStyleSheet("color: #B0B0B0;")
                        admin_stats.setFont(QFont('Arial', 7))
                        info_layout.addWidget(admin_stats)

                elif 'followers' in twitter_stats:
                    followers = twitter_stats.get('followers', 0)
                    following = twitter_stats.get('following', 0)
                    followers_label = QLabel(
                        f"   {followers:,} followers | {following:,} following"
                    )
                    followers_label.setStyleSheet("color: #90EE90;")
                    followers_label.setFont(QFont('Arial', 7))
                    info_layout.addWidget(followers_label)
        else:
            no_twitter = QLabel("No Twitter")
            no_twitter.setStyleSheet("color: #666666;")
            no_twitter.setFont(QFont('Arial', 8))
            info_layout.addWidget(no_twitter)

        # ----- Dev Avg MC -----
        mcap_info = self.token_data.get('dev_mcap_info', {})
        if 'avg_mcap' in mcap_info and 'error' not in mcap_info:
            cached_text = " [cached]" if mcap_info.get('cached') else ""
            mcap_label = QLabel(f"Dev Avg MC: ${mcap_info['avg_mcap']:,.0f}{cached_text}")
            mcap_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            mcap_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(mcap_label)
        else:
            mcap_label = QLabel("Dev Avg MC: Loading...")
            mcap_label.setStyleSheet("color: #666666;")
            mcap_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(mcap_label)

        # ----- Avg ATH MCAP + N -----
        avg_ath = self.token_data.get('avg_ath_mcap', 0)
        avg_count = self.token_data.get('avg_tokens_count', 0)
        if avg_ath > 0:
            cached_text = " [cached]" if mcap_info.get('cached') else ""
            ath_label = QLabel(f"Avg ATH: ${avg_ath:,.0f} (N={avg_count}){cached_text}")
            ath_label.setStyleSheet("color: #FF4500; font-weight: bold;")
            ath_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(ath_label)
        else:
            ath_label = QLabel("Avg ATH: Loading...")
            ath_label.setStyleSheet("color: #666666;")
            ath_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(ath_label)

        # ----- Время создания / отправки -----
        created_at = self.token_data.get('created_at', '')
        sent_at = self.token_data.get('timestamp', '')
        if created_at or sent_at:
            parts = []
            if created_at:
                parts.append(f"Created: {created_at}")
            if sent_at:
                parts.append(f"Sent: {sent_at}")
            time_label = QLabel(" | ".join(parts))
            time_label.setStyleSheet("color: #B0C4DE;")
            time_label.setFont(QFont('Arial', 7))
            info_layout.addWidget(time_label)

        # ----- Migrated -----
        migrated = self.token_data.get('migrated')
        total = self.token_data.get('total')
        percentage = self.token_data.get('percentage')

        if migrated is not None and total is not None and percentage is not None:
            migration_label = QLabel(f"Migrated: {migrated}/{total} ({percentage:.1f}%)")
            migration_label.setStyleSheet("color: #FFA726;")
            migration_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(migration_label)
        else:
            migration_label = QLabel("Migrated: Loading...")
            migration_label.setStyleSheet("color: #888888;")
            migration_label.setFont(QFont('Arial', 8))
            info_layout.addWidget(migration_label)

        info_layout.addStretch()
        main_layout.addLayout(info_layout, 4)

        # ────── Правая часть (кнопка) ──────
        button_layout = QVBoxLayout()
        button_layout.addStretch()

        self.open_btn = QPushButton("🚀Open on\nAxiom")
        self.open_btn.setFixedSize(120, 60)
        self.open_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.open_btn.clicked.connect(self.open_axiom)

        self.open_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #222222;
                border: 1px solid rgba(0,0,0,0.2);
                border-radius: 8px;
                padding: 8px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e6e6e6;
            }
            QPushButton:pressed {
                background-color: #6f6f6f;
                color: #ffffff;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.open_btn.setGraphicsEffect(shadow)

        button_layout.addWidget(self.open_btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout, 1)

        self.setLayout(main_layout)

    # ────── Открытие в Axiom ──────
    def open_axiom(self):
        """Открыть токен на Axiom"""
        try:
            pair_address = self.token_data['pair_address']
            url = f"https://axiom.trade/meme/{pair_address}?chain=sol"
            webbrowser.open(url)
            logging.info(f"Opened Axiom URL: {url}")
        except Exception as e:
            logging.error(f"Error opening Axiom URL: {e}")