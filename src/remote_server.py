import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from flask import Flask, request, render_template_string
import pyautogui
import pyperclip
import platform
import time
import logging
import qrcode
from PIL import Image, ImageTk
import io
import pystray
from pystray import MenuItem as item
import os
import sys
import tempfile
import ctypes
import asyncio
import hashlib
import json

# CF 模式依赖（可选）
try:
    import websockets
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CF_AVAILABLE = True
except (ImportError, RuntimeError):
    CF_AVAILABLE = False

# MQTT 模式依赖（可选）
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = CF_AVAILABLE and hasattr(mqtt, 'Client')
except (ImportError, RuntimeError):
    MQTT_AVAILABLE = False

# --- 配置文件 ---
def get_config_path():
    """获取配置文件路径"""
    if IS_WINDOWS:
        config_dir = os.path.join(os.environ.get('APPDATA', ''), 'QAA-AirType')
    else:
        config_dir = os.path.join(os.path.expanduser('~'), '.config', 'qaa-airtype')
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, 'config.json')

def load_config() -> dict:
    """加载配置"""
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(config: dict):
    """保存配置"""
    try:
        config_path = get_config_path()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配置失败: {e}")

# --- 资源路径处理 ---
def get_base_path():
    """获取基础路径，支持开发环境和打包后的环境"""
    if getattr(sys, 'frozen', False):
        # 打包后的exe文件
        return os.path.dirname(sys.executable)
    else:
        # 开发环境
        return os.path.dirname(os.path.abspath(__file__))

def load_theme(theme_name=None):
    """加载主题HTML文件"""
    base_path = get_base_path()


    # 优先级1: URL参数指定的主题（exe/src 同目录、theme/ 目录）
    if theme_name and theme_name != 'default':
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base_path, f"{theme_name}.html"),
            os.path.join(base_path, "theme", f"{theme_name}.html"),
            os.path.join(repo_root, "theme", f"{theme_name}.html"),
        ]
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            candidates.insert(0, os.path.join(sys._MEIPASS, "theme", f"{theme_name}.html"))
            candidates.insert(0, os.path.join(sys._MEIPASS, f"{theme_name}.html"))
        for theme_path in candidates:
            if os.path.exists(theme_path):
                try:
                    with open(theme_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    pass

    # 优先级2: custom.html
    custom_path = os.path.join(base_path, "custom.html")
    if os.path.exists(custom_path):
        try:
            with open(custom_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass

    # 优先级3: default.html
    if getattr(sys, 'frozen', False):
        # 打包模式：从PyInstaller临时目录加载
        if hasattr(sys, '_MEIPASS'):
            default_path = os.path.join(sys._MEIPASS, "default.html")
        else:
            default_path = os.path.join(base_path, "default.html")
    else:
        # 源代码模式：从src目录加载
        default_path = os.path.join(base_path, "default.html")

    if os.path.exists(default_path):
        try:
            with open(default_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass

    # 回退到基本错误页面
    return """
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>主题加载失败</title></head>
<body><h1>主题加载失败</h1><p>请检查主题文件是否存在</p></body>
</html>"""

def get_icon_path():
    """获取图标路径，支持开发环境和打包后的环境"""
    # 如果是 PyInstaller 打包的程序
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
        if os.path.exists(icon_path):
            return icon_path

    # 开发环境或当前目录
    if os.path.exists('icon.ico'):
        return 'icon.ico'

    return None

# --- Flask 应用配置 ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def get_static_base_path():
    """获取 static 资源目录，兼容源码运行和 PyInstaller 打包"""
    candidates = []
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, 'static'))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'))
    candidates.append(os.path.join(get_base_path(), 'static'))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0]

@app.route('/static/<path:filename>')
def serve_static(filename):
    """提供 mqtt.min.js 等手机端静态资源"""
    from flask import send_file
    base = os.path.normpath(get_static_base_path())
    safe = os.path.normpath(filename).replace('\\', '/')
    if safe.startswith('..') or os.path.isabs(filename):
        return 'Not Found', 404
    full = os.path.normpath(os.path.join(base, filename))
    if not full.startswith(base) or not os.path.isfile(full):
        return 'Not Found', 404
    return send_file(full)

@app.route('/__shutdown__', methods=['POST'])
def shutdown_server():
    """仅本机调用，用于停止 Flask 服务但不退出程序"""
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return 'Forbidden', 403
    shutdown = request.environ.get('werkzeug.server.shutdown')
    if shutdown:
        shutdown()
    return 'ok'

# --- 主题系统 ---

IS_MAC = platform.system() == 'Darwin'
IS_WINDOWS = platform.system() == 'Windows'
PASTE_KEY = 'command' if IS_MAC else 'ctrl'

# Windows API 常量
if IS_WINDOWS:
    VK_SHIFT = 0x10
    VK_INSERT = 0x2D
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    MAPVK_VK_TO_VSC = 0

