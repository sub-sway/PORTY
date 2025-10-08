import streamlit as st
import paho.mqtt.client as mqtt
import json
import threading
import time
import ssl
from datetime import datetime

# =======================================
# 기본 설정
# =======================================
BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8883  # SSL 포트
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

st.set_page_config(page_title="항만시설 안전 지킴이 경비 로봇", layout="wide")
st.title("🛡️ 항만시설 현장 안전 지킴이 대시보드")

# =======================================
# 세션 상태 초기화
# =======================================
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "client" not in st.session_state:
    st.session_state["client"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# =======================================
# MQTT 콜백
# =======================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC)
        st.session_state["connected"] = True
        st.toast(f"✅ MQTT 연결 성공: {TOPIC}", icon="🟢")
    else:
        st.error(f"❌ MQTT 연결 실패 (코드: {rc})")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
    except:
        data = {"message": msg.payload.decode(), "type": "unknown"}

    data["time"] = datetime.now().strftime("%H:%M:%S")
    st.session_state["messages"].insert(0, data)

# =======================================
# MQTT 연결 함수
# =======================================
def connect_mqtt():
    try:
        client = mqtt.Client()
        client.username_pw_set(USERNAME, PASSWORD)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        st.session_state["client"] = client
        st.session_state["connected"] = True
        st.success("✅ HiveMQ Cloud 브로커 연결 성공")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}")
        st.session_state["connected"] = False

# =======================================
# MQTT 연결 버튼
# =======================================
if not st.session_state["connected"]:
    if st.button("🔌 HiveMQ Cloud 연결하기"):
        connect_mqtt()
else:
    st.success("🟢 연결 상태: HiveMQ Cloud 활성")

st.divider()

# =======================================
# 실시간 메시지 표시
# =======================================
st.subheader("📡 실시간 경보 수신 로그")

placeholder = st.empty()

def render_message(msg):
    msg_type = msg.get("type", "info")
    text = msg.get("message", "")
    timestamp = msg.get("time", "")
    if msg_type in ["fire", "gas", "intruder"]:
        st.error(f"🚨 [{msg_type.upper()}] {text}  \n🕓 {timestamp}")
    elif msg_type == "normal":
        st.success(f"✅ 정상 상태  \n🕓 {timestamp}")
    else:
        st.info(f"ℹ️ {text}  \n🕓 {timestamp}")

def update_ui():
    while True:
        if st.session_state["messages"]:
            with placeholder.container():
                for msg in st.session_state["messages"][:10]:  # 최근 10개 표시
                    render_message(msg)
        time.sleep(0.5)

threading.Thread(target=update_ui, daemon=True).start()

st.caption("※ Jetson Orin에서 전송된 화재, 침입, 가스 이상 신호를 실시간으로 표시합니다.")
