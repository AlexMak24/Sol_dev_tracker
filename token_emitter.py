# token_emitter.py
from PySide6.QtCore import QObject, Signal

class TokenEmitter(QObject):
    new_token = Signal(dict)

token_emitter = TokenEmitter()