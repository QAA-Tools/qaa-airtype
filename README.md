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

QAA AirType 是一个轻量级的局域网输入板，让你可以通过手机端的输入法（如豆包语音输入）来实现电脑端的文字输入（与Agent对话）。

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
- 🌐 **局域网连接**：无需互联网，局域网内即可使用
- ☁️ **跨网络支持**：通过 Cloudflare Workers 突破局域网限制
- 🔽 **系统托盘**：最小化到托盘，不占用任务栏

📖 **详细文档**：[https://qaa-tools.github.io/qaa-airtype/](https://qaa-tools.github.io/qaa-airtype/)

## 🚀 快速开始

### 普通用户

1. 下载 `QAA-AirType.exe`
2. 双击运行，点击"启动服务并生成二维码"
3. 手机扫描二维码（确保同一 WiFi）
4. 在手机网页使用语音输入，点击发送

### 开发者

#### 运行源码

```bash
git clone https://github.com/QAA-Tools/qaa-airtype.git
cd qaa-airtype

# 安装依赖
pip install flask pyautogui pyperclip qrcode pillow pystray

# 运行程序
python src/remote_server.py
```

#### 项目结构

```
qaa-airtype/
├── src/
│   ├── remote_server.py     # 主程序
│   └── generate_icon.py     # 图标生成
├── build.ps1                # 构建脚本
├── pyproject.toml          # 项目配置
├── LICENSE                 # MIT 协议
└── README.md               # 项目说明
```

#### 编译可执行文件

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

编译完成后，可执行文件位于 `dist/QAA-AirType.exe`

#### 技术栈

Flask · Tkinter · PyAutoGUI · Pyperclip · QRCode · Pillow · Pystray

## 🙏 致谢

- **Gemini**：核心程序编写
- **Claude**：项目标准化设计

---

<div align="center">

MIT License · Made with ❤️

</div>
