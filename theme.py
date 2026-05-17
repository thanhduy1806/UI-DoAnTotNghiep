_CURRENT_THEME = "dark"


THEMES = {
    "dark": {
        "bg_deep": "#070B12",
        "bg_panel": "#0E1420",
        "bg_surface": "#131B2A",
        "bg_card": "#192338",
        "border": "#2B3B5E",
        "text_primary": "#F4F8FF",
        "text_secondary": "#B9C7DD",
        "log_text": "#B7D9EA",
        "button_pressed": "#0B111C",
        "accent_cyan": "#00C8E8",
        "accent_teal": "#00E5B0",
        "accent_warn": "#F59E0B",
        "accent_err": "#FF5C5C",
        "accent_prp": "#BD93F9",
        "tab_text": "#C8D6EF",
        "select_text": "#061018",
        "hover_surface": "#18253B",
        "laser_idle_text": "#BFD0EA",
        "laser_hover_text": "#7EEBFF",
        "laser_pressed": "#0C1830",
        "laser_active_bg": "#04313A",
        "laser_active_hover": "#06424D",
        "all_on_bg": "#064B5D",
        "all_on_hover": "#075D72",
        "all_on_pressed": "#043541",
        "all_off_bg": "#4A3412",
        "all_off_hover": "#5C4218",
        "all_off_pressed": "#33240D",
    },
    "light": {
        "bg_deep": "#EEF4F8",
        "bg_panel": "#FFFFFF",
        "bg_surface": "#F4F8FB",
        "bg_card": "#E8F2F7",
        "border": "#9DB2C8",
        "text_primary": "#102033",
        "text_secondary": "#4F6378",
        "log_text": "#214158",
        "button_pressed": "#DDEAF2",
        "accent_cyan": "#007FA3",
        "accent_teal": "#008C73",
        "accent_warn": "#A96800",
        "accent_err": "#C93636",
        "accent_prp": "#7C3AED",
        "tab_text": "#25435D",
        "select_text": "#FFFFFF",
        "hover_surface": "#DCECF4",
        "laser_idle_text": "#25435D",
        "laser_hover_text": "#005E7A",
        "laser_pressed": "#CFE3EF",
        "laser_active_bg": "#D7F4EE",
        "laser_active_hover": "#C2ECE3",
        "all_on_bg": "#D9F1F7",
        "all_on_hover": "#C6EAF3",
        "all_on_pressed": "#B3DFEA",
        "all_off_bg": "#F6E6C9",
        "all_off_hover": "#ECD8B3",
        "all_off_pressed": "#DFC699",
    },
}


def current_theme_name():
    return _CURRENT_THEME


def get_theme():
    return THEMES[_CURRENT_THEME]


def toggle_theme():
    global _CURRENT_THEME
    _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
    return _CURRENT_THEME


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def app_stylesheet():
    t = get_theme()
    scrollbar_handle = _rgba(t["accent_cyan"], 0.22)
    scrollbar_handle_hover = _rgba(t["accent_cyan"], 0.34)
    scrollbar_handle_pressed = _rgba(t["accent_cyan"], 0.14)
    return f"""
QWidget {{
    background-color: {t["bg_deep"]};
    color: {t["text_primary"]};
    font-family: "Segoe UI";
    font-size: 14px;
}}

QFrame {{
    background-color: transparent;
}}

QGroupBox {{
    background-color: {t["bg_panel"]};
    border: 1.5px solid {t["border"]};
    border-radius: 8px;
    margin-top: 20px;
    padding: 8px;
}}

QGroupBox::title {{
    color: {t["accent_cyan"]};
    subcontrol-origin: margin;
    left: 12px;
    top: 2px;
    font-size: 14px;
    font-weight: 700;
}}

QTextEdit {{
    background-color: {t["bg_surface"]};
    border: 1.5px solid {t["border"]};
    border-radius: 6px;
    color: {t["log_text"]};
    font-family: Consolas;
    font-size: 13px;
}}

QTabWidget::pane {{
    border: 1.5px solid {t["border"]};
    background: {t["bg_panel"]};
}}

QTabBar::tab {{
    background: {t["bg_surface"]};
    padding: 8px 12px;
    border: 1.5px solid {t["border"]};
    color: {t["tab_text"]};
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background: {t["bg_card"]};
    color: {t["accent_cyan"]};
}}

QLabel {{
    color: {t["text_primary"]};
}}

QPushButton {{
    min-height: 30px;
    background-color: {t["bg_surface"]};
    border: 1.5px solid {t["border"]};
    border-radius: 6px;
    color: {t["text_primary"]};
    font-weight: 700;
    padding: 4px 10px;
}}

QPushButton:hover {{
    border-color: {t["accent_cyan"]};
}}

QPushButton:pressed {{
    background-color: {t["button_pressed"]};
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    selection-background-color: {t["accent_cyan"]};
    selection-color: {t["select_text"]};
}}

QScrollBar:vertical {{
    background: {t["bg_surface"]};
    border: 1.5px solid {t["border"]};
    border-radius: 6px;
    width: 14px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    border: 1.5px solid {t["accent_cyan"]};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {scrollbar_handle_hover};
}}

QScrollBar::handle:vertical:pressed {{
    background: {scrollbar_handle_pressed};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    background: transparent;
    border: none;
    height: 0;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: {t["bg_surface"]};
    border: 1.5px solid {t["border"]};
    border-radius: 6px;
    height: 14px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {scrollbar_handle};
    border: 1.5px solid {t["accent_cyan"]};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {scrollbar_handle_hover};
}}

QScrollBar::handle:horizontal:pressed {{
    background: {scrollbar_handle_pressed};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    background: transparent;
    border: none;
    width: 0;
}}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""


def outline_button_style(accent=None):
    t = get_theme()
    accent = accent or t["accent_cyan"]
    return f"""
        QPushButton {{
            background-color: {t["bg_surface"]};
            border: 1.5px solid {accent};
            border-radius: 6px;
            color: {accent};
            font-size: 13px;
            font-weight: 800;
            padding: 4px 10px;
        }}
        QPushButton:hover {{
            background-color: {t["hover_surface"]};
        }}
        QPushButton:pressed {{
            background-color: {t["button_pressed"]};
        }}
    """


def filled_button_style(accent=None):
    t = get_theme()
    accent = accent or t["accent_teal"]
    return f"""
        QPushButton {{
            background-color: {t["bg_card"]};
            border: 1.5px solid {accent};
            border-radius: 6px;
            color: {t["text_primary"]};
            font-size: 13px;
            font-weight: 800;
        }}
        QPushButton:hover {{
            background-color: {t["hover_surface"]};
        }}
        QPushButton:pressed {{
            background-color: {t["button_pressed"]};
        }}
    """


def combo_style():
    t = get_theme()
    return f"""
        QComboBox {{
            background-color: {t["bg_surface"]};
            border: 1.5px solid {t["border"]};
            border-radius: 6px;
            color: {t["text_primary"]};
            font-size: 13px;
            font-weight: 600;
            padding: 4px 10px;
        }}
        QComboBox:hover {{ border-color: {t["accent_cyan"]}; }}
        QComboBox:disabled {{
            color: {t["text_secondary"]};
            border-color: {t["border"]};
        }}
        QComboBox::drop-down {{ border: none; width: 26px; }}
    """
