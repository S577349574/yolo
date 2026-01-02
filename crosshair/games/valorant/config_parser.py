# crosshair/games/valorant/config_parser.py
"""
Valorant 准星配置解析器（使用统一颜色定义）
"""
from typing import Dict, Optional
from .valorant_colors import (
    VALORANT_COLOR_NAMES,
    VALORANT_COLOR_HEX,
    VALORANT_COLOR_RGB,
    VALORANT_COLOR_BGR,
    get_color_by_index
)


class ValorantConfigParser:
    """Valorant 准星配置解析器"""

    @staticmethod
    def parse(config_code: str) -> Dict:
        """解析 Valorant 准星配置代码"""
        if not config_code:
            return ValorantConfigParser._get_default_config()

        parts = config_code.split(';')

        # 初始化配置（使用统一颜色定义）
        default_color = get_color_by_index(1)  # 默认绿色
        config = {
            'profile_index': 0,
            'color_index': 1,
            'color_name': default_color['name'],
            'color_hex': default_color['hex'],
            'color_rgb': default_color['rgb'],
            'color_bgr': default_color['bgr'],
            'center_dot': {
                'enabled': False,
                'thickness': 2,
                'opacity': 1.0,
            },
            'inner_lines': {
                'enabled': True,
                'opacity': 0.8,
                'length': 6,
                'vertical_length': 6,
                'thickness': 3,
                'offset': 3,
                'firing_error': True,
                'movement_error': False,
                'movement_multiplier': 1.0,
                'firing_multiplier': 1.0,
            },
            'outer_lines': {
                'enabled': True,
                'opacity': 0.35,
                'length': 2,
                'thickness': 2,
                'offset': 10,
            },
            'outline': {
                'enabled': True,
                'thickness': 1,
                'opacity': 0.5,
            },
            'crosshair_type': 'standard'
        }

        # 标志记录
        has_h_param = False
        has_0b_disable = False
        has_1b_disable = False

        # 解析参数
        i = 0
        while i < len(parts):
            key = parts[i]
            value = parts[i + 1] if i + 1 < len(parts) else None

            if value is None:
                i += 1
                continue

            # 记录关键标志
            if key == 'h':
                has_h_param = True

            if key == '0b':
                val = ValorantConfigParser._parse_number(value)
                if val is not None and val == 0:
                    has_0b_disable = True

            if key == '1b':
                val = ValorantConfigParser._parse_number(value)
                if val is not None and val == 0:
                    has_1b_disable = True

            ValorantConfigParser._parse_param(key, value, config)
            i += 2

        # 后处理：启用逻辑
        if has_0b_disable:
            config['inner_lines']['enabled'] = False

        if has_1b_disable:
            config['outer_lines']['enabled'] = False

        if has_h_param:
            config['outline']['enabled'] = False

        # 推断准星类型
        config['crosshair_type'] = ValorantConfigParser._infer_type(config)

        return config

    @staticmethod
    def _parse_param(key: str, value: str, config: Dict) -> bool:
        """解析单个参数"""

        # 配置文件索引
        if key.isdigit() and len(key) == 1:
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['profile_index'] = int(val)
                return True

        # c: Color - ⭐ 使用统一颜色定义
        if key == 'c':
            try:
                color_index = int(value)
                if 0 <= color_index <= 7:
                    color_info = get_color_by_index(color_index)
                    config['color_index'] = color_index
                    config['color_name'] = color_info['name']
                    config['color_hex'] = color_info['hex']
                    config['color_rgb'] = color_info['rgb']
                    config['color_bgr'] = color_info['bgr']
                    return True
            except (ValueError, TypeError):
                pass
            return False

        # t: ouTline thickness
        if key == 't':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outline']['thickness'] = int(val)
                return True

        # o: Outline opacity
        if key == 'o':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outline']['opacity'] = val
                return True

        # d: center Dot
        if key == 'd':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['center_dot']['enabled'] = (val == 1)
                return True

        # z: center dot thickness
        if key == 'z':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['center_dot']['thickness'] = int(val)
                return True

        # a: center dot opacity
        if key == 'a':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['center_dot']['opacity'] = val
                return True

        # h: 禁用轮廓的标志
        if key == 'h':
            return True

        if key == 'f':
            return True

        if key == 'm':
            return True

        # 0b: inner lines 禁用标志
        if key == '0b':
            return True

        # 0t: inner line thickness
        if key == '0t':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['thickness'] = int(val)
                return True

        # 0l: inner line length (左右)
        if key == '0l':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['length'] = int(val)
                return True

        # 0v: inner line vertical length (上下)
        if key == '0v':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['vertical_length'] = int(val)
                return True

        # 0o: inner line offset
        if key == '0o':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['offset'] = int(val)
                return True

        # 0a: inner line opacity
        if key == '0a':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['opacity'] = val
                return True

        # 0m: inner line movement error
        if key == '0m':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['movement_error'] = (val == 1)
                return True

        # 0f: inner line firing error
        if key == '0f':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['firing_error'] = (val == 1)
                return True

        # 0s: movement error multiplier
        if key == '0s':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['movement_multiplier'] = val
                return True

        # 0e: firing error multiplier
        if key == '0e':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['inner_lines']['firing_multiplier'] = val
                return True

        # 0g: 未知参数
        if key == '0g':
            return True

        # 1b: outer lines 禁用标志
        if key == '1b':
            return True

        # 1t: outer line thickness
        if key == '1t':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outer_lines']['thickness'] = int(val)
                return True

        # 1l: outer line length
        if key == '1l':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outer_lines']['length'] = int(val)
                return True

        # 1o: outer line offset
        if key == '1o':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outer_lines']['offset'] = int(val)
                return True

        # 1a: outer line opacity
        if key == '1a':
            val = ValorantConfigParser._parse_number(value)
            if val is not None:
                config['outer_lines']['opacity'] = val
                return True

        return False

    @staticmethod
    def _parse_number(value: str) -> Optional[float]:
        """解析数字（支持小数）"""
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _infer_type(config: Dict) -> str:
        """推断准星类型"""
        has_center = config['center_dot']['enabled']
        has_inner = config['inner_lines']['enabled']
        has_outer = config['outer_lines']['enabled']

        if has_center and not has_inner and not has_outer:
            return 'dot_only'
        elif has_inner and has_outer:
            return 'full_cross'
        elif has_inner:
            return 'standard'
        elif has_outer:
            return 'outer_only'
        else:
            return 'minimal'

    @staticmethod
    def _get_default_config() -> Dict:
        """获取默认配置"""
        default_color = get_color_by_index(1)  # 绿色
        return {
            'profile_index': 0,
            'color_index': 1,
            'color_name': default_color['name'],
            'color_hex': default_color['hex'],
            'color_rgb': default_color['rgb'],
            'color_bgr': default_color['bgr'],
            'center_dot': {
                'enabled': False,
                'thickness': 2,
                'opacity': 1.0,
            },
            'inner_lines': {
                'enabled': True,
                'opacity': 0.8,
                'length': 6,
                'vertical_length': 6,
                'thickness': 3,
                'offset': 3,
                'firing_error': True,
                'movement_error': False,
                'movement_multiplier': 1.0,
                'firing_multiplier': 1.0,
            },
            'outer_lines': {
                'enabled': True,
                'opacity': 0.35,
                'length': 2,
                'thickness': 2,
                'offset': 10,
            },
            'outline': {
                'enabled': True,
                'thickness': 1,
                'opacity': 0.5,
            },
            'crosshair_type': 'standard'
        }

    @staticmethod
    def describe(config: Dict) -> str:
        """生成配置的可读描述"""
        parts = []

        color_name = config.get('color_name', 'Unknown')
        color_hex = config.get('color_hex', '#FFFFFF')
        parts.append(f"颜色:{color_name}({color_hex})")

        if config['center_dot']['enabled']:
            dot = config['center_dot']
            parts.append(
                f"中心点(大小:{dot['thickness']}, 透明度:{dot['opacity']:.2f})"
            )

        if config['inner_lines']['enabled']:
            inner = config['inner_lines']
            v_len = inner.get('vertical_length', inner['length'])
            parts.append(
                f"内线(左右:{inner['length']}, 上下:{v_len}, 厚:{inner['thickness']}, "
                f"偏移:{inner['offset']}, 透明度:{inner['opacity']:.2f})"
            )

        if config['outer_lines']['enabled']:
            outer = config['outer_lines']
            parts.append(
                f"外线(长:{outer['length']}, 厚:{outer['thickness']}, "
                f"偏移:{outer['offset']}, 透明度:{outer['opacity']:.2f})"
            )

        if config['outline']['enabled']:
            outline = config['outline']
            parts.append(
                f"描边(厚度:{outline['thickness']}, 透明度:{outline['opacity']:.2f})"
            )

        return ' + '.join(parts) if parts else '空准星'


# 测试代码
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Valorant 准星配置解析器测试（使用统一颜色定义）")
    print("=" * 70)

    test_cases = [
        ("绿色准星", "0;P;c;1;d;1;0b;0;1b;0"),
        ("红色准星", "0;P;c;7;d;1;0b;0;1b;0"),
        ("青色准星", "0;P;c;5;d;1;0b;0;1b;0"),
        ("默认配置", ""),
    ]

    for name, code in test_cases:
        print(f"\n{'=' * 70}")
        print(f"测试: {name}")
        print(f"配置码: {code}")
        print(f"{'=' * 70}")

        config = ValorantConfigParser.parse(code)

        print(f"颜色索引: {config['color_index']}")
        print(f"颜色名称: {config['color_name']}")
        print(f"十六进制: {config['color_hex']}")
        print(f"RGB: {config['color_rgb']}")
        print(f"BGR: {config['color_bgr']}")

        print(f"\n描述: {ValorantConfigParser.describe(config)}")

    print("\n" + "=" * 70)
    print("✅ 所有测试完成")
    print("=" * 70)
