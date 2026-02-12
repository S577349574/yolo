from gui.tabs.tab_key_strategy import build_key_strategy_tab
from gui.tabs.tab_notice import build_notice_tab
from gui.tabs.tab_system import build_system_tab

from gui.tabs.tab_image_source import build_image_source_tab

from gui.tabs.tab_preview import build_preview_tab

from gui.tabs.tab_driver_keys import build_driver_keys_tab

from gui.tabs.tab_scripts import build_scripts_tab

from gui.tabs.tab_features import build_features_tab


def build_main_window(blue_notice_theme):
    build_system_tab(blue_notice_theme)
    build_image_source_tab(blue_notice_theme)
    build_preview_tab(blue_notice_theme)
    build_driver_keys_tab(blue_notice_theme)
    build_scripts_tab(blue_notice_theme)
    build_key_strategy_tab()
    build_features_tab(blue_notice_theme)
    build_notice_tab(blue_notice_theme)