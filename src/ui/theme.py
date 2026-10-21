"""Shared Qt styling; native widgets retain keyboard and accessibility support."""
from pathlib import Path
from string import Template
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication, theme: str = "light") -> None:
    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    colors = {
        "window": "#151b27", "surface": "#202838", "alternate": "#252e40",
        "text": "#edf1fb", "muted": "#abb8cf", "border": "#3b4860",
        "hover": "#2b364b", "selection": "#354974", "selected_text": "#edf2ff",
        "accent": "#526bcc", "accent_hover": "#607ada", "accent_pressed": "#455db5",
        "focus": "#91a9ff", "disabled": "#252d3b", "disabled_text": "#8491a7",
        "track": "#2a354a", "chunk": "#536eb4", "scroll": "#4b5d7d",
        "scroll_hover": "#7389af", "success": "#7fd4a7", "error": "#ff9797",
    } if theme == "dark" else {
        "window": "#f3f5fa", "surface": "#ffffff", "alternate": "#f8f9fc",
        "text": "#202b43", "muted": "#66738d", "border": "#dce2ec",
        "hover": "#edf1fa", "selection": "#e4eaff", "selected_text": "#253c83",
        "accent": "#4b62c6", "accent_hover": "#3d52b1", "accent_pressed": "#304396",
        "focus": "#657fd9", "disabled": "#edf0f6", "disabled_text": "#8791a4",
        "track": "#e8edf7", "chunk": "#9bafea", "scroll": "#c7d1e5",
        "scroll_hover": "#9eafcf", "success": "#23754b", "error": "#b8303a",
    }
    palette = QPalette()
    for role, name in (
        (QPalette.Window, "window"), (QPalette.WindowText, "text"),
        (QPalette.Base, "surface"), (QPalette.AlternateBase, "alternate"),
        (QPalette.Text, "text"), (QPalette.Button, "surface"),
        (QPalette.ButtonText, "text"), (QPalette.Highlight, "selection"),
        (QPalette.HighlightedText, "selected_text"), (QPalette.PlaceholderText, "muted"),
        (QPalette.ToolTipBase, "text"), (QPalette.ToolTipText, "surface"),
        (QPalette.Light, "border"), (QPalette.Mid, "border"), (QPalette.Dark, "window"),
    ):
        palette.setColor(role, QColor(colors[name]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        palette.setColor(QPalette.Disabled, role, QColor(colors["disabled_text"]))
    app.setPalette(palette)
    resources = Path(__file__).resolve().parents[1] / "resources"
    app.setStyleSheet(Template("""
        QMainWindow, QDialog { background: $window; }
        QLabel#heroTitle { font-size: 27px; font-weight: 700; color: $text; }
        QLabel#subtitle, QLabel#emptyState { color: $muted; }
        QLabel#emptyState { font-size: 15px; }
        QLabel#badge { background: $selection; color: $selected_text; border-radius: 12px;
                       padding: 8px 16px; font-weight: 600; }
        QLabel#sectionTitle { font-size: 16px; font-weight: 600; padding: 8px 0; }
        QLabel#preview { background: $hover; color: $muted; border-radius: 8px; padding: 12px; }
        QMenuBar { background: $window; padding: 4px 12px; }
        QMenuBar::item:selected, QMenu::item:selected { background: $selection; color: $selected_text; }
        QMenu { background: $surface; border: 1px solid $border; padding: 6px; }
        QMenu::item { padding: 8px 24px; }
        QPushButton { background: $surface; border: 1px solid $border; border-radius: 8px;
                      padding: 8px 14px; min-height: 20px; font-weight: 600; }
        QPushButton:hover { background: $hover; border-color: $focus; }
        QPushButton:checked { background: $selection; border-color: $focus; color: $selected_text; }
        QPushButton:pressed { background: $selection; }
        QPushButton:focus { border: 2px solid $focus; padding: 7px 13px; }
        QPushButton[primary="true"] { background: $accent; border-color: $accent; color: $on_accent; }
        QPushButton[primary="true"]:hover { background: $accent_hover; }
        QPushButton[primary="true"]:pressed { background: $accent_pressed; }
        QPushButton:disabled { background: $disabled; border-color: $border; color: $disabled_text; }
        QPushButton[primary="true"]:disabled { background: $disabled; border-color: $disabled; color: $disabled_text; }
        QLineEdit, QComboBox, QSpinBox, QTextEdit { background: $surface; color: $text;
            border: 1px solid $border; border-radius: 6px; padding: 6px 9px;
            selection-background-color: $selection; selection-color: $selected_text; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus { border-color: $focus; }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { background: $disabled; color: $disabled_text; }
        QComboBox { min-height: 20px; padding-right: 24px; }
        QComboBox::drop-down { border: none; width: 26px; }
        QComboBox::down-arrow { image: url("$DOWN"); width: 12px; height: 12px; }
        QSpinBox { min-height: 20px; padding-right: 26px; }
        QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
            width: 24px; border: none; background: $hover; border-top-right-radius: 6px; }
        QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
            width: 24px; border: none; background: $hover; border-bottom-right-radius: 6px; }
        QSpinBox::up-arrow { image: url("$UP"); width: 10px; height: 10px; }
        QSpinBox::down-arrow { image: url("$DOWN"); width: 10px; height: 10px; }
        QComboBox QAbstractItemView { background: $surface; selection-background-color: $selection;
            selection-color: $selected_text; border: 1px solid $border; padding: 4px; }
        QGroupBox { background: $surface; border: 1px solid $border; border-radius: 10px;
            margin-top: 16px; padding: 15px 12px 10px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; color: $muted; }
        QTabWidget::pane { background: $surface; border: 1px solid $border; border-radius: 10px; top: -1px; }
        QTabBar::tab { padding: 12px 18px; margin-right: 3px; border-bottom: 3px solid transparent;
            color: $muted; font-weight: 600; }
        QTabBar::tab:selected { color: $selected_text; border-bottom-color: $accent; background: $selection; }
        QTabBar::tab:hover { background: $hover; }
        QTabBar::tab:disabled { color: $disabled_text; }
        QTableWidget, QTreeWidget { background: $surface; border: 1px solid $border;
            border-radius: 10px; alternate-background-color: $alternate;
            selection-background-color: $selection; selection-color: $selected_text; }
        QTableWidget::item, QTreeWidget::item { padding: 7px; border-bottom: 1px solid $alternate; }
        QHeaderView::section { background: $hover; color: $muted; padding: 10px 7px;
            border: none; border-bottom: 1px solid $border; font-size: 12px; font-weight: 600; }
        QProgressBar { border: none; border-radius: 6px; background: $track;
            color: $selected_text; min-height: 20px; text-align: center; }
        QProgressBar::chunk { border-radius: 6px; background: $chunk; }
        QRadioButton, QCheckBox { spacing: 8px; padding: 3px 0; }
        QSplitter::handle { background: transparent; width: 18px; }
        QSplitter::handle:hover { background: $selection; }
        QStatusBar { background: $hover; color: $muted; padding: 3px 12px; }
        QStatusBar::item { border: none; }
        QScrollArea, QScrollArea > QWidget > QWidget { background: $surface; border: none; }
        QScrollBar:vertical { background: $alternate; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: $scroll; min-height: 28px; border-radius: 5px; }
        QScrollBar::handle:vertical:hover { background: $scroll_hover; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        QToolTip { background: $text; color: $surface; border: none; padding: 7px; }
        QLabel#coverPreview { background: $alternate; border: 2px dashed $border; border-radius: 8px; }
        QLabel#muted { color: $muted; }
        QLabel#success { color: $success; }
        QLabel#error { color: $error; }
    """).substitute(colors, on_accent="#ffffff",
                      DOWN=(resources / "chevron-down.svg").as_posix(),
                      UP=(resources / "chevron-up.svg").as_posix()))
