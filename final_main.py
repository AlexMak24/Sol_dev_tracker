# main.py
import sys
from threading import Thread
from PySide6.QtWidgets import QApplication
from gui_window import MainWindow
from new_ws_final_V1 import AxiomTracker  # твой настоящий трекер


def main():
    print("=" * 80)
    print(" AXIOM TOKEN STREAM - REAL MODE")
    print("=" * 80)
    print(" Real-time tokens from Axiom")
    print(" Real Twitter stats + Dev MCAP")
    print(" GUI updates live")
    print("=" * 80)
    print()

    # === Qt приложение ===
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # === Параметры ===
    AUTH_FILE = "auth_data.json"
    TWITTER_API_KEY = "new1_d84d121d635d4b2aa0680a22e25c08d2"

    # === Запуск трекера в ОТДЕЛЬНОМ ПОТОКЕ ===
    def run_tracker():
        tracker = AxiomTracker(
            auth_file=AUTH_FILE,
            twitter_api_key=TWITTER_API_KEY,
            avg_tokens_count=10
        )
        try:
            tracker.start()  # ← run_forever() здесь, но в отдельном потоке
        except KeyboardInterrupt:
            tracker.stop()

    tracker_thread = Thread(target=run_tracker, daemon=True)
    tracker_thread.start()

    print("\nApplication started! Watch the GUI window.\n")

    # === Запуск GUI (главный поток свободен!) ===
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()