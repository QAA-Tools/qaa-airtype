# QAA AirType - 无线语音输入工具

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?logo=windows&logoColor=white)
![Stars](https://img.shields.io/github/stars/QAA-Tools/qaa-airtype?style=flat&logo=github)
![License](https://img.shields.io/badge/License-MIT-green)

<div align="center">

<img src="demo.png" width="600" alt="Demo">

**通过手机端语音输入实现电脑端远程输入的便捷工具**

</div>

## 📖 项目简介

QAA AirType 是一个轻量级的远程输入工具，让你可以通过手机端的输入法（如豆包语音输入）来实现电脑端的文字输入。支持局域网直连和 Cloudflare Workers 跨网络两种模式。

### 为什么开发这个项目？

在日常使用中，我们发现：
- 电脑端的语音识别质量普遍较差
- 电脑的麦克风设备往往不够理想
- 手机端的语音输入法（如豆包输入法）识别准确率更高
- 需要一个简单的方式将手机的语音输入同步到电脑

因此，这个项目应运而生，让你可以充分利用手机端优秀的语音识别能力，提升电脑端的输入效率。

> **注意**：本程序目前主要针对 Windows 系统开发和测试，在 macOS 和 Linux 上可能需要额外的配置或存在兼容性问题。

## ✨ 主要特性

- 📱 **扫码即用**：启动程序后扫描二维码即可连接
- 📝 **历史记录**：保存最近10条输入记录，支持快速重发
- 🎨 **自定义主题**：支持自定义网页界面主题，如增加定时发送功能
- 🌐 **局域网模式**：无需互联网，同一 WiFi 下即可使用
- ☁️ **Cloudflare 模式**：自建免费 Workers 服务，突破局域网限制，手机流量也能用
- 📡 **MQTT 模式**：连接 MQTT Broker（可部署在国内），跨网延迟更低，长文本自动分片
- 🔽 **系统托盘**：最小化到托盘，不占用任务栏
- 📖 **详细文档**：[qaa-tools.github.io/qaa-airtype](https://qaa-tools.github.io/qaa-airtype/)

## 🚀 快速开始

> 完整安装与连接步骤：[安装与连接说明](docs/installation.md)

### 方式一：下载可执行文件

1. 从 [Releases](https://github.com/QAA-Tools/qaa-airtype/releases) 下载 `QAA-AirType.exe`
2. 双击运行，选择连接模式（局域网 IP 或 Cloudflare）
3. 点击"启动服务"
4. 手机扫描二维码或访问显示的地址
5. 在手机网页使用语音输入，点击发送，文字自动粘贴到电脑

### MQTT 模式（国内中转）

1. 在电脑端选择 `MQTT Broker (国内中转)`
2. 填写 Broker 地址、端口、用户名/密码（无认证可留空）和共享密钥
3. 手机扫码打开页面，连接后输入语音/文字即可发送
4. 电脑收到消息后自动粘贴；超长文本会自动分片传输，避免 Broker 长度限制

推荐使用国内可免费注册的 EMQX Cloud 中国区、中国移动 OneNET 或电信 CTWing；公共测试 Broker 可使用 `broker.emqx.io:8084`（wss）。

#### 国内免费 Broker 接入示例

- **EMQX Cloud 中国区 Serverless**：注册后创建免费部署，控制台会给出连接地址和端口。电脑端填 TCP 端口（通常 1883，TLS 为 8883），手机页面填 WebSocket 端口（通常 8083 ws 或 8084 wss），用户名/密码按控制台生成或留空。
- **中国移动 OneNET**：注册后创建产品和设备，MQTT 地址为 `183.230.40.96:1883`，用户名/密码使用平台生成的产品/设备凭据。
- **电信 CTWing**：注册后创建应用和设备，地址为 `mqtt.ctwing.cn:1883`，按平台文档填入设备凭据。

注意：手机页面必须连接 Broker 的 WebSocket 端口（ws/wss）。如果平台只提供 TCP 1883 端口，手机浏览器无法直连，需要改用 MQTT 客户端 App，或在国内服务器上自建 EMQX 并同时开放 1883 和 8083/8084。

### 自定义主题

程序支持自定义网页界面主题，在exe同目录放置HTML文件即可：

- **默认访问**：`http://ip:port/`
- **指定主题**：将自定义主题文件 `xxx.html` 放在 `QAA-AirType.exe` 同目录，采用 `http://ip:port/?theme=xxx` 使用
- **示例主题**：参考 `theme/` 目录中的示例
  - `light.html` - 简洁白色主题（手动发送）
  - `auto.html` - 智能主题（支持自动发送功能）
  - `detect.html` - 智能主题（当编辑框不发生变化后，再自动发送）

用户可根据需求自行开发主题，后端API保持不变。

### 方式二：从源码运行

```bash
git clone https://github.com/QAA-Tools/qaa-airtype.git
cd qaa-airtype

# 安装依赖
pip install flask pyautogui pyperclip qrcode pillow pystray paho-mqtt cryptography websockets

# 运行程序
python src/remote_server.py
```

## 🙏 致谢

- **Gemini**：核心程序编写
- **Claude**：项目标准化设计

---

<div align="center">

MIT License · Made with ❤️

</div>
