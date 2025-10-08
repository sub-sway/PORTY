import streamlit as st
import paho.mqtt.client as mqtt
import json
import socket
import threading
import time

st.set_page_config(page_title="ROS2 알림 모니터", layout="wide")
st.title("📡 ROS2 → MQTT 알림 모니터링")

# ----------------------------
# 세션 상태 초기화
# ----------------------------
# ✅ 브로커 IP를 직접 고정 (여기만 바꾸면 됨)
FIXED_BROKER_IP = "192.168.0.108"

if "broker_ip" not in st.session_state:
    st.session_state["broker_ip"] = FIXED_BROKER_IP
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "topic" not in st.session_state:
    st.session_state["topic"] = "robot/alerts"

message_buffer = []

# ----------------------------
# MQTT 콜백
# ----------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        topic = userdata.get("topic", "robot/alerts")
        client.subscribe(topic)
        print(f"✅ MQTT 구독 성공: {topic}")
    else:
        print(f"❌ MQTT 연결 실패 (코드: {rc})")

def on_message(client, userdata, msg):
    try:
        data = msg.payload.decode()
        parsed = json.loads(data)
    except:
        parsed = {"message": msg.payload.decode()}
    message_buffer.append(parsed)
    print(f"📩 MQTT 수신: {parsed}")

# ----------------------------
# MQTT 연결 함수
# ----------------------------
def connect_mqtt(ip, port, topic):
    try:
        client = mqtt.Client(userdata={"topic": topic})
    except TypeError:
        client = mqtt.Client(callback_api_version=4, userdata={"topic": topic})

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(ip, int(port), 60)
        client.loop_start()
        st.session_state["connected"] = True
        st.session_state["client"] = client
        st.toast(f"✅ MQTT 브로커 연결 성공 ({ip}:{port})", icon="🟢")
    except Exception as e:
        st.session_state["connected"] = False
        st.error(f"❌ MQTT 연결 실패: {e}")

# ----------------------------
# 사이드바
# ----------------------------
st.sidebar.header("⚙️ MQTT 설정")
st.sidebar.caption("Jetson Orin에서 실행 중인 MQTT 브로커에 연결합니다.")

# ✅ IP는 고정값 사용
broker_ip = FIXED_BROKER_IP
port = st.sidebar.number_input("포트 번호", min_value=1, max_value=65535, value=1883)
topic = st.sidebar.text_input("토픽", st.session_state["topic"])
connect_btn = st.sidebar.button("💾 연결")

if connect_btn:
    st.session_state["broker_ip"] = broker_ip
    st.session_state["topic"] = topic
    connect_mqtt(broker_ip, port, topic)

# ----------------------------
# UI 표시
# ----------------------------
st.markdown(f"**📡 현재 브로커:** `{broker_ip}:{port}`")
st.markdown(f"**🔌 연결 상태:** {'🟢 연결됨' if st.session_state['connected'] else '🔴 끊김'}")
st.divider()
st.subheader("📨 실시간 알림 내역")

placeholder = st.empty()

def update_ui():
    while True:
        if message_buffer:
            msg = message_buffer.pop(0)
            msg_type = msg.get("type", "info")
            message = msg.get("message", "")
            if msg_type in ["intruder", "fire", "gas"]:
                placeholder.error(f"🚨 [{msg_type.upper()}] {message}")
            else:
                placeholder.info(f"✅ 정상 상태 ({msg_type})")
            st.experimental_rerun()
        time.sleep(0.5)

threading.Thread(target=update_ui, daemon=True).start()

st.info("MQTT 메시지를 수신하면 자동으로 화면에 표시됩니다.")
