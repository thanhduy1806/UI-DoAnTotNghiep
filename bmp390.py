from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from theme import get_theme


def create_on_board_condition_strip(parent):
    strip = QFrame()
    strip.setObjectName("onBoardCondition")
    strip._condition_title = QLabel("ON BOARD CONDITION")
    strip._condition_title.setStyleSheet("background:transparent;")

    layout = QHBoxLayout(strip)
    layout.setContentsMargins(12, 4, 12, 4)
    layout.setSpacing(16)

    parent.bmp390_temp_label = QLabel("Temperature: 0.0 C")
    parent.bmp390_press_label = QLabel("Pressure: 0.0 Pa")
    for label in (parent.bmp390_temp_label, parent.bmp390_press_label):
        label.setStyleSheet("background:transparent;")

    layout.addWidget(strip._condition_title)
    layout.addWidget(parent.bmp390_temp_label)
    layout.addWidget(parent.bmp390_press_label)

    apply_on_board_condition_theme(parent)

    return strip


def apply_on_board_condition_theme(parent):
    if not hasattr(parent, "on_board_condition"):
        return

    t = get_theme()
    parent.on_board_condition.setStyleSheet(f"""
        QFrame#onBoardCondition {{
            background-color: {t["bg_surface"]};
            border: 1px solid {t["border"]};
            border-radius: 6px;
        }}
    """)

    parent.on_board_condition._condition_title.setStyleSheet(
        f"color:{t['accent_cyan']};font-size:12px;font-weight:800;"
        "background:transparent;"
    )
    for label in (parent.bmp390_temp_label, parent.bmp390_press_label):
        label.setStyleSheet(
            f"color:{t['text_primary']};font-size:12px;font-weight:600;"
            "background:transparent;"
        )


def create_bmp390_show_box(parent):
    return create_on_board_condition_strip(parent)


def update_bmp390_ui(parent, temp, press, pressure_unit="Pa"):

    parent.bmp390_temp_label.setText(
        f"Temperature: {temp:.2f} C"
    )

    parent.bmp390_press_label.setText(
        f"Pressure: {press:.2f} {pressure_unit}"
    )
