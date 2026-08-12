"""MQTT Serverless 保活脚本：发布消息并订阅同一主题验证回包。"""
import os
import random
import sys
import threading

import paho.mqtt.client as mqtt


def main():
    host = os.environ.get('MQTT_BROKER', '')
    port = int(os.environ.get('MQTT_PORT', '8883'))
    tls = os.environ.get('MQTT_TLS', 'true').lower() in ('1', 'true', 'yes')
    username = os.environ.get('MQTT_USERNAME', '')
    password = os.environ.get('MQTT_PASSWORD', '')
    topic = os.environ.get('MQTT_TOPIC', 'qaa/keepalive')
    payload = os.environ.get('MQTT_PAYLOAD', 'keepalive-ping')

    if not host or not username:
        print('缺少 MQTT_BROKER 或 MQTT_USERNAME', flush=True)
        return 1

    result = {}
    done = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        result['rc'] = str(reason_code)
        if reason_code == 0:
            client.subscribe(topic, qos=1)
            client.publish(topic, payload, qos=1)

    def on_message(client, userdata, msg):
        result['payload'] = msg.payload.decode('utf-8', errors='replace')
        done.set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id='github-keepalive-' + str(random.randint(1000, 9999)),
    )
    client.username_pw_set(username, password)
    if tls:
        client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(host, port, keepalive=30)
    client.loop_start()
    if not done.wait(timeout=30):
        print('FAIL: 未收到回包, rc=%s' % result.get('rc'), flush=True)
        client.disconnect()
        client.loop_stop()
        return 1

    print('OK topic=%s payload=%s' % (topic, result.get('payload')), flush=True)
    client.disconnect()
    client.loop_stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
