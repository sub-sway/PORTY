import streamlit as st
import paho.mqtt.client as mqtt
import json
import ssl
import threading
import time

# ===============================
# HiveMQ Cloud 설정
# ===============================
BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링 (HiveMQ Cloud)")

# ===============================
# 연결 상태 전역 변수
# ===============================
connection_status = {"connecting": True, "connected": False}
messages_buffer = []

# ===============================
# MQTT 콜백 정의
# ===============================
def on_connect(client, userdata, flags, rc, properties=None):
    """MQTT 연결 콜백"""
    if rc == 0:
        client.subscribe(TOPIC)
        connection_status["connected"] = True
        connection_status["connecting"] = False
        print(f"✅ HiveMQ Cloud 연결 성공 (topic: {TOPIC})")
    else:
        connection_status["connected"] = False
        connection_status["connecting"] = False
        print(f"❌ HiveMQ Cloud 연결 실패, 코드={rc}")

def on_message(client, userdata, msg):
    """MQTT 메시지 수신 콜백"""
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
    except Exception:
        data = {"type": "unknown", "message": msg.payload.decode()}

    if data.get("type") not in ["fire", "safety"]:
        return

    messages_buffer.insert(0, data)
    print(f"📩 수신: {data}")

# ===============================
# MQTT 연결 함수
# ===============================
def connect_mqtt():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        print("🟡 HiveMQ Cloud 연결 시도 중...")
    except Exception as e:
        connection_status["connecting"] = False
        print(f"❌ MQTT 연결 실패: {e}")

# 앱 시작 시 자동 연결
threading.Thread(target=connect_mqtt, daemon=True).start()

# ===============================
# UI 표시
# ===============================
if connection_status["connecting"]:
    st.warning("🔄 HiveMQ Cloud 연결 중...")
elif connection_status["connected"]:
    st.success("🟢 HiveMQ Cloud 연결됨")
else:
    st.error("❌ MQTT 연결 실패")

st.divider()
st.subheader("📡 실시간 경보 내역")

placeholder = st.empty()

def render_message(msg):
    msg_type = msg.get("type", "info")
    message = msg.get("message", "")
    timestamp = msg.get("timestamp", "")
    source = msg.get("source_ip", "unknown")

    if msg_type == "fire":
        st.error(f"🔥 **화재 경보!** {message}\n🕓 {timestamp}\n📍 {source}")
    elif msg_type == "safety":
        st.warning(f"⚠ **안전조끼 미착용** {message}\n🕓 {timestamp}\n📍 {source}")

def update_ui():
    while True:
        if messages_buffer:
            with placeholder.container():
                for msg in messages_buffer[:10]:
                    render_message(msg)
        time.sleep(0.5)

threading.Thread(target=update_ui, daemon=True).start()

st.caption("Jetson Orin이 HiveMQ Cloud로 발행한 이상 상태만 실시간 표시합니다.")