def send_shift_insert_windows():
    """使用 Windows API 发送 Shift+Insert 组合键（使用扫描码，兼容终端）"""
    if not IS_WINDOWS:
        return False

    try:
        user32 = ctypes.windll.user32

        # 获取扫描码（对于终端应用如 CMD/PowerShell 必须使用扫描码）
        shift_scan = user32.MapVirtualKeyW(VK_SHIFT, MAPVK_VK_TO_VSC)
        insert_scan = user32.MapVirtualKeyW(VK_INSERT, MAPVK_VK_TO_VSC)

        # 按下 Shift（使用扫描码）
        user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE, 0)
        time.sleep(0.05)

        # 按下 Insert（使用扫描码 + 扩展键标志）
        user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.02)

        # 释放 Insert（使用扫描码 + 扩展键标志）
        user32.keybd_event(VK_INSERT, insert_scan, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

        # 释放 Shift（使用扫描码）
        user32.keybd_event(VK_SHIFT, shift_scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)

        return True
    except Exception as e:
        print(f"Windows API error: {e}")
        return False


def send_enter_windows():
    """使用 Windows API 发送回车键（兼容子线程）"""
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        enter_scan = user32.MapVirtualKeyW(0x0D, MAPVK_VK_TO_VSC)
        user32.keybd_event(0x0D, enter_scan, KEYEVENTF_SCANCODE, 0)
        time.sleep(0.03)
        user32.keybd_event(0x0D, enter_scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"Windows API error: {e}")
        return False

def paste_text(text):
    """复制到剪切板并粘贴"""
    pyperclip.copy(text)
    time.sleep(0.1)
    if IS_WINDOWS:
        if not send_shift_insert_windows():
            pyautogui.hotkey('shift', 'insert')
    else:
        pyautogui.hotkey('shift', 'insert')


# --- CF 模式：cfchat 加密协议 ---
def derive_key_and_room(password: str) -> tuple:
    """从密码派生 AES 密钥和房间 ID"""
    password = password.strip() or 'noset'
    encoded = password.encode('utf-8')
    hash_bytes = hashlib.sha256(encoded).digest()
    room_id = hash_bytes.hex()
    return hash_bytes, room_id


def decrypt_message(key: bytes, iv_b64: str, data_b64: str) -> str:
    """AES-GCM 解密消息"""
    import base64
    iv = base64.b64decode(iv_b64)
    data = base64.b64decode(data_b64)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, data, None)
    return plaintext.decode('utf-8')


class CFChatClient:
    """CF 模式 WebSocket 客户端"""
    def __init__(self, worker_url: str, password: str, on_message=None, on_status=None):
        self.worker_url = worker_url.rstrip('/')
        self.password = password
        self.on_message = on_message
        self.on_status = on_status
        self.key, self.room_id = derive_key_and_room(password)
        self.ws = None
        self.running = False
        self._loop = None
        self._thread = None

    def _get_ws_url(self) -> str:
        """构建 WebSocket URL"""
        url = self.worker_url
        if url.startswith('https://'):
            url = 'wss://' + url[8:]
        elif url.startswith('http://'):
            url = 'ws://' + url[7:]
        elif not url.startswith('ws'):
            url = 'wss://' + url
        return f"{url}/ws/{self.room_id}"

    async def _connect(self):
        """连接并监听消息"""
        ws_url = self._get_ws_url()
        if self.on_status:
            self.on_status('connecting', '连接中...')

        try:
            async with websockets.connect(ws_url) as ws:
                self.ws = ws
                if self.on_status:
                    self.on_status('connected', '已连接 CF')

                while self.running:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        self._handle_message(raw)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        break

        except Exception as e:
            if self.on_status:
                self.on_status('error', f'连接失败: {e}')

        finally:
            self.ws = None
            if self.on_status and self.running:
                self.on_status('disconnected', '已断开，重连中...')

    def _handle_message(self, raw: str):
        """处理收到的消息"""
        try:
            payload = json.loads(raw)
            msg_type = payload.get('type', 'text').lower()

            if msg_type != 'text':
                return

            iv = payload.get('iv')
            data = payload.get('data')
            if not iv or not data:
                return

            text = decrypt_message(self.key, iv, data)
            if self.on_message:
                self.on_message(text)

        except Exception as e:
            print(f"消息处理错误: {e}")

    def _run_loop(self):
        """在独立线程运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        while self.running:
            try:
                self._loop.run_until_complete(self._connect())
            except Exception as e:
                print(f"连接错误: {e}")

            if self.running:
                time.sleep(2)

        self._loop.close()

    def start(self):
        """启动客户端"""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止客户端"""
        self.running = False
        if self.ws and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self._loop)
            except:
                pass


# --- MQTT 模式：复用 cfchat 的 AES-GCM 协议，走国内 Broker 中转 ---
MQTT_CHUNK_BYTES = 16 * 1024
MQTT_CHUNK_TIMEOUT = 20

def derive_mqtt_topic(password: str) -> str:
    """由共享密钥派生 MQTT 主题，避免不同用户串扰"""
    _, room_id = derive_key_and_room(password)
    return f"qaa/{room_id}/in"

def decrypt_bytes(key: bytes, iv_b64: str, data_b64: str) -> bytes:
    """AES-GCM 解密字节数据（用于长文本分片）"""
    import base64
    iv = base64.b64decode(iv_b64)
    data = base64.b64decode(data_b64)
    return AESGCM(key).decrypt(iv, data, None)

