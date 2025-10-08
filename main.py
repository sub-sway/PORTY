import streamlit as st
import paho.mqtt.client as mqtt
import json, ssl
from datetime import datetime

# ===============================
# HiveMQ Cloud 설정
# ===============================
BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 안전 지킴이 대시보드")

# ===============================
# 세션 상태 초기화
# ===============================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "client" not in st.session_state:
    st.session_state["client"] = None
if "connected" not in st.session_state:
    st.session_state["connected"] = False

# ===============================
# MQTT 콜백
# ===============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC)
        st.session_state["connected"] = True
        st.toast("✅ HiveMQ Cloud 연결 성공", icon="🟢")
    else:
        st.session_state["connected"] = False
        st.error(f"❌ 연결 실패 (코드 {rc})")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
    except:
        data = {"message": msg.payload.decode(), "type": "unknown"}
    data["time"] = datetime.now().strftime("%H:%M:%S")
    st.session_state["messages"].insert(0, data)
    st.experimental_rerun()  # 자동 갱신

# ===============================
# MQTT 자동 연결
# ===============================
def connect_mqtt():
    client = mqtt.Client()
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    st.session_state["client"] = client

if st.session_state["client"] is None:
    connect_mqtt()

# ===============================
# 상태 표시 및 로그
# ===============================
status = "🟢 연결됨" if st.session_state["connected"] else "🔴 연결 안 됨"
st.markdown(f"**📡 HiveMQ Cloud 상태:** {status}")
st.divider()

for msg in st.session_state["messages"][:10]:
    msg_type = msg.get("type", "info")
    message = msg.get("message", "")
    timestamp = msg.get("time", "")
    if msg_type in ["fire", "gas", "intruder", "safety"]:
        st.error(f"🚨 [{msg_type.upper()}] {message}  \n🕓 {timestamp}")
    else:
        st.info(f"ℹ️ {message}  \n🕓 {timestamp}")

st.caption("※ Jetson Orin에서 전송된 MQTT 경보를 HiveMQ Cloud로 수신합니다.")
