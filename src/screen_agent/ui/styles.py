"""QSS styles for the UI components."""

MAIN_WINDOW_STYLE = """
QMainWindow {
    background-color: #1e1e1e;
}

QWidget#centralWidget {
    background-color: #1e1e1e;
}

QLineEdit, QTextEdit {
    padding: 10px;
    border: 2px solid #3c3c3c;
    border-radius: 6px;
    background-color: #2d2d2d;
    color: #ffffff;
    font-size: 14px;
    selection-background-color: #4CAF50;
}

QLineEdit:focus, QTextEdit:focus {
    border-color: #4CAF50;
}

QPushButton {
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: bold;
    border: none;
}

QPushButton#startBtn {
    background-color: #4CAF50;
    color: white;
}

QPushButton#startBtn:hover {
    background-color: #45a049;
}

QPushButton#startBtn:pressed {
    background-color: #3d8b40;
}

QPushButton#startBtn:disabled {
    background-color: #555555;
    color: #888888;
}

QPushButton#stopBtn {
    background-color: #f44336;
    color: white;
}

QPushButton#stopBtn:hover {
    background-color: #da190b;
}

QPushButton#stopBtn:pressed {
    background-color: #b71c1c;
}

QPushButton#stopBtn:disabled {
    background-color: #555555;
    color: #888888;
}

QLabel {
    color: #ffffff;
    font-size: 13px;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #4CAF50;
}

QLabel#statusLabel {
    font-size: 14px;
    padding: 5px;
    border-radius: 4px;
    background-color: #2d2d2d;
}
"""

OVERLAY_STYLE = """
QWidget#overlayContainer {
    background-color: rgba(30, 30, 30, 230);
    border-radius: 10px;
    border: 1px solid rgba(76, 175, 80, 100);
}

QLabel {
    color: #ffffff;
    font-size: 12px;
    background: transparent;
}

QLabel#actionLabel {
    font-size: 14px;
    font-weight: bold;
    color: #4CAF50;
    padding: 5px;
}

QLabel#sectionLabel {
    font-size: 11px;
    font-weight: bold;
    color: #888888;
    padding-top: 8px;
}

QLabel#contentLabel {
    font-size: 12px;
    color: #cccccc;
    padding: 2px 5px;
}
"""
