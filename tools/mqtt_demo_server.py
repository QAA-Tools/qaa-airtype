"""MQTT 模式接收演示：启动 Flask 页面托管和 MQTT 接收客户端。

用法:
    python tools/mqtt_demo_server.py --broker broker.emqx.io --port 1883 --key 123456

收到消息后会打印，并可选写入日志文件；不会自动粘贴，避免干扰当前窗口。
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from remote_server import app, MqttClient  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='MQTT 接收演示服务')
    parser.add_argument('--broker', default='broker.emqx.io')
    parser.add_argument('--port', default='1883')
    parser.add_argument('--tls', action='store_true')
    parser.add_argument('--username', default='')
    parser.add_argument('--password', default='')
    parser.add_argument('--key', default='123456', help='与手机端一致的共享密钥')
    parser.add_argument('--flask-port', default='5000')
    parser.add_argument('--no-flask', action='store_true', help='不启动手机页面托管服务')
    parser.add_argument('--log', default='', help='收到的消息写入该文件')
    parser.add_argument('--duration', type=float, default=0, help='运行秒数，0 表示一直运行')
    parser.add_argument('--client-id', default='qaa-airtype-pc-demo', help='MQTT 客户端 ID，避免与正式程序冲突')
    args = parser.parse_args()

    def on_message(text, enter=False):
        print(f"RECEIVED len={len(text)} text={text[:60]!r}", flush=True)
        print(f"ENTER={int(bool(enter))}", flush=True)
        if args.log:
            with open(args.log, 'a', encoding='utf-8') as f:
                f.write(f"{time.time()}\t{len(text)}\t{text}\n")

    def on_status(state, text):
        print(f"STATUS {state}: {text}", flush=True)

    client = MqttClient(
        broker_host=args.broker,
        broker_port=args.port,
        username=args.username or None,
        password=args.password or None,
        use_tls=args.tls,
        shared_key=args.key,
        on_message=on_message,
        on_status=on_status,
        client_id=args.client_id,
    )
    if not client.start():
        print("MQTT 客户端启动失败", flush=True)
        return 1

    if not args.no_flask:
        def run_flask():
            app.run(host='0.0.0.0', port=int(args.flask_port), debug=False, use_reloader=False)
        threading.Thread(target=run_flask, daemon=True).start()
        print(f"手机页面: http://127.0.0.1:{args.flask_port}/?theme=mqtt", flush=True)

    print(f"主题: {client.topic}", flush=True)
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
