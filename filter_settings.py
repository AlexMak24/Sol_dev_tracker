# filter_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import json
import os


class FilterSettings:
    """Класс для хранения настроек фильтрации"""

    def __init__(self):
        self.min_avg_mcap = 0
        self.min_migration_percent = 0  # ← НОВОЕ: % миграций
        self.min_twitter_followers = 0
        self.min_admin_followers = 0

        # Чекбоксы для режима фильтрации
        self.enable_avg_mcap = False
        self.enable_migrations = False   # ← теперь это %!
        self.enable_twitter_followers = False
        self.enable_admin_followers = False

        # Режим: True = AND (все условия), False = OR (хотя бы одно)
        self.use_and_mode = False

    def load_from_file(self, filename="filter_settings.json"):
        """Загрузка настроек из файла"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    self.min_avg_mcap = data.get('min_avg_mcap', 0)
                    self.min_migration_percent = data.get('min_migration_percent', 0)  # ← НОВОЕ
                    self.min_twitter_followers = data.get('min_twitter_followers', 0)
                    self.min_admin_followers = data.get('min_admin_followers', 0)

                    self.enable_avg_mcap = data.get('enable_avg_mcap', False)
                    self.enable_migrations = data.get('enable_migrations', False)
                    self.enable_twitter_followers = data.get('enable_twitter_followers', False)
                    self.enable_admin_followers = data.get('enable_admin_followers', False)

                    self.use_and_mode = data.get('use_and_mode', False)
            except:
                pass

    def save_to_file(self, filename="filter_settings.json"):
        """Сохранение настроек в файл"""
        data = {
            'min_avg_mcap': self.min_avg_mcap,
            'min_migration_percent': self.min_migration_percent,  # ← НОВОЕ
            'min_twitter_followers': self.min_twitter_followers,
            'min_admin_followers': self.min_admin_followers,

            'enable_avg_mcap': self.enable_avg_mcap,
            'enable_migrations': self.enable_migrations,
            'enable_twitter_followers': self.enable_twitter_followers,
            'enable_admin_followers': self.enable_admin_followers,

            'use_and_mode': self.use_and_mode
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def check_token(self, token_data):
        """
        Проверка токена на соответствие фильтрам
        Returns: True если токен проходит фильтр, False если нет
        """
        # Если ни один фильтр не включен - пропускаем все токены
        if not any([self.enable_avg_mcap, self.enable_migrations,
                    self.enable_twitter_followers, self.enable_admin_followers]):
            return True

        conditions = []

        # Проверка Dev Avg Market Cap
        if self.enable_avg_mcap:
            dev_mcap_info = token_data.get('dev_mcap_info', {})
            if 'avg_mcap' in dev_mcap_info and 'error' not in dev_mcap_info:
                avg_mcap = dev_mcap_info['avg_mcap']
                conditions.append(avg_mcap >= self.min_avg_mcap)
            else:
                conditions.append(False)

        # Проверка Migration % (замена на процент)
        if self.enable_migrations:
            percentage = token_data.get('percentage')
            if percentage is not None:
                conditions.append(percentage >= self.min_migration_percent)
            else:
                conditions.append(False)

        # Проверка Twitter Followers
        if self.enable_twitter_followers:
            twitter_stats = token_data.get('twitter_stats')
            if twitter_stats and not twitter_stats.get('error'):
                followers = twitter_stats.get('followers', 0)
                conditions.append(followers >= self.min_twitter_followers)
            else:
                conditions.append(False)

        # Проверка Admin Followers (для сообществ)
        if self.enable_admin_followers:
            twitter_stats = token_data.get('twitter_stats')
            if twitter_stats and not twitter_stats.get('error'):
                admin_followers = twitter_stats.get('admin_followers', 0)
                conditions.append(admin_followers >= self.min_admin_followers)
            else:
                conditions.append(False)

        # Если нет активных условий - пропускаем токен
        if not conditions:
            return True

        # Режим фильтрации
        if self.use_and_mode:
            return all(conditions)
        else:
            return any(conditions)


class FilterDialog(QDialog):
    """Диалоговое окно настроек фильтрации"""
    settings_changed = Signal(FilterSettings)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.settings = FilterSettings()

        # Копируем текущие настройки
        self.settings.min_avg_mcap = current_settings.min_avg_mcap
        self.settings.min_migration_percent = getattr(current_settings, 'min_migration_percent', 0)
        self.settings.min_twitter_followers = current_settings.min_twitter_followers
        self.settings.min_admin_followers = current_settings.min_admin_followers

        self.settings.enable_avg_mcap = current_settings.enable_avg_mcap
        self.settings.enable_migrations = current_settings.enable_migrations
        self.settings.enable_twitter_followers = current_settings.enable_twitter_followers
        self.settings.enable_admin_followers = current_settings.enable_admin_followers

        self.settings.use_and_mode = current_settings.use_and_mode

        self.setup_ui()

    def setup_ui(self):
        """Настройка интерфейса"""
        self.setWindowTitle("Filter Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: white; }
            QGroupBox {
                color: #FFD700; font-weight: bold; border: 2px solid #404040;
                border-radius: 5px; margin-top: 10px; padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QSpinBox, QLineEdit {
                background-color: #2b2b2b; color: white; border: 1px solid #404040;
                border-radius: 3px; padding: 5px;
            }
            QCheckBox { color: white; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QPushButton {
                background-color: #1e88e5; color: white; border: none;
                border-radius: 5px; padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1976d2; }
            QPushButton#resetBtn { background-color: #f44336; }
            QPushButton#resetBtn:hover { background-color: #d32f2f; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # === ЗАГОЛОВОК ===
        header = QLabel("TOKEN FILTER SETTINGS")
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1DA1F2; padding: 10px;")
        layout.addWidget(header)

        # === РЕЖИМ ФИЛЬТРАЦИИ ===
        mode_group = QGroupBox("Filter Mode")
        mode_layout = QVBoxLayout()

        self.and_mode_checkbox = QCheckBox("Use AND mode (all conditions must be met)")
        self.and_mode_checkbox.setChecked(self.settings.use_and_mode)
        self.and_mode_checkbox.setFont(QFont('Arial', 10))
        mode_layout.addWidget(self.and_mode_checkbox)

        mode_info = QLabel("If unchecked: OR mode (at least one condition must be met)")
        mode_info.setStyleSheet("color: #888888; font-size: 9px; padding-left: 25px;")
        mode_layout.addWidget(mode_info)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # === DEV AVG MARKET CAP ===
        mcap_group = QGroupBox("Dev Average Market Cap")
        mcap_layout = QVBoxLayout()

        mcap_check_layout = QHBoxLayout()
        self.mcap_checkbox = QCheckBox("Enable filter")
        self.mcap_checkbox.setChecked(self.settings.enable_avg_mcap)
        mcap_check_layout.addWidget(self.mcap_checkbox)
        mcap_check_layout.addStretch()
        mcap_layout.addLayout(mcap_check_layout)

        mcap_input_layout = QHBoxLayout()
        mcap_label = QLabel("Minimum Avg Market Cap ($):")
        mcap_input_layout.addWidget(mcap_label)

        self.mcap_input = QSpinBox()
        self.mcap_input.setRange(0, 100000000)
        self.mcap_input.setSingleStep(1000)
        self.mcap_input.setValue(self.settings.min_avg_mcap)
        self.mcap_input.setMinimumWidth(150)
        mcap_input_layout.addWidget(self.mcap_input)
        mcap_input_layout.addStretch()

        mcap_layout.addLayout(mcap_input_layout)
        mcap_group.setLayout(mcap_layout)
        layout.addWidget(mcap_group)

        # === MIGRATION % (ЗАМЕНА) ===
        migration_group = QGroupBox("Token Migration %")
        migration_layout = QVBoxLayout()

        migration_check_layout = QHBoxLayout()
        self.migration_checkbox = QCheckBox("Enable filter")
        self.migration_checkbox.setChecked(self.settings.enable_migrations)
        migration_check_layout.addWidget(self.migration_checkbox)
        migration_check_layout.addStretch()
        migration_layout.addLayout(migration_check_layout)

        migration_input_layout = QHBoxLayout()
        migration_label = QLabel("Minimum Migration %:")
        migration_input_layout.addWidget(migration_label)

        self.migration_input = QSpinBox()
        self.migration_input.setRange(0, 100)  # ← 0–100%
        self.migration_input.setSuffix(" %")  # ← суффикс
        self.migration_input.setValue(self.settings.min_migration_percent)
        self.migration_input.setMinimumWidth(150)
        migration_input_layout.addWidget(self.migration_input)
        migration_input_layout.addStretch()

        migration_layout.addLayout(migration_input_layout)
        migration_group.setLayout(migration_layout)
        layout.addWidget(migration_group)

        # === TWITTER FOLLOWERS ===
        twitter_group = QGroupBox("Twitter Followers (User)")
        twitter_layout = QVBoxLayout()

        twitter_check_layout = QHBoxLayout()
        self.twitter_checkbox = QCheckBox("Enable filter")
        self.twitter_checkbox.setChecked(self.settings.enable_twitter_followers)
        twitter_check_layout.addWidget(self.twitter_checkbox)
        twitter_check_layout.addStretch()
        twitter_layout.addLayout(twitter_check_layout)

        twitter_input_layout = QHBoxLayout()
        twitter_label = QLabel("Minimum Followers:")
        twitter_input_layout.addWidget(twitter_label)

        self.twitter_input = QSpinBox()
        self.twitter_input.setRange(0, 10000000)
        self.twitter_input.setSingleStep(100)
        self.twitter_input.setValue(self.settings.min_twitter_followers)
        self.twitter_input.setMinimumWidth(150)
        twitter_input_layout.addWidget(self.twitter_input)
        twitter_input_layout.addStretch()

        twitter_layout.addLayout(twitter_input_layout)
        twitter_group.setLayout(twitter_layout)
        layout.addWidget(twitter_group)

        # === ADMIN FOLLOWERS ===
        admin_group = QGroupBox("Admin Followers (Community)")
        admin_layout = QVBoxLayout()

        admin_check_layout = QHBoxLayout()
        self.admin_checkbox = QCheckBox("Enable filter")
        self.admin_checkbox.setChecked(self.settings.enable_admin_followers)
        admin_check_layout.addWidget(self.admin_checkbox)
        admin_check_layout.addStretch()
        admin_layout.addLayout(admin_check_layout)

        admin_input_layout = QHBoxLayout()
        admin_label = QLabel("Minimum Admin Followers:")
        admin_input_layout.addWidget(admin_label)

        self.admin_input = QSpinBox()
        self.admin_input.setRange(0, 10000000)
        self.admin_input.setSingleStep(100)
        self.admin_input.setValue(self.settings.min_admin_followers)
        self.admin_input.setMinimumWidth(150)
        admin_input_layout.addWidget(self.admin_input)
        admin_input_layout.addStretch()

        admin_layout.addLayout(admin_input_layout)
        admin_group.setLayout(admin_layout)
        layout.addWidget(admin_group)

        # === КНОПКИ ===
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset All")
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply Filters")
        apply_btn.clicked.connect(self.apply_settings)
        button_layout.addWidget(apply_btn)

        layout.addLayout(button_layout)

        # === INFO ===
        info_label = QLabel(
            "If no filters are enabled, all tokens will be shown.\n"
            "In OR mode: tokens matching ANY condition will be shown.\n"
            "In AND mode: tokens must match ALL enabled conditions."
        )
        info_label.setStyleSheet("color: #888888; font-size: 9px; padding: 10px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.setLayout(layout)

    def reset_settings(self):
        """Сброс всех настроек"""
        self.mcap_input.setValue(0)
        self.migration_input.setValue(0)  # ← теперь %
        self.twitter_input.setValue(0)
        self.admin_input.setValue(0)

        self.mcap_checkbox.setChecked(False)
        self.migration_checkbox.setChecked(False)
        self.twitter_checkbox.setChecked(False)
        self.admin_checkbox.setChecked(False)

        self.and_mode_checkbox.setChecked(False)

    def apply_settings(self):
        """Применение настроек"""
        self.settings.min_avg_mcap = self.mcap_input.value()
        self.settings.min_migration_percent = self.migration_input.value()  # ← НОВОЕ
        self.settings.min_twitter_followers = self.twitter_input.value()
        self.settings.min_admin_followers = self.admin_input.value()

        self.settings.enable_avg_mcap = self.mcap_checkbox.isChecked()
        self.settings.enable_migrations = self.migration_checkbox.isChecked()
        self.settings.enable_twitter_followers = self.twitter_checkbox.isChecked()
        self.settings.enable_admin_followers = self.admin_checkbox.isChecked()

        self.settings.use_and_mode = self.and_mode_checkbox.isChecked()

        # Сохраняем в файл
        self.settings.save_to_file()

        # Отправляем сигнал
        self.settings_changed.emit(self.settings)

        self.accept()