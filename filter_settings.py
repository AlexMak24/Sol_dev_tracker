# filter_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QGroupBox, QSpinBox, QScrollArea, QWidget, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import json
import os


# === МАППИНГ: UI название → ключ в token_data['protocol'] ===
PROTOCOL_MAPPING = {
    'Pump V1': 'pump v1',
    'Meteora AMM V2': 'meteora amm v2',
    'Orca': 'orca',
    'Virtual Curve': 'virtual curve',
    'Raydium CPMM': 'raydium cpmm',
    'LaunchLab': 'launchlab',
    'Meteora DLMM': 'meteora dlmm',
    'Sugar': 'sugar',
    'Pump AMM': 'pump amm',
    'Raydium CLMM': 'raydium clmm',
    'Moonshot': 'moonshot',
    'Other': 'other'
}


class FilterSettings:
    def __init__(self):
        # Значения
        self.min_avg_mcap = 0
        self.min_avg_ath_mcap = 0
        self.min_migration_percent = 0
        self.min_twitter_followers = 0
        self.min_community_members = 0
        self.min_admin_followers = 0
        self.dev_tokens_count = 10

        # Включение
        self.enable_avg_mcap = False
        self.enable_avg_ath_mcap = False
        self.enable_migrations = False
        self.enable_twitter_user = False
        self.enable_twitter_community = False
        self.enable_protocol_filter = False

        # Внутренние ключи — как в Axiom (нижний регистр)
        self.protocols = {v: True for v in PROTOCOL_MAPPING.values()}

        self.use_and_mode = False

    def load_from_file(self, filename="filter_settings.json"):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    for key in [
                        'min_avg_mcap', 'min_avg_ath_mcap', 'min_migration_percent',
                        'min_twitter_followers', 'min_community_members', 'min_admin_followers',
                        'dev_tokens_count'
                    ]:
                        setattr(self, key, data.get(key, getattr(self, key, 0)))

                    for key in [
                        'enable_avg_mcap', 'enable_avg_ath_mcap', 'enable_migrations',
                        'enable_twitter_user', 'enable_twitter_community',
                        'enable_protocol_filter', 'use_and_mode'
                    ]:
                        setattr(self, key, data.get(key, getattr(self, key, False)))

                    loaded = data.get('protocols', {})
                    for internal in self.protocols:
                        self.protocols[internal] = loaded.get(internal, True)
            except Exception as e:
                print(f"[Filter] Load error: {e}")

    def save_to_file(self, filename="filter_settings.json"):
        data = {
            'min_avg_mcap': self.min_avg_mcap,
            'min_avg_ath_mcap': self.min_avg_ath_mcap,
            'min_migration_percent': self.min_migration_percent,
            'min_twitter_followers': self.min_twitter_followers,
            'min_community_members': self.min_community_members,
            'min_admin_followers': self.min_admin_followers,
            'dev_tokens_count': self.dev_tokens_count,

            'enable_avg_mcap': self.enable_avg_mcap,
            'enable_avg_ath_mcap': self.enable_avg_ath_mcap,
            'enable_migrations': self.enable_migrations,
            'enable_twitter_user': self.enable_twitter_user,
            'enable_twitter_community': self.enable_twitter_community,
            'enable_protocol_filter': self.enable_protocol_filter,

            'protocols': self.protocols,
            'use_and_mode': self.use_and_mode
        }
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Filter] Save error: {e}")

    def check_token(self, token_data):
        active = [
            self.enable_avg_mcap, self.enable_avg_ath_mcap,
            self.enable_migrations, self.enable_twitter_user,
            self.enable_twitter_community, self.enable_protocol_filter
        ]
        if not any(active):
            return True

        conditions = []

        # === ПРОТОКОЛЫ ===
        if self.enable_protocol_filter:
            raw_proto = token_data.get('protocol', 'unknown')
            if not isinstance(raw_proto, str):
                raw_proto = 'unknown'
            proto = raw_proto.strip().lower()

            matched = False
            for ui_name, internal in PROTOCOL_MAPPING.items():
                if internal in proto or ui_name.lower() in proto:
                    allowed = self.protocols.get(internal, True)
                    conditions.append(allowed)
                    matched = True
                    break
            if not matched:
                conditions.append(self.protocols['other'])

        # === DEV AVG MCAP ===
        if self.enable_avg_mcap:
            info = token_data.get('dev_mcap_info', {})
            conditions.append(
                'avg_mcap' in info and 'error' not in info and info['avg_mcap'] >= self.min_avg_mcap
            )

        # === DEV AVG ATH MCAP ===
        if self.enable_avg_ath_mcap:
            conditions.append(token_data.get('avg_ath_mcap', 0) >= self.min_avg_ath_mcap)

        # === MIGRATION % ===
        if self.enable_migrations:
            pct = token_data.get('percentage')
            conditions.append(pct is not None and pct >= self.min_migration_percent)

        # === TWITTER: USER OR COMMUNITY ===
        twitter_conds = []
        stats = token_data.get('twitter_stats', {})

        if self.enable_twitter_user and stats and not stats.get('error'):
            twitter_conds.append(stats.get('followers', 0) >= self.min_twitter_followers)

        if self.enable_twitter_community and stats and not stats.get('error'):
            members_ok = stats.get('community_followers', 0) >= self.min_community_members
            admin_ok = stats.get('admin_followers', 0) >= self.min_admin_followers
            twitter_conds.append(members_ok and admin_ok)

        if self.enable_twitter_user or self.enable_twitter_community:
            conditions.append(any(twitter_conds) if twitter_conds else False)

        return all(conditions) if self.use_and_mode else any(conditions)


