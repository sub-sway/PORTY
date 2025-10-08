import streamlit as st
import paho.mqtt.client as mqtt
import json
import socket
import threading
import time

# ----------------------------
# 페이지 설정
# ----------------------------
st.set_page_config(page_title="ROS2 알림 모니터", layout="wide")
st.title("📡 ROS2 → MQTT 알림 모니터링")

# ----------------------------
# 로컬 IP 자동 감지 함수
# ----------------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except:
        ip = "127.0.0.1"
    return ip

# ----------------------------
# 세션 상태 초기화
# ----------------------------
if "broker_ip" not in st.session_state:
    st.session_state["broker_ip"] = get_local_ip()
if "connected" not in st.session_state:
    st.session_state["connected"] = False
if "topic" not in st.session_state:
    st.session_state["topic"] = "robot/alerts"

# ✅ MQTT 콜백에서 안전하게 쓸 별도 리스트 (스레드 공유용)
message_buffer = []

# ----------------------------
# MQTT 콜백 함수
# ----------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        topic = userdata.get("topic", "robot/alerts")
        client.subscribe(topic)
        print(f"✅ MQTT 구독 성공: {topic}")
    else:
        print(f"❌ MQTT 연결 실패 (코드: {rc})")

def on_message(client, userdata, msg):
    """MQTT 수신 콜백 (Streamlit과 분리된 스레드에서 실행됨)"""
    try:
        data = msg.payload.decode()
        parsed = json.loads(data)
    except:
        parsed = {"message": msg.payload.decode()}
    message_buffer.append(parsed)  # ✅ st.session_state 대신 버퍼에 추가
    print(f"📩 MQTT 수신: {parsed}")

# ----------------------------
# MQTT 연결 함수
# ----------------------------
def connect_mqtt(ip, port, topic):
    client = mqtt.Client(userdata={"topic": topic})
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(ip, port, 60)
        client.loop_start()
        st.session_state["connected"] = True
        st.session_state["client"] = client
        st.toast(f"✅ MQTT 브로커 연결 성공 ({ip}:{port})", icon="🟢")
    except Exception as e:
        st.session_state["connected"] = False
        st.error(f"❌ MQTT 연결 실패: {e}")

# ----------------------------
# 사이드바 설정
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
# 연결 상태 표시
# ----------------------------
st.markdown(f"**📡 현재 브로커:** `{st.session_state['broker_ip']}:{port}`")
st.markdown(f"**🔌 연결 상태:** {'🟢 연결됨' if st.session_state['connected'] else '🔴 끊김'}")

st.divider()
st.subheader("📨 실시간 알림 내역")

# ----------------------------
# 실시간 표시 갱신 쓰레드
# ----------------------------
placeholder = st.empty()

def update_ui():
    """백그라운드에서 MQTT 버퍼를 계속 반영"""
    while True:
        if message_buffer:
            msg = message_buffer.pop(0)
            placeholder.warning(f"🚨 [{msg.get('type', '알림')}] {msg.get('message', '')}")
        time.sleep(0.5)

# ✅ 별도 쓰레드로 UI 갱신 루프 실행
threading.Thread(target=update_ui, daemon=True).start()

# 안내 메시지
st.info("MQTT 메시지를 수신하면 자동으로 화면에 표시됩니다.")
