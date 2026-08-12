"""MQTT 模式手机端发送模拟器（与 theme/mqtt.html 使用相同加密协议）。

用法:
    python tools/mqtt_send_simulator.py --broker broker.emqx.io --port 1883 --key 123456 --text 你好
    python tools/mqtt_send_simulator.py --broker broker.emqx.io --port 1883 --key 123456 --long-kb 200 --enter
"""
import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import paho.mqtt.client as mqtt  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from remote_server import MQTT_CHUNK_BYTES, derive_key_and_room, derive_mqtt_topic  # noqa: E402


def encrypt(key, data):
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, data, None)
    return base64.b64encode(iv).decode(), base64.b64encode(ct).decode()


def publish(client, topic, payload):
    info = client.publish(topic, json.dumps(payload), qos=1)
    info.wait_for_publish(timeout=20)


def send_text(client, topic, key, text, enter=False):
    data = text.encode('utf-8')
    extra = {'e': 1} if enter else {}

    if len(data) <= MQTT_CHUNK_BYTES:
        iv, ct = encrypt(key, data)
        payload = {'v': 1, 't': 'text', 'iv': iv, 'data': ct, **extra}
        publish(client, topic, payload)
        print(f"SENT text len={len(data)} enter={int(enter)}", flush=True)
        return 1

    msg_id = os.urandom(8).hex()
    total = (len(data) + MQTT_CHUNK_BYTES - 1) // MQTT_CHUNK_BYTES
    for i in range(total):
        part = data[i * MQTT_CHUNK_BYTES:(i + 1) * MQTT_CHUNK_BYTES]
        iv, ct = encrypt(key, part)
        chunk_payload = {
            'v': 1, 't': 'chunk', 'id': msg_id, 'i': i, 'n': total,
            'iv': iv, 'data': ct, **extra,
        }
        publish(client, topic, chunk_payload)
        time.sleep(0.03)
    print(f"SENT chunks={total} total_bytes={len(data)} enter={int(enter)}", flush=True)
    return total


def main():
    parser = argparse.ArgumentParser(description='MQTT 手机端发送模拟器')
    parser.add_argument('--broker', default='broker.emqx.io')
    parser.add_argument('--port', default='1883')
    parser.add_argument('--tls', action='store_true')
    parser.add_argument('--username', default='')
    parser.add_argument('--password', default='')
    parser.add_argument('--key', default='123456')
    parser.add_argument('--text', default='')
    parser.add_argument('--long-kb', type=int, default=0, help='生成指定 KB 的长文本并分片发送')
    parser.add_argument('--enter', action='store_true', help='发送后通知电脑端自动回车')
    args = parser.parse_args()

    key, _ = derive_key_and_room(args.key)
    topic = derive_mqtt_topic(args.key)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='qaa-phone-sim')
    if args.username:
        client.username_pw_set(args.username, args.password)
    if args.tls:
        client.tls_set()

    connected = False

    def on_connect(c, userdata, flags, reason_code, properties=None):
        nonlocal connected
        connected = reason_code == 0

    client.on_connect = on_connect
    client.connect_async(args.broker, int(args.port), keepalive=30)
    client.loop_start()

    deadline = time.time() + 20
    while not connected and time.time() < deadline:
        time.sleep(0.1)
    if not connected:
        print("发送端连接失败", flush=True)
        client.loop_stop()
        return 1

    print(f"发送端已连接 topic={topic}", flush=True)

    if args.text:
        send_text(client, topic, key, args.text, enter=args.enter)
    if args.long_kb > 0:
        long_text = ('消息长度测试' + 'A' * 40) * max(1, args.long_kb * 1024 // 48)
        long_text = long_text[:args.long_kb * 1024]
        send_text(client, topic, key, long_text, enter=args.enter)

    time.sleep(1)
    client.loop_stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
