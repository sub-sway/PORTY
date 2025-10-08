import streamlit as st
import paho.mqtt.client as mqtt
import json
import socket
import threading
import time
import os

st.set_page_config(page_title="ROS2 알림 모니터", layout="wide")
st.title("📡 ROS2 → MQTT 알림 모니터링")

# ----------------------------
# 로컬 IP 자동 감지
# ----------------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return ip

# ----------------------------
# 설정 파일 저장/불러오기
# ----------------------------
CONFIG_PATH = os.path.expanduser("~/.mqtt_config.json")

def load_broker_ip():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f).get("broker_ip", get_local_ip())
        except Exception:
            return get_local_ip()
    return get_local_ip()

def save_broker_ip(ip):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"broker_ip": ip}, f)
    except Exception:
        pass

# ----------------------------
# 세션 상태 초기화
# ----------------------------
if "broker_ip" not in st.session_state:
    st.session_state["broker_ip"] = load_broker_ip()
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
    # ✅ 버전 호환성 처리
    try:
        client = mqtt.Client(userdata={"topic": topic})
    except TypeError:
        # 일부 환경에서는 callback_api_version 필요
        client = mqtt.Client(callback_api_version=4, userdata={"topic": topic})

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(ip, int(port), 60)
        client.loop_start()
        st.session_state["connected"] = True
        st.session_state["client"] = client
        st.toast(f"✅ MQTT 브로커 연결 성공 ({ip}:{port})", icon="🟢")
        save_broker_ip(ip)
    except Exception as e:
        st.session_state["connected"] = False
        st.error(f"❌ MQTT 연결 실패: {e}")

# ----------------------------
# 사이드바
# ----------------------------
st.sidebar.header("⚙️ MQTT 설정")
st.sidebar.caption("Jetson Orin에서 실행 중인 MQTT 브로커에 연결합니다.")

broker_ip = st.sidebar.text_input("브로커 IP", st.session_state["broker_ip"])
port = st.sidebar.number_input("포트 번호", min_value=1, max_value=65535, value=1883)
topic = st.sidebar.text_input("토픽", st.session_state["topic"])
save_btn = st.sidebar.button("💾 설정 저장 및 연결")

if save_btn:
    st.session_state["broker_ip"] = broker_ip
    st.session_state["topic"] = topic
    connect_mqtt(broker_ip, port, topic)

# ----------------------------
# UI 표시
# ----------------------------
st.markdown(f"**📡 현재 브로커:** `{st.session_state['broker_ip']}:{port}`")
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
