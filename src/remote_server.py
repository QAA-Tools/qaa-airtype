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

    # 将主要 IP 放在第一位
    main_ip = get_host_ip()
    if main_ip in ips:
        ips.remove(main_ip)
    ips.insert(0, main_ip)

    return ips

# --- GUI 主程序 ---
class ServerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("无线输入板")
        # 增加高度以容纳二维码
        self.root.geometry("380x500")
        self.root.resizable(False, False)
        
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

        tk.Label(main_frame, text="端口 (Port):", font=("Arial", 10, "bold")).pack(anchor='w')
        tk.Entry(main_frame, textvariable=self.port_var, font=("Arial", 10)).pack(fill='x', pady=(0, 15))

        # 启动按钮
        self.btn_start = tk.Button(main_frame, text="启动服务并生成二维码", command=self.toggle_server, 
                                   bg="#007AFF", fg="white", font=("Arial", 12, "bold"), 
                                   relief="flat", pady=8, cursor="hand2")
        self.btn_start.pack(fill='x', pady=(0, 20))

        # 二维码显示区域
        self.qr_label = tk.Label(main_frame, text="点击启动后\n在此处显示二维码", 
                                 bg="#e6e6e6", fg="#888", width=30, height=12)
        self.qr_label.pack(pady=5)

        # 底部链接提示
        self.url_label = tk.Label(main_frame, text="", fg="blue", font=("Arial", 9, "underline"), cursor="hand2")
        self.url_label.pack(pady=(10, 0))
        self.url_label.bind("<Button-1>", self.open_browser) # 点击用浏览器打开

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
            # 停止服务
            result = messagebox.askyesno("停止服务", "确定要停止服务吗？\n停止后需要重启程序才能再次启动。")
            if result:
                self.root.quit()
            return

        port_str = self.port_var.get()
        if not port_str.isdigit():
            messagebox.showerror("错误", "端口必须是数字")
            return

        port = int(port_str)
        host_ip = self.ip_var.get()
        url = f"http://{host_ip}:{port}"

        # 启动 Flask 线程
        t = threading.Thread(target=self.run_flask, args=('0.0.0.0', port), daemon=True)
        t.start()

        self.is_running = True
        self.btn_start.config(text="停止服务", state='normal', bg="#ff3b30")

        # 生成并显示二维码
        try:
            self.qr_img = self.generate_qr(url) # 必须保持引用，否则会被垃圾回收
            self.qr_label.config(image=self.qr_img, width=200, height=200, bg="white")
        except Exception as e:
            self.qr_label.config(text=f"二维码生成失败\n{e}")

        # 显示文本链接
        self.url_label.config(text=url)
        self.current_url = url

    def open_browser(self, event):
        if hasattr(self, 'current_url'):
            import webbrowser
            webbrowser.open(self.current_url)

if __name__ == '__main__':
    root = tk.Tk()
    app_gui = ServerApp(root)
    root.mainloop()