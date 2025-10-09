import streamlit as st
import paho.mqtt.client as mqtt
import json
import ssl
import queue  # queue 라이브러리는 그대로 import 합니다.
import datetime
import logging
import random
from streamlit_autorefresh import st_autorefresh

# --- 설정 ---
try:
    BROKER = st.secrets["HIVE_BROKER"]
    USERNAME = st.secrets["HIVE_USERNAME"]
    PASSWORD = st.secrets["HIVE_PASSWORD"]
except KeyError as e:
    st.error(f"Streamlit Secrets 설정이 필요합니다. '.streamlit/secrets.toml' 파일에서 '{e}' 키를 찾을 수 없습니다.")
    st.stop()

PORT = 8884
TOPIC = "robot/alerts"
MAX_ALERTS_IN_MEMORY = 100
UI_REFRESH_INTERVAL_MS = 1000

### [수정 1] ###
# 전역 변수로 선언했던 QUEUE를 제거합니다.
# MESSAGE_QUEUE = queue.Queue()  <- 이 줄을 삭제

# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링 (HiveMQ Cloud)")

# --- 세션 상태 초기화 ---
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "client" not in st.session_state:
    st.session_state.client = None
if "current_status" not in st.session_state:
    st.session_state.current_status = {"message": "데이터 수신 대기 중...", "timestamp": "N/A"}
if "raw_logs" not in st.session_state:
    st.session_state.raw_logs = []

### [수정 2] ###
# message_queue를 session_state에 한 번만 초기화합니다.
if "message_queue" not in st.session_state:
    st.session_state.message_queue = queue.Queue()

# --- MQTT 콜백 함수 ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe(TOPIC)

def on_message(client, userdata, msg, properties=None):
    try:
        data = json.loads(msg.payload.decode())
        ### [수정 3] ###
        # session_state에 있는 큐에 데이터를 넣습니다.
        st.session_state.message_queue.put(data)
    except Exception:
        error_data = {"type": "error", "message": "메시지 처리 오류", "raw_payload": msg.payload.decode(errors='ignore')}
        st.session_state.message_queue.put(error_data)

# --- MQTT 클라이언트 설정 ---
def setup_mqtt_client():
    client_id = f"streamlit-app-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        st.error(f"MQTT 연결 중 오류 발생: {e}")
        return None

# --- 메인 애플리케이션 로직 ---
if st.session_state.client is None:
    st.session_state.client = setup_mqtt_client()

### [수정 4] ###
# session_state에 저장된 큐를 사용합니다.
while not st.session_state.message_queue.empty():
    message = st.session_state.message_queue.get()
    
    st.session_state.raw_logs.append(message)
    if len(st.session_state.raw_logs) > MAX_ALERTS_IN_MEMORY:
        st.session_state.raw_logs.pop(0)
    
    msg_type = message.get("type")
    
    if msg_type == "normal":
        st.session_state.current_status = message
    elif msg_type in ["fire", "safety"]:
        st.session_state.alerts.append(message)
        if len(st.session_state.alerts) > MAX_ALERTS_IN_MEMORY:
            st.session_state.alerts.pop(0)

# --- UI 표시 (기존과 동일) ---
if st.session_state.client and st.session_state.client.is_connected():
    st.success("🟢 HiveMQ Cloud 연결됨")
else:
    st.warning("🔄 HiveMQ Cloud에 연결 중이거나 연결에 실패했습니다.")

st.divider()

st.subheader("📡 시스템 현재 상태")
status_message = st.session_state.current_status.get("message", "상태 정보 없음")
status_time = st.session_state.current_status.get("timestamp", "N/A")

try:
    last_signal_time = datetime.datetime.strptime(status_time, "%Y-%m-%d %H:%M:%S")
    time_diff_seconds = (datetime.datetime.now() - last_signal_time).total_seconds()
    
    if time_diff_seconds > 15:
        st.error(f"❌ ROS2 노드 연결 끊김 의심 (마지막 신호: {status_time})")
    else:
        st.info(f"{status_message} (마지막 신호: {status_time})")
except (ValueError, TypeError):
    st.warning(f"{status_message}")

st.divider()

st.subheader("🚨 실시간 경보 내역")
if not st.session_state.alerts:
    st.info("현재 수신된 경보가 없습니다.")
else:
    for alert in reversed(st.session_state.alerts[-10:]):
        msg_type = alert.get("type", "unknown")
        message = alert.get("message", "내용 없음")
        timestamp = alert.get("timestamp", "N/A")
        source = alert.get("source_ip", "N/A")
        
        if msg_type == "fire":
            st.error(f"🔥 **화재 경보!** - {message} (발생 시각: {timestamp}, 발생지: {source})")
        elif msg_type == "safety":
            st.warning(f"⚠️ **안전조끼 미착용** - {message} (발생 시각: {timestamp}, 발생지: {source})")

with st.expander("🕵️ 전체 수신 로그 (디버깅용)"):
    if not st.session_state.raw_logs:
        st.write("수신된 메시지가 없습니다.")
    else:
        st.json(st.session_state.raw_logs[::-1])

st_autorefresh(interval=UI_REFRESH_INTERVAL_MS, key="auto_refresh")
