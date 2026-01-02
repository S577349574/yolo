"""
Valorant 准星颜色定义
包含所有颜色格式：索引、名称、十六进制、RGB、BGR
"""

# 颜色索引映射（内部键名）
VALORANT_COLOR_INDEX = {
    0: 'white',
    1: 'green',
    2: 'yellow_green',
    3: 'green_yellow',
    4: 'yellow',
    5: 'cyan',
    6: 'pink',
    7: 'red',
}

# 颜色显示名称
VALORANT_COLOR_NAMES = {
    0: 'White',
    1: 'Green',
    2: 'Yellow Green',
    3: 'Green Yellow',
    4: 'Yellow',
    5: 'Cyan',
    6: 'Pink',
    7: 'Red',
}

# 十六进制颜色（游戏内格式）
VALORANT_COLOR_HEX = {
    0: '#FFFFFF',  # White
    1: '#00FF00',  # Green
    2: '#80FF00',  # Yellow Green
    3: '#C8FF00',  # Green Yellow
    4: '#FFFF00',  # Yellow
    5: '#00FFFF',  # Cyan
    6: '#FF00FF',  # Pink
    7: '#FF0000',  # Red
}

# RGB 格式（标准）
VALORANT_COLOR_RGB = {
    0: (255, 255, 255),  # White
    1: (0, 255, 0),      # Green
    2: (128, 255, 0),    # Yellow Green
    3: (200, 255, 0),    # Green Yellow
    4: (255, 255, 0),    # Yellow
    5: (0, 255, 255),    # Cyan
    6: (255, 0, 255),    # Pink
    7: (255, 0, 0),      # Red
}

# BGR 格式（OpenCV）
VALORANT_COLOR_BGR = {
    0: (255, 255, 255),  # White
    1: (0, 255, 0),      # Green
    2: (0, 255, 128),    # Yellow Green
    3: (0, 255, 200),    # Green Yellow
    4: (0, 255, 255),    # Yellow
    5: (255, 255, 0),    # Cyan
    6: (255, 0, 255),    # Pink
    7: (0, 0, 255),      # Red - ⭐ 注意：BGR格式，所以红色是 (0, 0, 255)
}


def get_color_by_index(index: int) -> dict:
    """根据索引获取颜色信息"""
    return {
        'index': index,
        'name': VALORANT_COLOR_NAMES.get(index, 'Unknown'),
        'hex': VALORANT_COLOR_HEX.get(index, '#FFFFFF'),
        'rgb': VALORANT_COLOR_RGB.get(index, (255, 255, 255)),
        'bgr': VALORANT_COLOR_BGR.get(index, (255, 255, 255)),
    }


def hex_to_rgb(hex_color: str) -> tuple:
    """十六进制转RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def hex_to_bgr(hex_color: str) -> tuple:
    """十六进制转BGR"""
    r, g, b = hex_to_rgb(hex_color)
    return (b, g, r)


def rgb_to_hex(rgb: tuple) -> str:
    """RGB转十六进制"""
    r, g, b = rgb
    return f'#{r:02X}{g:02X}{b:02X}'


def print_color_table():
    """打印颜色对照表"""
    print("=" * 80)
    print("Valorant 准星颜色完整对照表")
    print("=" * 80)
    print(f"{'索引':<6} {'名称':<15} {'十六进制':<10} {'RGB':<18} {'BGR':<18}")
    print("-" * 80)

    for i in range(8):
        info = get_color_by_index(i)
        print(f"{i:<6} {info['name']:<15} {info['hex']:<10} {str(info['rgb']):<18} {str(info['bgr']):<18}")

    print("=" * 80)


if __name__ == "__main__":
    print_color_table()
