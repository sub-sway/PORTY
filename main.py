import streamlit as st
import paho.mqtt.client as mqtt
import json, ssl
from datetime import datetime
import threading, time

# =======================================
# HiveMQ Cloud 설정
# =======================================
BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8883  # SSL 포트
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

# =======================================
# 페이지 설정
# =======================================
st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 안전 지킴이 대시보드")

# =======================================
# 세션 상태 초기화
# =======================================
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "client" not in st.session_state:
    st.session_state["client"] = None

# =======================================
# MQTT 콜백
# =======================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC)
        st.session_state["connected"] = True
        print(f"✅ HiveMQ Cloud 연결 성공: {TOPIC}")
    else:
        st.session_state["connected"] = False
        print(f"❌ MQTT 연결 실패 (코드: {rc})")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
    except:
        data = {"type": "unknown", "message": msg.payload.decode()}
    data["time"] = datetime.now().strftime("%H:%M:%S")
    st.session_state["messages"].insert(0, data)
    st.experimental_rerun()  # 새 메시지 도착 시 즉시 화면 갱신

# =======================================
# MQTT 자동 연결
# =======================================
def connect_mqtt():
    if st.session_state["client"] is not None:
        return  # 이미 연결된 경우 중복 방지

    try:
        client = mqtt.Client()
        client.username_pw_set(USERNAME, PASSWORD)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        st.session_state["client"] = client
        print("🟢 HiveMQ Cloud 자동 연결 시도 중...")
    except Exception as e:
        st.error(f"❌ HiveMQ Cloud 연결 실패: {e}")

# Streamlit 실행 시 자동 연결
connect_mqtt()

# =======================================
# 연결 상태 표시
# =======================================
status = "🟢 연결됨" if st.session_state["connected"] else "🔴 연결 안 됨"
st.markdown(f"**📡 HiveMQ Cloud 상태:** {status}")
st.divider()

# =======================================
# 실시간 메시지 표시
# =======================================
st.subheader("📨 실시간 경보 로그")

for msg in st.session_state["messages"][:10]:
    msg_type = msg.get("type", "info")
    message = msg.get("message", "")
    timestamp = msg.get("time", "")

    if msg_type in ["fire", "gas", "intruder", "safety"]:
        st.error(f"🚨 [{msg_type.upper()}] {message}  \n🕓 {timestamp}")
    elif msg_type == "normal":
        st.success(f"✅ 정상 상태  \n🕓 {timestamp}")
    else:
        st.info(f"ℹ️ {message}  \n🕓 {timestamp}")

st.caption("※ Jetson Orin에서 발행된 MQTT 경보를 HiveMQ Cloud로 수신하여 실시간 표시합니다.")
