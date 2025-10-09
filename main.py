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

# ===============================
# Streamlit 기본 설정
# ===============================
st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링 (HiveMQ Cloud)")

# ===============================
# 세션 상태 초기화
# ===============================
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "alerts" not in st.session_state:
    st.session_state["alerts"] = []
if "mqtt_client" not in st.session_state:
    st.session_state["mqtt_client"] = None

# ===============================
# MQTT 콜백 함수
# ===============================
def on_connect(client, userdata, flags, rc, properties=None):
    """MQTT 연결 콜백"""
    if rc == 0:
        client.subscribe(TOPIC)
        st.session_state["connected"] = True
        print(f"✅ HiveMQ Cloud 연결 성공 (topic: {TOPIC})")
    else:
        st.session_state["connected"] = False
        print(f"❌ HiveMQ Cloud 연결 실패, 코드={rc}")

def on_message(client, userdata, msg):
    """MQTT 메시지 수신 콜백"""
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
    except Exception:
        data = {"type": "unknown", "message": msg.payload.decode()}

    # 화재 또는 안전 관련 메시지만 처리
    if data.get("type") in ["fire", "safety"]:
        st.session_state["alerts"].append({
            "type": data.get("type"),
            "message": data.get("message", ""),
            "timestamp": data.get("timestamp", ""),
            "source": data.get("source_ip", "unknown")
        })
        print(f"📩 수신: {data}")

# ===============================
# MQTT 연결 함수
# ===============================
def connect_mqtt():
    """HiveMQ Cloud 연결"""
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        st.session_state["mqtt_client"] = client
        print("🟡 HiveMQ Cloud 연결 시도 중...")
    except Exception as e:
        st.session_state["connected"] = False
        print(f"❌ MQTT 연결 실패: {e}")

# ===============================
# 연결 스레드 시작 (1회만 실행)
# ===============================
if st.session_state["mqtt_client"] is None:
    threading.Thread(target=connect_mqtt, daemon=True).start()

# ===============================
# UI 표시
# ===============================
if not st.session_state["connected"]:
    st.warning("🔄 HiveMQ Cloud 연결 중... (약간의 시간이 걸릴 수 있습니다.)")
else:
    st.success("🟢 HiveMQ Cloud 연결됨")

st.divider()
st.subheader("📡 실시간 경보 내역")

# ===============================
# 실시간 UI 업데이트
# ===============================
alert_placeholder = st.empty()

def render_alerts():
    """Streamlit rerun 루프에서 경보 표시"""
    alerts = st.session_state["alerts"][-10:]  # 최근 10개만 표시
    with alert_placeholder.container():
        for alert in reversed(alerts):
            msg_type = alert.get("type", "info")
            message = alert.get("message", "")
            timestamp = alert.get("timestamp", "")
            source = alert.get("source", "unknown")

            if msg_type == "fire":
                st.error(f"🔥 **화재 경보!** {message}\n🕓 {timestamp}\n📍 {source}")
            elif msg_type == "safety":
                st.warning(f"⚠ **안전조끼 미착용** {message}\n🕓 {timestamp}\n📍 {source}")
            else:
                st.info(f"ℹ️ {message}")

# ===============================
# Streamlit rerun 루프
# ===============================
while True:
    render_alerts()
    time.sleep(1)
    st.rerun()
