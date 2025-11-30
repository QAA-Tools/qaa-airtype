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
PASTE_KEY = 'command' if IS_MAC else 'ctrl'

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
            pyautogui.hotkey(PASTE_KEY, 'v')
            return {'success': True}
    except Exception:
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
        self.root.geometry("380x500")
        self.root.resizable(False, False)

        # 绑定窗口关闭事件
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

        # 设置窗口图标
        try:
            if os.path.exists('icon.ico'):
                self.root.iconbitmap('icon.ico')
        except Exception:
            pass

        # 系统托盘图标
        self.tray_icon = None
        self.create_tray_icon()
        
        # 居中屏幕
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 380) // 2
        y = (screen_height - 500) // 2
        self.root.geometry(f"380x500+{x}+{y}")

        self.all_ips = get_all_ips()
        self.ip_var = tk.StringVar(value=self.all_ips[0])
        self.port_var = tk.StringVar(value="5000")
        self.is_running = False

        # 主容器
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(expand=True, fill='both')

        # IP 和 端口 设置
        tk.Label(main_frame, text="本机 IP:", font=("Arial", 10, "bold")).pack(anchor='w')
        self.ip_combo = ttk.Combobox(main_frame, textvariable=self.ip_var,
                                     values=self.all_ips, font=("Arial", 10), state='normal')
        self.ip_combo.pack(fill='x', pady=(0, 10))
        # 绑定 IP 改变事件
        self.ip_combo.bind('<<ComboboxSelected>>', self.on_ip_changed)

        tk.Label(main_frame, text="端口 (Port):", font=("Arial", 10, "bold")).pack(anchor='w')
        self.port_entry = tk.Entry(main_frame, textvariable=self.port_var, font=("Arial", 10))
        self.port_entry.pack(fill='x', pady=(0, 15))

        # 启动按钮
        self.btn_start = tk.Button(main_frame, text="启动服务", command=self.toggle_server,
                                   bg="#007AFF", fg="white", font=("Arial", 12, "bold"),
                                   relief="flat", pady=8, cursor="hand2")
        self.btn_start.pack(fill='x', pady=(0, 20))

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
        all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0')]
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
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Error: {e}")

    def generate_qr(self, url):
        # 生成二维码图像
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        # 转换为 Tkinter 可用的格式
        img_tk = ImageTk.PhotoImage(img)
        return img_tk

    def toggle_server(self):
        if self.is_running:
            # 停止服务并退出
            self.quit_app()
            return

        port_str = self.port_var.get()
        if not port_str.isdigit():
            messagebox.showerror("错误", "端口必须是数字")
            return

        port = int(port_str)
        host_ip = self.ip_var.get()

        # 启动 Flask 线程
        t = threading.Thread(target=self.run_flask, args=('0.0.0.0', port), daemon=True)
        t.start()

        self.is_running = True
        self.btn_start.config(text="停止服务并退出", state='normal', bg="#ff3b30")

        # 禁用端口输入框
        self.port_entry.config(state='disabled', bg="#f0f0f0")

        # 处理 "0.0.0.0 (所有网卡)" 的情况
        if host_ip.startswith('0.0.0.0'):
            # 显示所有可用的 IP 地址
            self.show_all_ips_display(port, started=True)
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0')]
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            # 生成并显示二维码
            url = f"http://{host_ip}:{port}"
            try:
                self.qr_img = self.generate_qr(url) # 必须保持引用，否则会被垃圾回收
                self.qr_label.config(image=self.qr_img, width=200, height=200, bg="white", text='', font=("Arial", 10))
            except Exception as e:
                self.qr_label.config(text=f"二维码生成失败\n{e}")

            # 显示文本链接
            self.url_label.config(text=url)
            self.current_url = url
            self.tip_label.config(text="提示：如无法访问，请切换 IP 或端口重新扫码")

    def on_ip_changed(self, event=None):
        """当 IP 改变时更新二维码"""
        if not self.is_running:
            return

        host_ip = self.ip_var.get()
        port = int(self.port_var.get())

        # 处理 "0.0.0.0 (所有网卡)" 的情况
        if host_ip.startswith('0.0.0.0'):
            # 显示所有可用的 IP 地址
            self.show_all_ips_display(port, started=True)
            all_ips = [ip for ip in self.all_ips if not ip.startswith('0.0.0.0')]
            self.url_label.config(text="请手动输入上方地址")
            self.current_url = f"http://{all_ips[0]}:{port}" if all_ips else ""
            self.tip_label.config(text="")
        else:
            # 生成并显示二维码
            url = f"http://{host_ip}:{port}"
            try:
                self.qr_img = self.generate_qr(url)
                self.qr_label.config(image=self.qr_img, width=200, height=200, bg="white", text='', font=("Arial", 10))
            except Exception as e:
                self.qr_label.config(text=f"二维码生成失败\n{e}")

            # 显示文本链接
            self.url_label.config(text=url)
            self.current_url = url
            self.tip_label.config(text="提示：如无法访问，请切换 IP 或端口重新扫码")
            self.tip_label.config(text="提示：如无法访问，请切换 IP 重新扫码")

    def create_tray_icon(self):
        """创建系统托盘图标"""
        # 尝试加载 icon.png，如果不存在则创建简单图标
        try:
            if os.path.exists('icon.png'):
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