class FilterDialog(QDialog):
    settings_changed = Signal(FilterSettings)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.settings = FilterSettings()
        self._copy_settings(current_settings)
        self.setup_ui()

    def _copy_settings(self, src):
        fields = [
            'min_avg_mcap', 'min_avg_ath_mcap', 'min_migration_percent',
            'min_twitter_followers', 'min_community_members', 'min_admin_followers',
            'dev_tokens_count', 'enable_avg_mcap', 'enable_avg_ath_mcap',
            'enable_migrations', 'enable_twitter_user', 'enable_twitter_community',
            'enable_protocol_filter', 'use_and_mode'
        ]
        for f in fields:
            if hasattr(src, f):
                setattr(self.settings, f, getattr(src, f))
        self.settings.protocols = getattr(src, 'protocols', {k: True for k in self.settings.protocols})

    def setup_ui(self):
        self.setWindowTitle("Token Filter Settings")
        self.setModal(True)
        self.setMinimumWidth(700)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: white; }
            QGroupBox {
                color: #FFD700; font-weight: bold; border: 2px solid #404040;
                border-radius: 5px; margin-top: 12px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QSpinBox {
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
        container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(15, 15, 15, 15)

        # Заголовок
        title = QLabel("TOKEN FILTER SETTINGS")
        title.setFont(QFont('Arial', 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #1DA1F2; padding: 10px;")
        layout.addWidget(title)

        # Режим
        mode_group = QGroupBox("Filter Logic")
        mode_layout = QVBoxLayout()
        self.and_mode_cb = QCheckBox("AND Mode (all conditions must match)")
        self.and_mode_cb.setChecked(self.settings.use_and_mode)
        mode_layout.addWidget(self.and_mode_cb)
        mode_info = QLabel("Unchecked: OR Mode (any condition)")
        mode_info.setStyleSheet("color: #888; font-size: 9px; padding-left: 25px;")
        mode_layout.addWidget(mode_info)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # === ПРОТОКОЛЫ ===
        proto_group = QGroupBox("Protocols")
        proto_layout = QVBoxLayout()
        proto_check = QHBoxLayout()
        self.proto_enable_cb = QCheckBox("Enable protocol filter")
        self.proto_enable_cb.setChecked(self.settings.enable_protocol_filter)
        proto_check.addWidget(self.proto_enable_cb)
        proto_check.addStretch()
        proto_layout.addLayout(proto_check)

        # Две строки для красоты
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        self.proto_cbs = {}
        ui_names = list(PROTOCOL_MAPPING.keys())

        for i, ui_name in enumerate(ui_names):
            internal = PROTOCOL_MAPPING[ui_name]
            cb = QCheckBox(ui_name)
            cb.setChecked(self.settings.protocols.get(internal, True))
            self.proto_cbs[ui_name] = cb
            if i < 6:
                row1.addWidget(cb)
            else:
                row2.addWidget(cb)

        proto_layout.addLayout(row1)
        proto_layout.addLayout(row2)
        proto_group.setLayout(proto_layout)
        layout.addWidget(proto_group)

        # === N ===
        n_group = QGroupBox("Dev Tokens Count (N)")
        n_layout = QHBoxLayout()
        n_layout.addWidget(QLabel("Analyze last N tokens:"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 10)
        self.n_spin.setValue(self.settings.dev_tokens_count)
        n_layout.addWidget(self.n_spin)
        n_layout.addStretch()
        n_group.setLayout(n_layout)
        layout.addWidget(n_group)

        # === AVG MCAP ===
        mcap_group = QGroupBox("Dev Average Market Cap")
        mcap_layout = QVBoxLayout()
        mcap_check = QHBoxLayout()
        self.mcap_enable_cb = QCheckBox("Enable")
        self.mcap_enable_cb.setChecked(self.settings.enable_avg_mcap)
        mcap_check.addWidget(self.mcap_enable_cb)
        mcap_check.addStretch()
        mcap_layout.addLayout(mcap_check)
        mcap_in = QHBoxLayout()
        mcap_in.addWidget(QLabel("Min Avg MCAP ($):"))
        self.mcap_spin = QSpinBox()
        self.mcap_spin.setRange(0, 100000000)
        self.mcap_spin.setSingleStep(1000)
        self.mcap_spin.setValue(self.settings.min_avg_mcap)
        mcap_in.addWidget(self.mcap_spin)
        mcap_in.addStretch()
        mcap_layout.addLayout(mcap_in)
        mcap_group.setLayout(mcap_layout)
        layout.addWidget(mcap_group)

        # === AVG ATH ===
        ath_group = QGroupBox("Dev Average ATH Market Cap")
        ath_layout = QVBoxLayout()
        ath_check = QHBoxLayout()
        self.ath_enable_cb = QCheckBox("Enable")
        self.ath_enable_cb.setChecked(self.settings.enable_avg_ath_mcap)
        ath_check.addWidget(self.ath_enable_cb)
        ath_check.addStretch()
        ath_layout.addLayout(ath_check)
        ath_in = QHBoxLayout()
        ath_in.addWidget(QLabel("Min Avg ATH ($):"))
        self.ath_spin = QSpinBox()
        self.ath_spin.setRange(0, 100000000)
        self.ath_spin.setSingleStep(1000)
        self.ath_spin.setValue(self.settings.min_avg_ath_mcap)
        ath_in.addWidget(self.ath_spin)
        ath_in.addStretch()
        ath_layout.addLayout(ath_in)
        ath_group.setLayout(ath_layout)
        layout.addWidget(ath_group)

        # === MIGRATION % ===
        mig_group = QGroupBox("Migration %")
        mig_layout = QVBoxLayout()
        mig_check = QHBoxLayout()
        self.mig_enable_cb = QCheckBox("Enable")
        self.mig_enable_cb.setChecked(self.settings.enable_migrations)
        mig_check.addWidget(self.mig_enable_cb)
        mig_check.addStretch()
        mig_layout.addLayout(mig_check)
        mig_in = QHBoxLayout()
        mig_in.addWidget(QLabel("Min Migration %:"))
        self.mig_spin = QSpinBox()
        self.mig_spin.setRange(0, 100)
        self.mig_spin.setSuffix(" %")
        self.mig_spin.setValue(self.settings.min_migration_percent)
        mig_in.addWidget(self.mig_spin)
        mig_in.addStretch()
        mig_layout.addLayout(mig_in)
        mig_group.setLayout(mig_layout)
        layout.addWidget(mig_group)

        # === TWITTER ===
        tw_group = QGroupBox("Twitter Community / User")
        tw_layout = QVBoxLayout()

        user_l = QHBoxLayout()
        self.tw_user_cb = QCheckBox("User: Min Followers")
        self.tw_user_cb.setChecked(self.settings.enable_twitter_user)
        user_l.addWidget(self.tw_user_cb)
        self.tw_user_spin = QSpinBox()
        self.tw_user_spin.setRange(0, 10000000)
        self.tw_user_spin.setSingleStep(100)
        self.tw_user_spin.setValue(self.settings.min_twitter_followers)
        user_l.addWidget(self.tw_user_spin)
        user_l.addStretch()
        tw_layout.addLayout(user_l)

        comm_l = QHBoxLayout()
        self.tw_comm_cb = QCheckBox("Community: Min Members")
        self.tw_comm_cb.setChecked(self.settings.enable_twitter_community)
        comm_l.addWidget(self.tw_comm_cb)
        self.tw_comm_spin = QSpinBox()
        self.tw_comm_spin.setRange(0, 1000000)
        self.tw_comm_spin.setSingleStep(50)
        self.tw_comm_spin.setValue(self.settings.min_community_members)
        comm_l.addWidget(self.tw_comm_spin)
        comm_l.addWidget(QLabel("Admin:"))
        self.tw_admin_spin = QSpinBox()
        self.tw_admin_spin.setRange(0, 10000000)
        self.tw_admin_spin.setSingleStep(100)
        self.tw_admin_spin.setValue(self.settings.min_admin_followers)
        comm_l.addWidget(self.tw_admin_spin)
        comm_l.addStretch()
        tw_layout.addLayout(comm_l)

        info = QLabel("If both enabled → OR logic (user OR community)")
        info.setStyleSheet("color: #888; font-size: 9px; padding-left: 25px;")
        tw_layout.addWidget(info)
        tw_group.setLayout(tw_layout)
        layout.addWidget(tw_group)

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

        # === ИНФО ===
        info_text = QLabel(
            "• No filters → show all\n"
            "• OR mode: any condition → show\n"
            "• AND mode: all conditions → show\n"
            "• Twitter: User OR Community"
        )
        info_text.setStyleSheet("color: #888; font-size: 9px; padding: 10px;")
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        layout.addStretch()
        container.setLayout(layout)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def reset_settings(self):
        self.mcap_spin.setValue(0)
        self.ath_spin.setValue(0)
        self.mig_spin.setValue(0)
        self.tw_user_spin.setValue(0)
        self.tw_comm_spin.setValue(0)
        self.tw_admin_spin.setValue(0)
        self.n_spin.setValue(10)

        self.mcap_enable_cb.setChecked(False)
        self.ath_enable_cb.setChecked(False)
        self.mig_enable_cb.setChecked(False)
        self.tw_user_cb.setChecked(False)
        self.tw_comm_cb.setChecked(False)
        self.proto_enable_cb.setChecked(False)

        for cb in self.proto_cbs.values():
            cb.setChecked(True)

        self.and_mode_cb.setChecked(False)

    def apply_settings(self):
        self.settings.min_avg_mcap = self.mcap_spin.value()
        self.settings.min_avg_ath_mcap = self.ath_spin.value()
        self.settings.min_migration_percent = self.mig_spin.value()
        self.settings.min_twitter_followers = self.tw_user_spin.value()
        self.settings.min_community_members = self.tw_comm_spin.value()
        self.settings.min_admin_followers = self.tw_admin_spin.value()
        self.settings.dev_tokens_count = self.n_spin.value()

        self.settings.enable_avg_mcap = self.mcap_enable_cb.isChecked()
        self.settings.enable_avg_ath_mcap = self.ath_enable_cb.isChecked()
        self.settings.enable_migrations = self.mig_enable_cb.isChecked()
        self.settings.enable_twitter_user = self.tw_user_cb.isChecked()
        self.settings.enable_twitter_community = self.tw_comm_cb.isChecked()
        self.settings.enable_protocol_filter = self.proto_enable_cb.isChecked()

        for ui_name, cb in self.proto_cbs.items():
            internal = PROTOCOL_MAPPING[ui_name]
            self.settings.protocols[internal] = cb.isChecked()

        self.settings.use_and_mode = self.and_mode_cb.isChecked()

        self.settings.save_to_file()
        self.settings_changed.emit(self.settings)
        self.accept()