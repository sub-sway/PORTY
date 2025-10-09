# publisher.py
import paho.mqtt.client as mqtt
import time
import json
import random

BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8884
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

client_id = f"simple-publisher-{random.randint(0, 1000)}"
client = mqtt.Client(client_id=client_id, transport="websockets")
client.username_pw_set(USERNAME, PASSWORD)

try:
    client.connect(BROKER, PORT, 60)
    print("✅ Publisher connected to HiveMQ (WebSocket)")
    client.loop_start()

    count = 0
    while True:
        count += 1
        message = f"테스트 메시지 #{count}"
        data = {
            "type": "normal",
            "message": message,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "source_ip": "publisher.py"
        }
        payload = json.dumps(data)
        client.publish(TOPIC, payload)
        print(f"Sent: {payload}")
        time.sleep(2)

except Exception as e:
    print(f"❌ Publisher connection failed: {e}")

except KeyboardInterrupt:
    print("\n🛑 Publisher stopped.")
    client.loop_stop()
    client.disconnect()
