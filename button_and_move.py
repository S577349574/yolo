import serial
import time

print('打开串口\n')
ser = serial.Serial('COM3', 115200, timeout=0.1)  # 添加超时
print('向kmbox发送 import km')
ser.write('import km\r\n'.encode('utf-8'))
time.sleep(0.1)
print('kmbox回码如下：', ser.read(ser.in_waiting or 1))

# ========== 配置 ==========
# 监听的按键: 'left' 左键, 'right' 右键, 'middle' 中键, 'side1' 侧键1, 'side2' 侧键2
BUTTON = 'middle'
MOVE_STEP = 1       # 每次移动的像素
MOVE_DELAY = 0.001  # 移动间隔时间（秒）
# ==========================

# 按键配置映射
BUTTON_CONFIG = {
    'left':   {'cmd': 'km.left()',   'name': '左键',   'dx': -MOVE_STEP, 'dy': -MOVE_STEP},
    'right':  {'cmd': 'km.right()',  'name': '右键',   'dx': MOVE_STEP,  'dy': MOVE_STEP},
    'middle': {'cmd': 'km.middle()', 'name': '中键',   'dx': 0,          'dy': -MOVE_STEP},
    'side1':  {'cmd': 'km.side1()',  'name': '侧键1',  'dx': -MOVE_STEP, 'dy': 0},
    'side2':  {'cmd': 'km.side2()',  'name': '侧键2',  'dx': MOVE_STEP,  'dy': 0},
}

config = BUTTON_CONFIG.get(BUTTON, BUTTON_CONFIG['right'])
BUTTON_CMD = config['cmd']
BUTTON_NAME = config['name']
MOVE_DX = config['dx']
MOVE_DY = config['dy']

def get_button_state():
    """发送命令并获取按钮状态，返回1表示按住，0表示松开，-1表示无效"""
    ser.write(f'{BUTTON_CMD}\r\n'.encode('utf-8'))
    time.sleep(0.01)  # 等待回码返回
    response = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore').strip()
    print(f'{BUTTON_CMD} 回码: [{response}]')
    try:
        return int(response)
    except:
        return -1

def move_mouse():
    """移动鼠标"""
    ser.write(f'km.move({MOVE_DX},{MOVE_DY})\r\n'.encode('utf-8'))

# 按键状态
pressed = False

print(f'监听 {BUTTON_NAME}，按 Ctrl+C 退出...')
try:
    while True:
        state = get_button_state()
        
        if state == 1:
            if not pressed:
                print(f'{BUTTON_NAME}按下 -> 开始移动')
            pressed = True
        elif state == 0:
            if pressed:
                print(f'{BUTTON_NAME}松开 -> 停止移动')
            pressed = False
        # state == -1 保持原状态
        
        if pressed:
            move_mouse()
        
        time.sleep(MOVE_DELAY)

except KeyboardInterrupt:
    print('\n退出程序')
finally:
    ser.close()
    print('串口已关闭')