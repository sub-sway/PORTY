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
# 세션 상태 초기화 (안전하게 보장)
# ===============================
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "connecting" not in st.session_state:
    st.session_state["connecting"] = True

# ✅ 전역 메시지 버퍼 (스레드 안전)
messages_buffer = []

# ===============================
# MQTT 콜백 정의
# ===============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC)
        st.session_state["connected"] = True
        st.session_state["connecting"] = False
        print(f"✅ MQTT 구독 성공: {TOPIC}")
    else:
        st.session_state["connecting"] = False
        print(f"❌ MQTT 연결 실패 (코드 {rc})")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
    except:
        data = {"type": "unknown", "message": msg.payload.decode()}

    # ✅ 정상 상태 제외
    if data.get("type") not in ["fire", "safety"]:
        return

    messages_buffer.insert(0, data)  # 새 메시지 맨 위로 추가
    print(f"📩 MQTT 수신: {data}")

# ===============================
# MQTT 자동 연결
# ===============================
def connect_mqtt():
    client = mqtt.Client()
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        print("🟡 HiveMQ Cloud 연결 시도 중...")
    except Exception as e:
        st.session_state["connecting"] = False
        print(f"❌ MQTT 연결 실패: {e}")

# ✅ 앱 시작 시 자동 연결
if not st.session_state["connected"] and st.session_state["connecting"]:
    threading.Thread(target=connect_mqtt, daemon=True).start()

# ===============================
# 연결 상태 표시
# ===============================
if st.session_state["connecting"]:
    st.warning("🔄 HiveMQ Cloud 연결 중...")
elif st.session_state["connected"]:
    st.success("🟢 HiveMQ Cloud 연결됨")
else:
    st.error("❌ MQTT 연결 실패")

st.divider()
st.subheader("📡 실시간 경보 내역")

placeholder = st.empty()

# ===============================
# 메시지 렌더링 함수
# ===============================
def render_message(msg):
    msg_type = msg.get("type", "info")
    message = msg.get("message", "")
    timestamp = msg.get("timestamp", "")
    source = msg.get("source_ip", "unknown")

    if msg_type == "fire":
        st.error(f"🔥 **화재 경보!** {message}\n🕓 {timestamp}\n📍 {source}")
    elif msg_type == "safety":
        st.warning(f"⚠ **안전조끼 미착용** {message}\n🕓 {timestamp}\n📍 {source}")

# ===============================
# UI 업데이트 스레드 (session_state 접근 금지)
# ===============================
def update_ui():
    while True:
        if messages_buffer:
            with placeholder.container():
                for msg in messages_buffer[:10]:  # 최근 10개 표시
                    render_message(msg)
        time.sleep(0.5)

threading.Thread(target=update_ui, daemon=True).start()

st.caption("Jetson Orin이 HiveMQ Cloud로 발행한 이상 상태만 실시간 표시합니다.")
