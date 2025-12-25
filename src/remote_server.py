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
except ImportError:
    CF_AVAILABLE = False

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

# --- HTML 模板 (保持之前的历史记录功能) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>无线键盘</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
            padding: 20px; 
            text-align: center; 
            background-color: #f5f5f7; 
            color: #333;
        }
        h2 { margin-bottom: 20px; font-weight: 600; }
        .input-group { margin-bottom: 15px; }
        input[type="text"] {
            width: 100%; padding: 15px; font-size: 16px; border-radius: 12px;
            border: 1px solid #d1d1d6; box-sizing: border-box; outline: none;
            background: #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: border-color 0.2s;
        }
        input[type="text"]:focus { border-color: #007AFF; }
        .button-group { display: flex; gap: 10px; margin-bottom: 15px; }
        button {
            flex: 1; padding: 15px; font-size: 18px; color: white;
            border: none; border-radius: 12px; cursor: pointer; font-weight: 600;
            transition: background-color 0.1s, transform 0.1s;
        }
        button#sendBtn {
            background-color: #007AFF;
            box-shadow: 0 4px 6px rgba(0,122,255,0.2);
        }
        button#sendBtn:active { background-color: #0056b3; transform: scale(0.98); }
        button#clearBtn {
            background-color: #8e8e93;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        button#clearBtn:active { background-color: #636366; transform: scale(0.98); }
        #status { margin-top: 10px; height: 20px; font-size: 14px; color: #34c759; font-weight: 500;}
        .history-container { margin-top: 30px; text-align: left; }
        .history-header { 
            font-size: 14px; color: #888; margin-bottom: 10px; 
            display: flex; justify-content: space-between; align-items: center;
        }
        .clear-btn { color: #ff3b30; cursor: pointer; font-size: 12px; }
        .history-list { list-style: none; padding: 0; margin: 0; }
        .history-item {
            background: #fff; padding: 12px; margin-bottom: 8px; border-radius: 8px;
            border: 1px solid #e5e5ea; cursor: pointer;
            display: flex; align-items: center; justify-content: space-between;
            transition: background 0.1s;
        }
        .history-item:active { background: #f0f0f0; }
        .history-text { 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; 
            max-width: 85%; font-size: 14px;
        }
        .history-arrow { color: #c7c7cc; font-size: 18px; }
    </style>
</head>
<body>
    <h2>电脑远程输入板</h2>
    <div class="input-group">
        <input type="text" id="textInput" placeholder="输入文字..." autofocus autocomplete="off">
    </div>
    <div class="button-group">
        <button id="clearBtn" onclick="handleClear()">清空</button>
        <button id="sendBtn" onclick="handleSend()">发送 (Ent)</button>
    </div>
    <div id="status"></div>
    <div class="history-container">
        <div class="history-header">
            <span>最近记录 (点击重发)</span>
            <span class="clear-btn" onclick="clearHistory()">清空</span>
        </div>
        <ul id="historyList" class="history-list"></ul>
    </div>
    <script>
        const input = document.getElementById('textInput');
        const status = document.getElementById('status');
        const historyList = document.getElementById('historyList');
        const MAX_HISTORY = 10;

        window.onload = function() { renderHistory(); }

        // 回车发送
        input.addEventListener("keypress", function(event) {
            if (event.key === "Enter") { event.preventDefault(); handleSend(); }
        });

        // 点击页面任意位置聚焦输入框（除了按钮和历史记录）
        document.body.addEventListener('click', function(event) {
            const target = event.target;
            // 如果点击的不是按钮、历史记录项、清空按钮，则聚焦输入框
            if (!target.closest('button') &&
                !target.closest('.history-item') &&
                !target.closest('.clear-btn') &&
                target !== input) {
                input.focus();
            }
        });
        function handleSend() {
            const text = input.value.trim();
            if (!text) return;
            saveToHistory(text);
            sendRequest(text);
        }
        function handleClear() {
            input.value = '';
            input.focus();
        }
        function sendRequest(text) {
            status.innerText = "发送中...";
            status.style.color = "#888";
            fetch('/type', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.innerText = "✓ 已发送";
                    status.style.color = "#34c759";
                    input.value = ''; 
                    setTimeout(() => status.innerText = "", 1500);
                } else { throw new Error("Server error"); }
            })
            .catch(err => {
                status.innerText = "✕ 发送失败";
                status.style.color = "#ff3b30";
            });
        }
        function getHistory() {
            const stored = localStorage.getItem('typeHistory');
            return stored ? JSON.parse(stored) : [];
        }
        function saveToHistory(text) {
            let history = getHistory();
            history = history.filter(item => item !== text);
            history.unshift(text);
            if (history.length > MAX_HISTORY) { history = history.slice(0, MAX_HISTORY); }
            localStorage.setItem('typeHistory', JSON.stringify(history));
            renderHistory();
        }
        function renderHistory() {
            const history = getHistory();
            historyList.innerHTML = '';
            history.forEach(text => {
                const li = document.createElement('li');
                li.className = 'history-item';
                li.onclick = () => { input.value = text; handleSend(); };
                li.innerHTML = `<span class="history-text">${escapeHtml(text)}</span><span class="history-arrow">⤶</span>`;
                historyList.appendChild(li);
            });
        }
        function clearHistory() { localStorage.removeItem('typeHistory'); renderHistory(); }
        function escapeHtml(text) {
            const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
            return text.replace(/[&<>"']/g, function(m) { return map[m]; });
        }
    </script>
</body>
</html>
"""

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


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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

        self.all_ips = get_all_ips()
        self.ip_var = tk.StringVar(value=self.all_ips[0])
        self.is_running = False
        self.cf_client = None  # CF 模式客户端
        self.cf_mode = False   # 是否为 CF 模式

        # 加载配置
        self.config = load_config()
        saved_mode = self.config.get('mode', 'lan')  # lan 或 cf
        saved_port = self.config.get('port', '5000')
        saved_ip = self.config.get('ip', '')
        saved_cf_url = self.config.get('cf_url', '')
        saved_cf_key = self.config.get('cf_key', '')

        # 在 IP 列表末尾添加 CF 模式选项
        self.all_ips.append('Cloudflare Chat Workers')

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

        tk.Label(self.lan_frame, text="端口:", font=("Arial", 10, "bold")).pack(anchor='w')
        self.port_var = tk.StringVar(value=saved_port)
        self.port_entry = tk.Entry(self.lan_frame, textvariable=self.port_var, font=("Arial", 10))
        self.port_entry.pack(fill='x')

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

        # 恢复保存的模式
        if saved_mode == 'cf':
            self.ip_var.set('Cloudflare Chat Workers')
            self.lan_frame.pack_forget()
            self.cf_frame.pack(fill='x', pady=(0, 10))
        elif saved_ip and saved_ip in self.all_ips:
            self.ip_var.set(saved_ip)

        # 按钮组
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

    def show_all_ips_display(self, port, started=False):
        """显示所有可用 IP 地址列表"""
        # 过滤掉 0.0.0.0 和 Cloudflare 选项
        all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare')]
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

    def toggle_server(self):
        if self.is_running:
            # 停止服务并退出
            self.quit_app()
            return

        selected = self.ip_var.get()

        # 判断模式并启动
        if selected == 'Cloudflare Chat Workers':
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
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare')]
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            url = f"http://{host_ip}:{port}"
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

        if selected == 'Cloudflare Chat Workers':
            # 切换到 CF 模式界面
            self.lan_frame.pack_forget()
            self.cf_frame.pack(fill='x', pady=(0, 10), before=self.button_frame)
        else:
            # 切换到局域网模式界面
            self.cf_frame.pack_forget()
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
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0') and not ip.startswith('Cloudflare')]
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            url = f"http://{host_ip}:{port}"
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
    root.mainloop()