class MqttClient:
    """MQTT 接收客户端：订阅加密主题，支持长文本分片重组"""

    def __init__(self, broker_host, broker_port=1883, username=None, password=None,
                 use_tls=False, shared_key='', on_message=None, on_status=None, client_id=None):
        self.broker_host = broker_host
        self.broker_port = int(broker_port or 1883)
        self.username = username or None
        self.password = password or None
        self.use_tls = use_tls
        self.shared_key = shared_key or 'noset'
        self.client_id = client_id
        self.on_message = on_message
        self.on_status = on_status
        self.key, _ = derive_key_and_room(self.shared_key)
        self.topic = derive_mqtt_topic(self.shared_key)
        self.client = None
        self.running = False
        self._chunks = {}

    def _status(self, state, text):
        if self.on_status:
            try:
                self.on_status(state, text)
            except Exception:
                pass

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            client.subscribe(self.topic, qos=1)
            self._status('connected', '已连接 MQTT')
        else:
            self._status('error', f'MQTT 连接失败: {reason_code}')

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        if self.running:
            self._status('disconnected', 'MQTT 已断开，重连中...')

    def _emit(self, text, enter=False):
        if self.on_message:
            try:
                self.on_message(text, enter)
            except Exception as e:
                print(f"MQTT 消息处理错误: {e}")

    def _cleanup_chunks(self):
        now = time.time()
        expired = [cid for cid, item in self._chunks.items() if now - item['ts'] > MQTT_CHUNK_TIMEOUT]
        for cid in expired:
            del self._chunks[cid]

    def _handle_payload(self, raw):
        try:
            payload = json.loads(raw)
        except Exception:
            return
        try:
            msg_type = payload.get('t')
            if msg_type == 'text':
                text = decrypt_message(self.key, payload['iv'], payload['data'])
                self._emit(text, bool(payload.get('e')))
            elif msg_type == 'chunk':
                chunk_id = str(payload.get('id'))
                index = int(payload.get('i', -1))
                total = int(payload.get('n', 0))
                if not chunk_id or index < 0 or total <= 0:
                    return
                part = decrypt_bytes(self.key, payload['iv'], payload['data'])
                item = self._chunks.setdefault(chunk_id, {'n': total, 'parts': {}, 'ts': time.time()})
                item['parts'][index] = part
                item['e'] = bool(payload.get('e'))
                if len(item['parts']) == item['n']:
                    ordered = b''.join(item['parts'][i] for i in sorted(item['parts']))
                    del self._chunks[chunk_id]
                    self._emit(ordered.decode('utf-8'), bool(item.get('e')))
                self._cleanup_chunks()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"MQTT payload 处理异常: {e}")

    def _on_message(self, client, userdata, msg):
        self._handle_payload(msg.payload)

    def start(self):
        if not MQTT_AVAILABLE:
            self._status('error', 'MQTT 模式需要依赖: pip install paho-mqtt cryptography')
            return False
        if self.running:
            return True
        self.running = True
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id or 'qaa-airtype-pc')
            if self.username:
                self.client.username_pw_set(self.username, self.password)
            if self.use_tls:
                self.client.tls_set()
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=30)
            self.client.loop_start()
            self._status('connecting', '正在连接 MQTT Broker...')
            return True
        except Exception as e:
            self.running = False
            self._status('error', f'MQTT 启动失败: {e}')
            return False

    def stop(self):
        self.running = False
        if self.client:
            try:
                self.client.disconnect()
                self.client.loop_stop()
            except Exception:
                pass
            self.client = None


@app.route('/')
def index():
    theme = request.args.get('theme')
    return load_theme(theme)

@app.route('/type', methods=['POST'])
def type_text():
    try:
        data = request.get_json()
        text = data.get('text', '')
        if text:
            pyperclip.copy(text)
            time.sleep(0.1)

            # 使用 Shift+Insert 粘贴（兼容所有应用，包括终端）
            if IS_WINDOWS:
                # Windows: 使用 Windows API 直接发送键盘事件（解决子线程问题）
                success = send_shift_insert_windows()
                if not success:
                    # 如果 Windows API 失败，回退到 pyautogui
                    pyautogui.hotkey('shift', 'insert')
            else:
                # Mac/Linux: 使用 pyautogui
                pyautogui.hotkey('shift', 'insert')

            return {'success': True}
    except Exception as e:
        print(f"Error in type_text: {e}")
        pass
    return {'success': False}

