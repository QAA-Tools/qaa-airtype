# QAA AirType 安装与连接说明

本文档说明如何在本机安装、启动，并用手机通过国内 MQTT 传输文字到电脑。

## 1. 安装

环境要求：Windows、Python 3.8 或更高版本。

方式一：双击 `install.bat` 自动安装依赖。

方式二：手动安装

```bash
pip install -r requirements.txt
```

如果使用打包版，则不需要安装 Python，直接运行 `QAA-AirType.exe`。

## 2. 启动

双击 `start.bat`，或在源码目录执行：

```bash
python src/remote_server.py
```

程序会打开 QAA AirType 窗口。

## 3. 电脑端配置 MQTT 模式

1. 在“连接模式”下拉框选择 `MQTT Broker (国内中转)`
2. 填写以下配置（以已开通的 EMQX Cloud 中国区为例）：
   - Broker 地址：`v7eaa3a3.ala.cn-hangzhou.emqxsl.cn`
   - 端口：`8883`
   - TLS：勾选
   - 用户名：`pc`
   - 密码：`123456`
   - 共享密钥：自己设置一个，例如 `my-shared-key`（电脑和手机必须一致）
   - 手机页面：可填 Cloudflare 页面地址，例如 `https://cfchat.wangbin060506.workers.dev/mqtt`；留空则使用本机局域网页面
3. 点击“启动服务”，状态变为“已连接 MQTT”即成功

## 4. 手机端连接

### 方式 A：局域网页面（最快）

手机和电脑连接同一个 WiFi，扫描电脑窗口上的二维码。页面会自动填入 Broker、账号和共享密钥，输入文字或使用手机输入法的语音输入，点击“发送”即可。

### 方式 B：Cloudflare 页面（跨网，消息仍走国内 MQTT）

1. 在电脑端“手机页面”填 `https://cfchat.wangbin060506.workers.dev/mqtt`（已绑定自定义域名时用自定义域名）后启动，二维码会指向该页面并附带连接参数
2. 手机在任何网络扫码打开页面，页面从 Cloudflare 加载，但 WebSocket 消息直连国内 EMQX，不经过 Cloudflare
3. 输入文字或语音输入后发送

## 5. Cloudflare 页面部署

`cfchat` 项目已新增 `/mqtt` 页面路由。如果你使用 Cloudflare Pages 连接 Git 仓库，推送后会自动构建部署；如果使用 Workers，需要执行：

```bash
wrangler deploy
```

部署后访问 `https://你的域名/mqtt` 确认页面可打开。

## 6. 消息长度说明

手机页面会把长文本按 16KB 分片加密发送，电脑端自动重组，因此不受常见 Broker 单条消息长度限制。已实测 200KB 文本完整传输。

## 8. 开机自启动与后台运行

- 勾选“开机自启动”后，Windows 登录时会以最小化方式在系统托盘后台启动，不弹窗口
- 勾选“启动后自动连接”后，程序启动会自动连接上一次使用的模式
- 运行中点击“停止服务”只停止当前连接，不退出程序；需要彻底退出时点“退出”或托盘菜单退出

## 7. 常见问题

- 连接不上：确认 Broker 地址、端口、TLS、用户名密码都正确；EMQX Cloud 免费实例有连接数限制，避免多个旧连接残留。
- 电脑端显示“已连接”但手机发消息没反应：确认两端共享密钥完全一致。
- 页面无法打开：确认手机和电脑在同一网络（局域网模式），或 Cloudflare 页面已部署成功。
- 想打包成 exe：运行 `build.ps1`（需要 PyInstaller）。
