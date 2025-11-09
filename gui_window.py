# gui_window.py
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QScrollArea, QHBoxLayout,
    QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, Slot, QPropertyAnimation
from PySide6.QtGui import QFont, QIcon
from token_widget import TokenWidget
from token_emitter import token_emitter
from filter_settings import FilterSettings, FilterDialog
import logging
from datetime import datetime

# Логирование
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self):
        super().__init__()
        self.token_widgets = []
        self.max_tokens = 20
        self.token_counter = 0
        self.filter_text = ""
        self.filter_settings = FilterSettings()
        self.filter_settings.load_from_file()
        self.setup_ui()

        # Подключаем сигнал

        token_emitter.new_token.connect(self.add_token)
        # Логируем запуск
        logging.info(f"Application started at {datetime.now()}")

    def setup_ui(self):
        self.setWindowTitle("AXIOM TOKEN STREAM - TEST MODE")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("background-color: #1a1a1a;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === HEADER ===
        header = QLabel("🚀 AXIOM TOKEN STREAM - LIVE MONITORING")
        header.setFont(QFont('Arial', 18, QFont.Bold))
        header.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1e88e5, stop:1 #1565c0);
            color: white; padding: 20px; border-bottom: 4px solid #0d47a1;
        """)
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # === TOOLBAR ===
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #252525; padding: 8px;")
        toolbar_layout = QHBoxLayout(toolbar)

        # Кнопка настроек
        settings_btn = QPushButton("Options ⚙")
        settings_btn.setIcon(QIcon.fromTheme("preferences-system"))
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #333; color: white; border: 1px solid #555;
                padding: 6px 12px; border-radius: 5px; font-weight: bold;
            }
            QPushButton:hover { background-color: #444; }
        """)
        settings_btn.clicked.connect(self.open_settings)
        toolbar_layout.addWidget(settings_btn)

        # Поиск
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Поиск: тикер, название, адрес, deployer, twitter...")
        self.filter_input.setStyleSheet("""
            QLineEdit {
                background-color: #2b2b2b; color: white;
                border: 1px solid #404040; border-radius: 5px;
                padding: 6px; min-width: 400px;
            }
        """)
        self.filter_input.textChanged.connect(self.filter_tokens)
        toolbar_layout.addWidget(self.filter_input)

        # Счетчик
        self.counter_label = QLabel("Tokens: 0")
        self.counter_label.setStyleSheet("color: #FFA726; font-weight: bold;")
        self.counter_label.setFont(QFont('Arial', 10))
        toolbar_layout.addWidget(self.counter_label)

        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar)

        # === SCROLL AREA ===
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #1a1a1a; }
            QScrollBar:vertical {
                background: #2b2b2b; width: 16px; border-radius: 8px; margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #404040; border-radius: 8px; min-height: 40px;
            }
            QScrollBar::handle:vertical:hover { background: #505050; }
        """)

        self.tokens_container = QWidget()
        self.tokens_layout = QVBoxLayout(self.tokens_container)
        self.tokens_layout.setSpacing(2)
        self.tokens_layout.setContentsMargins(8, 8, 8, 8)
        self.tokens_layout.addStretch()

        self.scroll_area.setWidget(self.tokens_container)
        main_layout.addWidget(self.scroll_area)

        # === FOOTER ===
        self.footer = QLabel(f"Receiving tokens every 1 second | Showing last {self.max_tokens} tokens")
        self.footer.setStyleSheet("background-color: #252525; color: #888; padding: 8px;")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setFont(QFont('Arial', 9))
        main_layout.addWidget(self.footer)

    def open_settings(self):
        """Открыть окно настроек"""
        dialog = FilterDialog(self.filter_settings, self)
        dialog.settings_changed.connect(self.update_settings)
        dialog.exec()

    def update_settings(self, new_settings):
        self.filter_settings = new_settings
        self.refilter_tokens()

    @Slot(dict)
    def add_token(self, token_data):
        if not self.filter_settings.check_token(token_data):
            return  # Не добавляем, если не проходит фильтр

        self.token_counter += 1
        self.counter_label.setText(f"Tokens: {self.token_counter}")
        self.footer.setText(f"Last update: {datetime.now().strftime('%H:%M:%S')} | Showing last {self.max_tokens} tokens")

        logging.info(f"GUI received token #{self.token_counter}: {token_data['token_name']}")

        # Создаём виджет
        token_widget = TokenWidget(token_data)
        token_widget.setStyleSheet("opacity: 0")

        self.tokens_layout.insertWidget(0, token_widget)
        self.token_widgets.insert(0, token_widget)

        # Анимация
        anim = QPropertyAnimation(token_widget, b"windowOpacity")
        anim.setDuration(500)
        anim.setStartValue(0)
        anim.setEndValue(1)
        anim.start()

        # Удаляем старые
        if len(self.token_widgets) > self.max_tokens:
            old = self.token_widgets.pop()
            self.tokens_layout.removeWidget(old)
            old.deleteLater()

        # Прокрутка вверх
        if self.scroll_area.verticalScrollBar().value() < 50:
            anim_scroll = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value")
            anim_scroll.setDuration(300)
            anim_scroll.setStartValue(self.scroll_area.verticalScrollBar().value())
            anim_scroll.setEndValue(0)
            anim_scroll.start()

        # Применяем текстовый фильтр
        self.filter_tokens(self.filter_text)

    def filter_tokens(self, text):
        """Универсальный поиск по всем полям"""
        self.filter_text = text.lower().strip()
        query = self.filter_text

        for widget in self.token_widgets:
            data = widget.token_data
            visible = True

            if query:
                search_fields = [
                    data.get('token_ticker', ''),
                    data.get('token_name', ''),
                    data.get('token_address', ''),
                    data.get('deployer_address', ''),
                    data.get('twitter', ''),
                    str(data.get('counter', '')),
                ]

                # Dev MCAP
                mcap = data.get('dev_mcap_info', {})
                if isinstance(mcap, dict) and 'avg_mcap' in mcap:
                    search_fields.append(f"${mcap['avg_mcap']:,.0f}")

                # Миграции
                if 'percentage' in data:
                    search_fields.append(f"{data['percentage']:.0f}%")

                # Поиск
                visible = any(query in str(field).lower() for field in search_fields)

            widget.setVisible(visible)

    def refilter_tokens(self):
        """Перефильтровать существующие токены после изменения настроек"""
        to_remove = []
        for widget in self.token_widgets:
            if not self.filter_settings.check_token(widget.token_data):
                to_remove.append(widget)

        for widget in to_remove:
            self.token_widgets.remove(widget)
            self.tokens_layout.removeWidget(widget)
            widget.deleteLater()

        self.token_counter = len(self.token_widgets)
        self.counter_label.setText(f"Tokens: {self.token_counter}")

        # Применяем текстовый фильтр заново
        self.filter_tokens(self.filter_text)

    def closeEvent(self, event):
        logging.info(f"Application closed at {datetime.now()}")
        event.accept()