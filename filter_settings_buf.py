# filter_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QGroupBox, QSpinBox,
    QButtonGroup, QRadioButton, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import json
import os


class FilterSettings:
    """Класс для хранения настроек фильтрации"""

    def __init__(self):
        # Основные
        self.min_avg_mcap = 0
        self.min_avg_ath_mcap = 0
        self.min_migration_percent = 0
        self.min_twitter_followers = 0
        self.min_admin_followers = 0
        self.dev_tokens_count = 10  # N

        # Включение фильтров
        self.enable_avg_mcap = False
        self.enable_avg_ath_mcap = False
        self.enable_migrations = False
        self.enable_twitter_followers = False
        self.enable_admin_followers = False
        self.enable_protocol_filter = False

        # Протоколы (True = показывать)
        self.protocols = {
            'pumpfun': True,
            'raydium': True,
            'orca': True,
            'meteora': True,
            'other': True
        }

        # Режим: AND / OR
        self.use_and_mode = False

    def load_from_file(self, filename="filter_settings.json"):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    self.min_avg_mcap = data.get('min_avg_mcap', 0)
                    self.min_avg_ath_mcap = data.get('min_avg_ath_mcap', 0)
                    self.min_migration_percent = data.get('min_migration_percent', 0)
                    self.min_twitter_followers = data.get('min_twitter_followers', 0)
                    self.min_admin_followers = data.get('min_admin_followers', 0)
                    self.dev_tokens_count = data.get('dev_tokens_count', 10)

                    self.enable_avg_mcap = data.get('enable_avg_mcap', False)
                    self.enable_avg_ath_mcap = data.get('enable_avg_ath_mcap', False)
                    self.enable_migrations = data.get('enable_migrations', False)
                    self.enable_twitter_followers = data.get('enable_twitter_followers', False)
                    self.enable_admin_followers = data.get('enable_admin_followers', False)
                    self.enable_protocol_filter = data.get('enable_protocol_filter', False)

                    self.protocols = data.get('protocols', {k: True for k in self.protocols})
                    self.use_and_mode = data.get('use_and_mode', False)
            except Exception as e:
                print(f"Filter load error: {e}")

    def save_to_file(self, filename="filter_settings.json"):
        data = {
            'min_avg_mcap': self.min_avg_mcap,
            'min_avg_ath_mcap': self.min_avg_ath_mcap,
            'min_migration_percent': self.min_migration_percent,
            'min_twitter_followers': self.min_twitter_followers,
            'min_admin_followers': self.min_admin_followers,
            'dev_tokens_count': self.dev_tokens_count,

            'enable_avg_mcap': self.enable_avg_mcap,
            'enable_avg_ath_mcap': self.enable_avg_ath_mcap,
            'enable_migrations': self.enable_migrations,
            'enable_twitter_followers': self.enable_twitter_followers,
            'enable_admin_followers': self.enable_admin_followers,
            'enable_protocol_filter': self.enable_protocol_filter,

            'protocols': self.protocols,
            'use_and_mode': self.use_and_mode
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def check_token(self, token_data):
        if not any([
            self.enable_avg_mcap, self.enable_avg_ath_mcap,
            self.enable_migrations, self.enable_twitter_followers,
            self.enable_admin_followers, self.enable_protocol_filter
        ]):
            return True

        conditions = []

        # === PROTOCOL FILTER ===
        if self.enable_protocol_filter:
            protocol = token_data.get('protocol', 'unknown').lower()
            allowed = self.protocols.get(protocol, self.protocols['other'])
            conditions.append(allowed)

        # === DEV AVG MCAP ===
        if self.enable_avg_mcap:
            dev_mcap_info = token_data.get('dev_mcap_info', {})
            if 'avg_mcap' in dev_mcap_info and 'error' not in dev_mcap_info:
                conditions.append(dev_mcap_info['avg_mcap'] >= self.min_avg_mcap)
            else:
                conditions.append(False)

        # === DEV AVG ATH MCAP ===
        if self.enable_avg_ath_mcap:
            avg_ath = token_data.get('avg_ath_mcap', 0)
            conditions.append(avg_ath >= self.min_avg_ath_mcap)

        # === MIGRATION % ===
        if self.enable_migrations:
            percentage = token_data.get('percentage')
            if percentage is not None:
                conditions.append(percentage >= self.min_migration_percent)
            else:
                conditions.append(False)

        # === TWITTER FOLLOWERS (USER) ===
        if self.enable_twitter_followers:
            stats = token_data.get('twitter_stats', {})
            if stats and not stats.get('error'):
                conditions.append(stats.get('followers', 0) >= self.min_twitter_followers)
            else:
                conditions.append(False)

        # === ADMIN FOLLOWERS (COMMUNITY) ===
        if self.enable_admin_followers:
            stats = token_data.get('twitter_stats', {})
            if stats and not stats.get('error'):
                conditions.append(stats.get('admin_followers', 0) >= self.min_admin_followers)
            else:
                conditions.append(False)

        if not conditions:
            return True

        return all(conditions) if self.use_and_mode else any(conditions)


class FilterDialog(QDialog):
    settings_changed = Signal(FilterSettings)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.settings = FilterSettings()
        self._copy_settings(current_settings)
        self.setup_ui()

    def _copy_settings(self, src):
        for attr in [
            'min_avg_mcap', 'min_avg_ath_mcap', 'min_migration_percent',
            'min_twitter_followers', 'min_admin_followers', 'dev_tokens_count',
            'enable_avg_mcap', 'enable_avg_ath_mcap', 'enable_migrations',
            'enable_twitter_followers', 'enable_admin_followers',
            'enable_protocol_filter', 'use_and_mode'
        ]:
            if hasattr(src, attr):
                setattr(self.settings, attr, getattr(src, attr))
        self.settings.protocols = getattr(src, 'protocols', {k: True for k in self.settings.protocols})

    def setup_ui(self):
        self.setWindowTitle("Token Filter Settings")
        self.setModal(True)
        self.setMinimumWidth(560)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: white; }
            QGroupBox {
                color: #FFD700; font-weight: bold; border: 2px solid #404040;
                border-radius: 5px; margin-top: 12px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QSpinBox, QLineEdit {
                background-color: #2b2b2b; color: white; border: 1px solid #404040;
                border-radius: 3px; padding: 5px; min-height: 20px;
            }
            QCheckBox { color: white; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QPushButton {
                background-color: #1e88e5; color: white; border: none;
                border-radius: 5px; padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1976d2; }
            QPushButton#resetBtn { background-color: #f44336; }
            QPushButton#resetBtn:hover { background-color: #d32f2f; }
        """)

        scroll = QScrollArea()
        scroll_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(15, 15, 15, 15)

        # === ЗАГОЛОВОК ===
        header = QLabel("TOKEN FILTER SETTINGS")
        header.setFont(QFont('Arial', 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1DA1F2; padding: 10px;")
        layout.addWidget(header)

        # === РЕЖИМ ФИЛЬТРАЦИИ ===
        mode_group = QGroupBox("Filter Logic")
        mode_layout = QVBoxLayout()
        self.and_mode_checkbox = QCheckBox("AND Mode (all conditions must match)")
        self.and_mode_checkbox.setChecked(self.settings.use_and_mode)
        mode_layout.addWidget(self.and_mode_checkbox)
        mode_info = QLabel("Unchecked: OR Mode (any condition)")
        mode_info.setStyleSheet("color: #888; font-size: 9px; padding-left: 25px;")
        mode_layout.addWidget(mode_info)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # === ПРОТОКОЛЫ ===
        proto_group = QGroupBox("Protocols")
        proto_layout = QVBoxLayout()

        proto_check_layout = QHBoxLayout()
        self.proto_checkbox = QCheckBox("Enable protocol filter")
        self.proto_checkbox.setChecked(self.settings.enable_protocol_filter)
        proto_check_layout.addWidget(self.proto_checkbox)
        proto_check_layout.addStretch()
        proto_layout.addLayout(proto_check_layout)

        proto_grid = QHBoxLayout()
        self.proto_checks = {}
        protocols = ['pumpfun', 'raydium', 'orca', 'meteora', 'other']
        for proto in protocols:
            cb = QCheckBox(proto.title())
            cb.setChecked(self.settings.protocols.get(proto, True))
            self.proto_checks[proto] = cb
            proto_grid.addWidget(cb)
        proto_layout.addLayout(proto_grid)
        proto_group.setLayout(proto_layout)
        layout.addWidget(proto_group)

        # === DEV TOKENS COUNT (N) ===
        n_group = QGroupBox("Dev Tokens Count (N)")
        n_layout = QHBoxLayout()
        n_label = QLabel("Analyze last N tokens:")
        n_layout.addWidget(n_label)
        self.n_input = QSpinBox()
        self.n_input.setRange(1, 10)
        self.n_input.setValue(self.settings.dev_tokens_count)
        n_layout.addWidget(self.n_input)
        n_layout.addStretch()
        n_group.setLayout(n_layout)
        layout.addWidget(n_group)

        # === DEV AVG MCAP ===
        mcap_group = QGroupBox("Dev Average Market Cap")
        mcap_layout = QVBoxLayout()
        mcap_check = QHBoxLayout()
        self.mcap_checkbox = QCheckBox("Enable")
        self.mcap_checkbox.setChecked(self.settings.enable_avg_mcap)
        mcap_check.addWidget(self.mcap_checkbox)
        mcap_check.addStretch()
        mcap_layout.addLayout(mcap_check)

        mcap_input = QHBoxLayout()
        mcap_input.addWidget(QLabel("Min Avg MCAP ($):"))
        self.mcap_input = QSpinBox()
        self.mcap_input.setRange(0, 100000000)
        self.mcap_input.setSingleStep(1000)
        self.mcap_input.setValue(self.settings.min_avg_mcap)
        mcap_input.addWidget(self.mcap_input)
        mcap_input.addStretch()
        mcap_layout.addLayout(mcap_input)
        mcap_group.setLayout(mcap_layout)
        layout.addWidget(mcap_group)

        # === DEV AVG ATH MCAP ===
        ath_group = QGroupBox("Dev Average ATH Market Cap")
        ath_layout = QVBoxLayout()
        ath_check = QHBoxLayout()
        self.ath_checkbox = QCheckBox("Enable")
        self.ath_checkbox.setChecked(self.settings.enable_avg_ath_mcap)
        ath_check.addWidget(self.ath_checkbox)
        ath_check.addStretch()
        ath_layout.addLayout(ath_check)

        ath_input = QHBoxLayout()
        ath_input.addWidget(QLabel("Min Avg ATH ($):"))
        self.ath_input = QSpinBox()
        self.ath_input.setRange(0, 100000000)
        self.ath_input.setSingleStep(1000)
        self.ath_input.setValue(self.settings.min_avg_ath_mcap)
        ath_input.addWidget(self.ath_input)
        ath_input.addStretch()
        ath_layout.addLayout(ath_input)
        ath_group.setLayout(ath_layout)
        layout.addWidget(ath_group)

        # === MIGRATION % ===
        mig_group = QGroupBox("Migration %")
        mig_layout = QVBoxLayout()
        mig_check = QHBoxLayout()
        self.mig_checkbox = QCheckBox("Enable")
        self.mig_checkbox.setChecked(self.settings.enable_migrations)
        mig_check.addWidget(self.mig_checkbox)
        mig_check.addStretch()
        mig_layout.addLayout(mig_check)

        mig_input = QHBoxLayout()
        mig_input.addWidget(QLabel("Min Migration %:"))
        self.mig_input = QSpinBox()
        self.mig_input.setRange(0, 100)
        self.mig_input.setSuffix(" %")
        self.mig_input.setValue(self.settings.min_migration_percent)
        mig_input.addWidget(self.mig_input)
        mig_input.addStretch()
        mig_layout.addLayout(mig_input)
        mig_group.setLayout(mig_layout)
        layout.addWidget(mig_group)

        # === TWITTER USER ===
        tw_user_group = QGroupBox("Twitter User Followers")
        tw_user_layout = QVBoxLayout()
        tw_user_check = QHBoxLayout()
        self.tw_user_checkbox = QCheckBox("Enable")
        self.tw_user_checkbox.setChecked(self.settings.enable_twitter_followers)
        tw_user_check.addWidget(self.tw_user_checkbox)
        tw_user_check.addStretch()
        tw_user_layout.addLayout(tw_user_check)

        tw_user_input = QHBoxLayout()
        tw_user_input.addWidget(QLabel("Min Followers:"))
        self.tw_user_input = QSpinBox()
        self.tw_user_input.setRange(0, 10000000)
        self.tw_user_input.setSingleStep(100)
        self.tw_user_input.setValue(self.settings.min_twitter_followers)
        tw_user_input.addWidget(self.tw_user_input)
        tw_user_input.addStretch()
        tw_user_layout.addLayout(tw_user_input)
        tw_user_group.setLayout(tw_user_layout)
        layout.addWidget(tw_user_group)

        # === TWITTER ADMIN ===
        tw_admin_group = QGroupBox("Twitter Community Admin")
        tw_admin_layout = QVBoxLayout()
        tw_admin_check = QHBoxLayout()
        self.tw_admin_checkbox = QCheckBox("Enable")
        self.tw_admin_checkbox.setChecked(self.settings.enable_admin_followers)
        tw_admin_check.addWidget(self.tw_admin_checkbox)
        tw_admin_check.addStretch()
        tw_admin_layout.addLayout(tw_admin_check)

        tw_admin_input = QHBoxLayout()
        tw_admin_input.addWidget(QLabel("Min Admin Followers:"))
        self.tw_admin_input = QSpinBox()
        self.tw_admin_input.setRange(0, 10000000)
        self.tw_admin_input.setSingleStep(100)
        self.tw_admin_input.setValue(self.settings.min_admin_followers)
        tw_admin_input.addWidget(self.tw_admin_input)
        tw_admin_input.addStretch()
        tw_admin_layout.addLayout(tw_admin_input)
        tw_admin_group.setLayout(tw_admin_layout)
        layout.addWidget(tw_admin_group)

        # === КНОПКИ ===
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset All")
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(self.reset_settings)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        # === INFO ===
        info = QLabel(
            "• If no filters enabled → all tokens shown\n"
            "• OR mode: any condition → show\n"
            "• AND mode: all conditions → show"
        )
        info.setStyleSheet("color: #888; font-size: 9px; padding: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        scroll_widget.setLayout(layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def reset_settings(self):
        self.mcap_input.setValue(0)
        self.ath_input.setValue(0)
        self.mig_input.setValue(0)
        self.tw_user_input.setValue(0)
        self.tw_admin_input.setValue(0)
        self.n_input.setValue(10)

        self.mcap_checkbox.setChecked(False)
        self.ath_checkbox.setChecked(False)
        self.mig_checkbox.setChecked(False)
        self.tw_user_checkbox.setChecked(False)
        self.tw_admin_checkbox.setChecked(False)
        self.proto_checkbox.setChecked(False)

        for cb in self.proto_checks.values():
            cb.setChecked(True)

        self.and_mode_checkbox.setChecked(False)

    def apply_settings(self):
        self.settings.min_avg_mcap = self.mcap_input.value()
        self.settings.min_avg_ath_mcap = self.ath_input.value()
        self.settings.min_migration_percent = self.mig_input.value()
        self.settings.min_twitter_followers = self.tw_user_input.value()
        self.settings.min_admin_followers = self.tw_admin_input.value()
        self.settings.dev_tokens_count = self.n_input.value()

        self.settings.enable_avg_mcap = self.mcap_checkbox.isChecked()
        self.settings.enable_avg_ath_mcap = self.ath_checkbox.isChecked()
        self.settings.enable_migrations = self.mig_checkbox.isChecked()
        self.settings.enable_twitter_followers = self.tw_user_checkbox.isChecked()
        self.settings.enable_admin_followers = self.tw_admin_checkbox.isChecked()
        self.settings.enable_protocol_filter = self.proto_checkbox.isChecked()

        for proto, cb in self.proto_checks.items():
            self.settings.protocols[proto] = cb.isChecked()

        self.settings.use_and_mode = self.and_mode_checkbox.isChecked()

        self.settings.save_to_file()
        self.settings_changed.emit(self.settings)
        self.accept()