def get_host_ip():
    """获取主要的本机 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_all_ips():
    """获取所有可用的本机 IP 地址"""
    ips = []
    try:
        # 获取主机名
        hostname = socket.gethostname()
        # 获取所有 IP 地址
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = addr[4][0]
            # 只保留 IPv4 地址，排除回环地址
            if ':' not in ip and ip != '127.0.0.1':
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass

    # 如果没有找到任何 IP，添加默认值
    if not ips:
        ips.append('127.0.0.1')

    # IP 分类排序
    # 优先级：192.168.x.x > 10.x.x.x > 其他 > 虚拟网卡
    priority_192 = []  # 192.168.x.x (家庭/办公网络)
    priority_10 = []   # 10.x.x.x (企业网络)
    other_ips = []     # 其他真实 IP
    virtual_ips = []   # 虚拟网卡 IP

    for ip in ips:
        if ip.startswith('192.168.'):
            priority_192.append(ip)
        elif ip.startswith('10.'):
            priority_10.append(ip)
        elif ip.startswith('172.'):
            # 检查是否是虚拟网卡
            parts = ip.split('.')
            if len(parts) >= 2:
                second = int(parts[1])
                # Docker: 172.17.x.x, 172.18.x.x
                # Windows 虚拟网卡: 172.16.x.x
                # 私有网络范围: 172.16-31.x.x
                if 16 <= second <= 31:
                    virtual_ips.append(ip)
                else:
                    other_ips.append(ip)
        elif ip.startswith('198.18.'):
            # Clash 等代理工具虚拟网卡
            virtual_ips.append(ip)
        else:
            other_ips.append(ip)

    # 重新组合：优先级从高到低
    ips = priority_192 + priority_10 + other_ips + virtual_ips

    # 将主要 IP 移到对应分类的第一位（保持分类顺序）
    main_ip = get_host_ip()
    if main_ip in ips:
        ips.remove(main_ip)
        # 根据主要 IP 的类型，插入到对应分类的开头
        if main_ip.startswith('192.168.'):
            insert_pos = 0
        elif main_ip.startswith('10.'):
            insert_pos = len(priority_192)
        else:
            insert_pos = len(priority_192) + len(priority_10)
        ips.insert(insert_pos, main_ip)

    # 在最前面添加 0.0.0.0（监听所有网卡）
    ips.insert(0, '0.0.0.0 (所有网卡)')

    return ips

# --- GUI 主程序 ---
class ServerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("QAA AirType")
        # 增加高度以容纳二维码
        self.root.geometry("512x640")
        self.root.geometry("512x760")
        self.root.resizable(True, True)
        self.root.minsize(380, 480)  # 最小尺寸

        # 绑定窗口关闭事件（正常退出）
        self.root.protocol('WM_DELETE_WINDOW', self.quit_app)

        # 设置窗口图标
        try:
            icon_path = get_icon_path()
            if icon_path:
                self.root.iconbitmap(icon_path)
        except Exception as e:
            pass

        # 系统托盘图标
        self.tray_icon = None
        self.create_tray_icon()

        # 居中屏幕
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 512) // 2
        y = (screen_height - 640) // 2
        self.root.geometry(f"512x640+{x}+{y}")
        self.root.geometry(f"512x760+{x}+{y}")

        self.all_ips = get_all_ips()
        self.ip_var = tk.StringVar(value=self.all_ips[0])
        self.is_running = False
        self.cf_client = None  # CF 模式客户端
        self.cf_mode = False   # 是否为 CF 模式
        self.mqtt_client = None  # MQTT 模式客户端
        self.mqtt_mode = False   # 是否为 MQTT 模式

        # 加载配置
        self.config = load_config()
        saved_mode = self.config.get('mode', 'lan')  # lan 或 cf
        saved_port = self.config.get('port', '5000')
        saved_ip = self.config.get('ip', '')
        saved_cf_url = self.config.get('cf_url', '')
        saved_cf_key = self.config.get('cf_key', '')
        saved_mqtt_host = self.config.get('mqtt_host', 'broker.emqx.io')
        saved_mqtt_port = self.config.get('mqtt_port', '1883')
        saved_mqtt_user = self.config.get('mqtt_user', '')
        saved_mqtt_pass = self.config.get('mqtt_pass', '')
        saved_mqtt_key = self.config.get('mqtt_key', '')
        saved_mqtt_page = self.config.get('mqtt_page_url', '')
        saved_mqtt_tls = self.config.get('mqtt_tls', False)

        self.all_ips.append('Cloudflare Chat Workers')
        self.all_ips.append('MQTT 中转')
        # 在 IP 列表末尾添加 MQTT / CF 模式选项

        # 主容器
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(expand=True, fill='both')

        # 模式/IP 选择
        tk.Label(main_frame, text="连接模式:", font=("Arial", 10, "bold")).pack(anchor='w')
        self.ip_combo = ttk.Combobox(main_frame, textvariable=self.ip_var,
                                     values=self.all_ips, font=("Arial", 10), state='readonly')
        self.ip_combo.pack(fill='x', pady=(0, 10))
        self.ip_combo.bind('<<ComboboxSelected>>', self.on_mode_changed)

        # --- 局域网模式控件 ---
        self.lan_frame = tk.Frame(main_frame)
        self.lan_frame.pack(fill='x', pady=(0, 10))

        # 端口输入（标签和输入框在同一行）
        port_row = tk.Frame(self.lan_frame)
        port_row.pack(fill='x', pady=(0, 5))
        tk.Label(port_row, text="端口:", font=("Arial", 10, "bold"), width=10, anchor='w').pack(side='left')
        self.port_var = tk.StringVar(value=saved_port)
        self.port_entry = tk.Entry(port_row, textvariable=self.port_var, font=("Arial", 10))
        self.port_entry.pack(side='left', fill='x', expand=True)

        # 主题名称输入（标签和输入框在同一行）
        theme_row = tk.Frame(self.lan_frame)
        theme_row.pack(fill='x')
        tk.Label(theme_row, text="主题名称:", font=("Arial", 10, "bold"), width=10, anchor='w').pack(side='left')
        self.theme_var = tk.StringVar(value='')
        self.theme_entry = tk.Entry(theme_row, textvariable=self.theme_var, font=("Arial", 10))
        self.theme_entry.pack(side='left', fill='x', expand=True)
        tk.Label(theme_row, text="如: xxx.html", font=("Arial", 8), fg="#888").pack(side='left', padx=(5, 0))

        # --- CF 模式控件 ---
        self.cf_frame = tk.Frame(main_frame)
        # 默认隐藏，选择 CF 模式时显示

        tk.Label(self.cf_frame, text="CF Worker 地址:", font=("Arial", 10, "bold")).pack(anchor='w')
        self.cf_url_var = tk.StringVar(value=saved_cf_url)
        self.cf_url_entry = tk.Entry(self.cf_frame, textvariable=self.cf_url_var, font=("Arial", 10))
        self.cf_url_entry.pack(fill='x', pady=(0, 10))

        tk.Label(self.cf_frame, text="共享密钥:", font=("Arial", 10, "bold")).pack(anchor='w')
        self.cf_key_var = tk.StringVar(value=saved_cf_key)
        self.cf_key_entry = tk.Entry(self.cf_frame, textvariable=self.cf_key_var, font=("Arial", 10), show="*")
        self.cf_key_entry.pack(fill='x')

        # --- MQTT 模式控件 ---
        self.mqtt_frame = tk.Frame(main_frame)

        def mqtt_row(label_text, var, show=None):
            row = tk.Frame(self.mqtt_frame)
            row.pack(fill='x', pady=(0, 5))
            tk.Label(row, text=label_text, font=("Arial", 10, "bold"), width=10, anchor='w').pack(side='left')
            entry = tk.Entry(row, textvariable=var, font=("Arial", 10), show=show)
            entry.pack(side='left', fill='x', expand=True)
            return entry

        self.mqtt_host_var = tk.StringVar(value=saved_mqtt_host)
        self.mqtt_host_entry = mqtt_row("Broker 地址:", self.mqtt_host_var)

        port_tls_row = tk.Frame(self.mqtt_frame)
        port_tls_row.pack(fill='x', pady=(0, 5))
        tk.Label(port_tls_row, text="端口:", font=("Arial", 10, "bold"), width=10, anchor='w').pack(side='left')
        self.mqtt_port_var = tk.StringVar(value=saved_mqtt_port)
        self.mqtt_port_entry = tk.Entry(port_tls_row, textvariable=self.mqtt_port_var, font=("Arial", 10), width=8)
        self.mqtt_port_entry.pack(side='left')
        self.mqtt_tls_var = tk.BooleanVar(value=bool(saved_mqtt_tls))
        tk.Checkbutton(port_tls_row, text="TLS", variable=self.mqtt_tls_var, font=("Arial", 9)).pack(side='left', padx=(8, 0))

        self.mqtt_user_var = tk.StringVar(value=saved_mqtt_user)
        self.mqtt_user_entry = mqtt_row("用户名:", self.mqtt_user_var)
        self.mqtt_pass_var = tk.StringVar(value=saved_mqtt_pass)
        self.mqtt_pass_entry = mqtt_row("密码:", self.mqtt_pass_var, show="*")
        self.mqtt_key_var = tk.StringVar(value=saved_mqtt_key)
        self.mqtt_key_entry = mqtt_row("共享密钥:", self.mqtt_key_var, show="*")
        self.mqtt_page_var = tk.StringVar(value=saved_mqtt_page)
        self.mqtt_page_entry = mqtt_row("手机页面:", self.mqtt_page_var)
        tk.Label(self.mqtt_frame, text="手机页面地址用于二维码，留空则用本机地址", font=("Arial", 8), fg="#888").pack(anchor='w')

        # 恢复保存的模式
        if saved_mode == 'mqtt':
            self.ip_var.set('MQTT 中转')
            self.lan_frame.pack_forget()
            self.mqtt_frame.pack(fill='x', pady=(0, 10))
        elif saved_mode == 'cf':
            self.ip_var.set('Cloudflare Chat Workers')
            self.lan_frame.pack_forget()
            self.cf_frame.pack(fill='x', pady=(0, 10))
        elif saved_ip and saved_ip in self.all_ips:
            self.ip_var.set(saved_ip)

        # 按钮组
        # 自启动与自动连接选项
        self.options_frame = tk.Frame(main_frame)
        self.options_frame.pack(fill='x', pady=(0, 10))
        self.autostart_var = tk.BooleanVar(value=bool(self.config.get('autostart', False)))
        self.auto_connect_var = tk.BooleanVar(value=bool(self.config.get('auto_connect', True)))
        self.autostart_check = tk.Checkbutton(self.options_frame, text="开机自启动", variable=self.autostart_var,
                                              command=self.on_autostart_toggle, font=("Arial", 9))
        self.autostart_check.pack(side='left')
        self.auto_connect_check = tk.Checkbutton(self.options_frame, text="启动后自动连接", variable=self.auto_connect_var,
                                               command=self.on_auto_connect_toggle, font=("Arial", 9))
        self.auto_connect_check.pack(side='left', padx=(10, 0))
        self.button_frame = tk.Frame(main_frame)
        self.button_frame.pack(fill='x', pady=(0, 20))

        # 启动按钮
        self.btn_start = tk.Button(self.button_frame, text="启动服务", command=self.toggle_server,
                                   bg="#007AFF", fg="white", font=("Arial", 12, "bold"),
                                   relief="flat", pady=8, cursor="hand2")
        self.btn_start.pack(side='left', fill='x', expand=True, padx=(0, 5))

        # 最小化到托盘按钮
        self.btn_minimize = tk.Button(self.button_frame, text="🔽", command=self.hide_window,
                                      bg="#8e8e93", fg="white", font=("Arial", 12, "bold"),
                                      relief="flat", pady=8, cursor="hand2", width=3)
        self.btn_minimize.pack(side='right')

        # 停止按钮：只停止服务，不退出程序
        self.btn_stop = tk.Button(self.button_frame, text="停止", command=self.stop_service,
                                 bg="#ff9500", fg="white", font=("Arial", 12, "bold"),
                                 relief="flat", pady=8, cursor="hand2", width=5)
        self.btn_stop.pack(side='right', padx=(5, 0))

        # 退出按钮：停止服务后仍可继续修改配置，需要彻底退出时使用

        # 二维码显示区域
        self.qr_label = tk.Label(main_frame, text="",
                                 bg="#e6e6e6", fg="#333", width=30, height=12, font=("Arial", 9))
        self.qr_label.pack(pady=5)

        # 初始显示所有可用地址
        self.show_all_ips_display(5000)

        # 底部链接提示
        self.url_label = tk.Label(main_frame, text="", fg="blue", font=("Arial", 9, "underline"), cursor="hand2")
        self.url_label.pack(pady=(5, 0))
        self.url_label.bind("<Button-1>", self.open_browser) # 点击用浏览器打开

        # 提示信息
        self.tip_label = tk.Label(main_frame, text="", fg="#888", font=("Arial", 8))
        self.tip_label.pack(pady=(5, 0))

        # 启动时同步一次自启动注册表，并在需要时自动连接上次配置
        self.apply_autostart()
        if self.auto_connect_var.get():
            self.root.after(500, self.auto_connect_last)

    def show_all_ips_display(self, port, started=False):
        """显示所有可用 IP 地址列表"""
        # 过滤掉 0.0.0.0 和 Cloudflare 选项
        all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare') and not ip.startswith('MQTT')]
        ip_list = '\n'.join([f"http://{ip}:{port}" for ip in all_ips])

        if started:
            # 已启动状态
            title = "监听所有网卡"
            tip = "💡 切换到具体 IP 可显示二维码"
        else:
            # 未启动状态
            title = "可用地址"
            tip = "💡 点击启动服务开始使用"

        self.qr_label.config(
            text=f"{title}\n\n{ip_list}\n\n{tip}",
            image='',
            bg="#e6e6e6",
            fg="#333",
            font=("Arial", 9)
        )

    def run_flask(self, host, port):
        try:
            app.run(host=host, port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Error: {e}")

    def generate_qr(self, url, target_size=200):
        """生成二维码图像，自动调整大小以适应目标尺寸"""
        # 生成二维码图像
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        # 调整图像大小以适应显示区域
        img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)

        # 转换为 Tkinter 可用的格式
        img_tk = ImageTk.PhotoImage(img)
        return img_tk

    def _autostart_command(self):
        """构造开机自启动命令行，后台最小化启动"""
        if getattr(sys, 'frozen', False):
            return f'"{sys.executable}" --minimized'
        pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        script = os.path.abspath(__file__)
        return f'"{pythonw}" "{script}" --minimized'

    def set_autostart(self, enabled):
        """写入或删除 Windows 开机自启动注册表项"""
        if not IS_WINDOWS:
            return
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r'Software\Microsoft\Windows\CurrentVersion\Run',
                                 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, 'QAA-AirType', 0, winreg.REG_SZ, self._autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, 'QAA-AirType')
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"自启动设置失败: {e}")

    def apply_autostart(self):
        """启动时同步一次自启动状态"""
        self.set_autostart(bool(self.autostart_var.get()))

    def on_autostart_toggle(self):
        self.config['autostart'] = bool(self.autostart_var.get())
        save_config(self.config)
        self.set_autostart(self.config['autostart'])

    def on_auto_connect_toggle(self):
        self.config['auto_connect'] = bool(self.auto_connect_var.get())
        save_config(self.config)

    def auto_connect_last(self):
        """启动后自动连接上一次使用的模式"""
        mode = self.config.get('mode', 'lan')
        if mode == 'mqtt':
            if MQTT_AVAILABLE and self.mqtt_host_var.get().strip() and self.mqtt_key_var.get():
                self.start_mqtt_mode()
            else:
                self.tip_label.config(text="上次为 MQTT 模式，配置不完整，未自动连接", fg="#888")
        elif mode == 'cf':
            if CF_AVAILABLE and self.cf_url_var.get().strip():
                self.start_cf_mode()
            else:
                self.tip_label.config(text="上次为 CF 模式，配置不完整，未自动连接", fg="#888")
        elif mode == 'lan':
            if self.port_var.get().strip().isdigit():
                self.start_lan_mode()
            else:
                self.tip_label.config(text="上次为局域网模式，端口无效，未自动连接", fg="#888")

    def stop_service(self):
        """停止当前服务，但不退出程序"""
        if self.mqtt_client:
            self.mqtt_client.stop()
            self.mqtt_client = None
        if self.cf_client:
            self.cf_client.stop()
            self.cf_client = None
        if not self.cf_mode and not self.mqtt_mode:
            # 局域网 Flask 服务通过本机 shutdown 接口停止
            try:
                import urllib.request
                port = self.port_var.get().strip() or '5000'
                urllib.request.urlopen(f'http://127.0.0.1:{port}/__shutdown__', data=b'', timeout=2)
            except Exception:
                pass
        self.is_running = False
        self.cf_mode = False
        self.mqtt_mode = False
        self.btn_start.config(text="启动服务", bg="#007AFF", state='normal')
        self.port_entry.config(state='normal', bg='white')
        self.ip_combo.config(state='readonly')
        for entry in (self.mqtt_host_entry, self.mqtt_port_entry, self.mqtt_user_entry,
                      self.mqtt_pass_entry, self.mqtt_key_entry, self.mqtt_page_entry):
            entry.config(state='normal', bg='white')
        self.cf_url_entry.config(state='normal', bg='white')
        self.cf_key_entry.config(state='normal', bg='white')
        self.show_all_ips_display(5000)
        self.url_label.config(text="")
        self.current_url = None
        self.tip_label.config(text="服务已停止，可修改配置后重新启动", fg="#888")

    def toggle_server(self):
        if self.is_running:
            # 停止服务并退出
            self.quit_app()
            return

        selected = self.ip_var.get()

        # 判断模式并启动
        if selected == 'MQTT 中转':
            # 保存 MQTT 配置
            self.config['mode'] = 'mqtt'
            self.config['mqtt_host'] = self.mqtt_host_var.get().strip()
            self.config['mqtt_port'] = self.mqtt_port_var.get().strip()
            self.config['mqtt_user'] = self.mqtt_user_var.get().strip()
            self.config['mqtt_pass'] = self.mqtt_pass_var.get()
            self.config['mqtt_key'] = self.mqtt_key_var.get()
            self.config['mqtt_page_url'] = self.mqtt_page_var.get().strip()
            self.config['mqtt_tls'] = bool(self.mqtt_tls_var.get())
            save_config(self.config)
            self.start_mqtt_mode()
        elif selected == 'Cloudflare Chat Workers':
            # 保存 CF 配置
            self.config['mode'] = 'cf'
            self.config['cf_url'] = self.cf_url_var.get()
            self.config['cf_key'] = self.cf_key_var.get()
            save_config(self.config)
            self.start_cf_mode()
        else:
            # 保存局域网配置
            self.config['mode'] = 'lan'
            self.config['port'] = self.port_var.get()
            self.config['ip'] = selected
            save_config(self.config)
            self.start_lan_mode()

    def parse_cf_config(self, config: str) -> tuple:
        """解析 CF 配置：key@url（保留兼容）"""
        if '@' not in config:
            return '', config
        at_pos = config.find('@')
        key = config[:at_pos]
        url = config[at_pos + 1:]
        return key, url

    def start_cf_mode(self):
        """启动 CF 模式"""
        if not CF_AVAILABLE:
            messagebox.showerror("错误", "CF 模式需要安装依赖:\npip install websockets cryptography")
            return

        url = self.cf_url_var.get().strip()
        key = self.cf_key_var.get()

        if not url:
            messagebox.showerror("错误", "请输入 CF Worker 地址")
            return

        # 确保 URL 有协议
        if not url.startswith('http'):
            url = 'https://' + url

        self.cf_mode = True
        self.cf_url = url
        self.cf_key = key

        # 创建 CF 客户端
        self.cf_client = CFChatClient(
            worker_url=url,
            password=key,
            on_message=self.on_cf_message,
            on_status=self.on_cf_status
        )
        self.cf_client.start()

        self.is_running = True
        self.btn_start.config(text="停止服务并退出", bg="#ff3b30")
        self.cf_url_entry.config(state='disabled', bg="#f0f0f0")
        self.cf_key_entry.config(state='disabled', bg="#f0f0f0")
        self.ip_combo.config(state='disabled')

        # 显示 cfchat URL 的二维码
        try:
            qr_size = min(self.root.winfo_width() - 80, 250)
            self.qr_img = self.generate_qr(url, target_size=qr_size)
            self.qr_label.config(image=self.qr_img, width=qr_size, height=qr_size,
                                bg="white", text='', font=("Arial", 10))
        except Exception as e:
            self.qr_label.config(text=f"二维码生成失败\n{e}")

        self.url_label.config(text=url)
        self.current_url = url
        self.tip_label.config(text="CF 模式：手机访问上方链接发送消息")

    def start_mqtt_mode(self):
        """启动 MQTT 模式"""
        if not MQTT_AVAILABLE:
            messagebox.showerror("错误", "MQTT 模式需要安装依赖:\npip install paho-mqtt cryptography")
            return

        host = self.mqtt_host_var.get().strip()
        port = self.mqtt_port_var.get().strip() or '1883'
        key = self.mqtt_key_var.get()
        username = self.mqtt_user_var.get().strip()
        password = self.mqtt_pass_var.get()

        if not host:
            messagebox.showerror("错误", "请输入 MQTT Broker 地址")
            return
        if not key:
            messagebox.showerror("错误", "请输入共享密钥")
            return

        self.mqtt_mode = True
        self.mqtt_client = MqttClient(
            broker_host=host,
            broker_port=port,
            username=username or None,
            password=password or None,
            use_tls=bool(self.mqtt_tls_var.get()),
            shared_key=key,
            on_message=self.on_mqtt_message,
            on_status=self.on_mqtt_status
        )
        if not self.mqtt_client.start():
            self.mqtt_mode = False
            return

        self.is_running = True
        self.btn_start.config(text="停止服务并退出", bg="#ff3b30")
        self.ip_combo.config(state='disabled')
        for entry in (self.mqtt_host_entry, self.mqtt_port_entry, self.mqtt_user_entry,
                      self.mqtt_pass_entry, self.mqtt_key_entry, self.mqtt_page_entry):
            entry.config(state='disabled', bg="#f0f0f0")

        from urllib.parse import quote
        tls_flag = 1 if self.mqtt_tls_var.get() else 0
        params = (f"theme=mqtt&k={quote(key)}&h={quote(host)}&p={quote(port)}"
                  f"&u={quote(username)}&w={quote(password)}&tls={tls_flag}")
        page_url = self.mqtt_page_var.get().strip()
        if not page_url:
            page_url = f"http://{get_host_ip()}:{self.port_var.get() or 5000}/"
        sep = '&' if '?' in page_url else '?'
        full_url = f"{page_url}{sep}{params}"
        try:
            qr_size = min(self.root.winfo_width() - 80, 250)
            self.qr_img = self.generate_qr(full_url, target_size=qr_size)
            self.qr_label.config(image=self.qr_img, width=qr_size, height=qr_size,
                                bg="white", text='', font=("Arial", 10))
        except Exception as e:
            self.qr_label.config(text=f"二维码生成失败\n{e}")

        self.url_label.config(text=full_url)
        self.current_url = full_url
        self.tip_label.config(text="MQTT 模式：手机打开页面后在任意网络使用")

    def on_mqtt_message(self, text, enter=False):
        """MQTT 模式收到消息回调"""
        self.root.after(0, lambda: self._handle_mqtt_message(text, enter))

    def _handle_mqtt_message(self, text, enter=False):
        paste_text(text)
        if enter:
            send_enter_windows()
        display = text[:30] + '...' if len(text) > 30 else text
        self.tip_label.config(text=f"已粘贴: {display}", fg="#34c759")

    def on_mqtt_status(self, state, text):
        """MQTT 状态回调"""
        self.root.after(0, lambda: self._update_mqtt_status(state, text))

    def _update_mqtt_status(self, state, text):
        colors = {
            'connected': '#34c759',
            'connecting': '#f59e0b',
            'disconnected': '#888',
            'error': '#ff3b30'
        }
        self.tip_label.config(text=text, fg=colors.get(state, '#888'))

    def start_lan_mode(self):
        """启动局域网模式"""
        port_str = self.port_var.get().strip()

        if not port_str.isdigit():
            messagebox.showerror("错误", "端口必须是数字")
            return

        self.cf_mode = False
        port = int(port_str)
        host_ip = self.ip_var.get()

        # 确定监听地址
        if host_ip.startswith('0.0.0.0'):
            listen_host = '0.0.0.0'
        else:
            listen_host = host_ip

        # 启动 Flask 线程
        t = threading.Thread(target=self.run_flask, args=(listen_host, port), daemon=True)
        t.start()

        self.is_running = True
        self.listen_on_all = host_ip.startswith('0.0.0.0')
        self.btn_start.config(text="停止服务并退出", state='normal', bg="#ff3b30")
        self.port_entry.config(state='disabled', bg="#f0f0f0")

        if not self.listen_on_all:
            self.ip_combo.config(state='disabled')

        if host_ip.startswith('0.0.0.0'):
            self.show_all_ips_display(port, started=True)
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare') and not ip.startswith('MQTT')]
            theme = self.theme_var.get().strip()
            theme_param = f"?theme={theme}" if theme else ""
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}{theme_param}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            theme = self.theme_var.get().strip()
            theme_param = f"?theme={theme}" if theme else ""
            url = f"http://{host_ip}:{port}{theme_param}"
            try:
                qr_size = min(self.root.winfo_width() - 80, 250)
                self.qr_img = self.generate_qr(url, target_size=qr_size)
                self.qr_label.config(image=self.qr_img, width=qr_size, height=qr_size,
                                    bg="white", text='', font=("Arial", 10))
            except Exception as e:
                self.qr_label.config(text=f"二维码生成失败\n{e}")

            self.url_label.config(text=url)
            self.current_url = url
            self.tip_label.config(text="提示：如无法访问，请切换 IP 或端口重新扫码")

    def on_cf_message(self, text: str):
        """CF 模式收到消息回调"""
        self.root.after(0, lambda: self._handle_cf_message(text))

    def _handle_cf_message(self, text: str):
        """处理 CF 消息并粘贴"""
        paste_text(text)
        # 更新提示
        display = text[:30] + '...' if len(text) > 30 else text
        self.tip_label.config(text=f"已粘贴: {display}")

    def on_cf_status(self, state: str, text: str):
        """CF 模式状态回调"""
        self.root.after(0, lambda: self._update_cf_status(state, text))

    def _update_cf_status(self, state: str, text: str):
        """更新 CF 状态显示"""
        colors = {
            'connected': '#34c759',
            'connecting': '#f59e0b',
            'disconnected': '#888',
            'error': '#ff3b30'
        }
        self.tip_label.config(text=text, fg=colors.get(state, '#888'))

    def on_mode_changed(self, event=None):
        """模式/IP 改变时切换界面"""
        selected = self.ip_var.get()

        if selected == 'MQTT 中转':
            # 切换到 MQTT 模式界面
            self.lan_frame.pack_forget()
            self.cf_frame.pack_forget()
            self.mqtt_frame.pack(fill='x', pady=(0, 10), before=self.button_frame)
        elif selected == 'Cloudflare Chat Workers':
            # 切换到 CF 模式界面
            self.lan_frame.pack_forget()
            self.mqtt_frame.pack_forget()
            self.cf_frame.pack(fill='x', pady=(0, 10), before=self.button_frame)
        else:
            # 切换到局域网模式界面
            self.cf_frame.pack_forget()
            self.mqtt_frame.pack_forget()
            self.lan_frame.pack(fill='x', pady=(0, 10), before=self.button_frame)

            # 如果运行中且是 0.0.0.0 模式，更新二维码
            if self.is_running and hasattr(self, 'listen_on_all') and self.listen_on_all:
                self._update_lan_qr()

    def _update_lan_qr(self):
        """更新局域网模式二维码"""
        host_ip = self.ip_var.get()
        port = int(self.port_var.get())

        if host_ip.startswith('0.0.0.0'):
            self.show_all_ips_display(port, started=True)
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare') and not ip.startswith('MQTT')]
            theme = self.theme_var.get().strip()
            theme_param = f"?theme={theme}" if theme else ""
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}{theme_param}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            theme = self.theme_var.get().strip()
            theme_param = f"?theme={theme}" if theme else ""
            url = f"http://{host_ip}:{port}{theme_param}"
            try:
                qr_size = min(self.root.winfo_width() - 80, 250)
                self.qr_img = self.generate_qr(url, target_size=qr_size)
                self.qr_label.config(image=self.qr_img, width=qr_size, height=qr_size,
                                    bg="white", text='', font=("Arial", 10))
            except Exception as e:
                self.qr_label.config(text=f"二维码生成失败\n{e}")

            self.url_label.config(text=url)
            self.current_url = url
            self.tip_label.config(text="提示：如无法访问，请切换 IP 重新扫码")

    def create_tray_icon(self):
        """创建系统托盘图标"""
        # 尝试加载 icon.ico，保持与窗口图标一致
        try:
            icon_path = get_icon_path()
            if icon_path:
                icon_image = Image.open(icon_path)
            elif os.path.exists('icon.png'):
                icon_image = Image.open('icon.png')
            else:
                # 创建一个简单的蓝色图标
                icon_image = Image.new('RGB', (64, 64), color='#007AFF')
        except Exception:
            # 如果加载失败，创建简单图标
            icon_image = Image.new('RGB', (64, 64), color='#007AFF')

        # 创建托盘菜单
        menu = pystray.Menu(
            item('显示窗口', self.show_window),
            item('退出', self.quit_app)
        )

        # 创建托盘图标
        self.tray_icon = pystray.Icon("QAA-AirType", icon_image, "QAA AirType", menu)

        # 在后台线程运行托盘图标
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        """隐藏窗口到系统托盘"""
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        """显示窗口"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, icon=None, item=None):
        """退出应用"""
        # 停止 CF 客户端
        if self.cf_client:
            self.cf_client.stop()
            self.cf_client = None
        # 停止 MQTT 客户端
        if self.mqtt_client:
            self.mqtt_client.stop()
            self.mqtt_client = None
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()

    def open_browser(self, event):
        if hasattr(self, 'current_url'):
            import webbrowser
            webbrowser.open(self.current_url)

if __name__ == '__main__':
    root = tk.Tk()
    app_gui = ServerApp(root)
    if '--minimized' in sys.argv:
        app_gui.hide_window()
    root.mainloop()
