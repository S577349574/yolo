from tabs.tab_notice import build_notice_tab
from tabs.tab_system import build_system_tab


def build_main_window(blue_notice_theme):
    build_notice_tab(blue_notice_theme)
    build_system_tab(blue_notice_theme)
    # build_image_source_tab()
    # build_preview_tab()
    # build_driver_keys_tab()
    # build_scripts_tab()
    # build_features_tab()