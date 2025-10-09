import streamlit as st
import paho.mqtt.client as mqtt
import json
import ssl
import queue
import datetime
import logging
import sys
from streamlit_autorefresh import st_autorefresh

# --- 설정 ---
BROKER = st.secrets["HIVE_BROKER"]
USERNAME = st.secrets["HIVE_USERNAME"]
PASSWORD = st.secrets["HIVE_PASSWORD"]

PORT = 8884
TOPIC = "robot/alerts"
MAX_ALERTS_IN_MEMORY = 100
UI_REFRESH_INTERVAL_MS = 1000
MESSAGE_QUEUE = queue.Queue()


# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="항만시설 안전 지킴이 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링 (HiveMQ Cloud)")

# ▼▼▼ 디버깅을 위해 이 블록을 추가 ▼▼▼
with st.expander("🐞 디버깅 정보 확인"):
    st.write("--- 연결에 사용되는 실제 값 ---")
    try:
        st.write(f"BROKER: `{st.secrets['HIVE_BROKER']}`")
        st.write(f"USERNAME: `{st.secrets['HIVE_USERNAME']}`")
        # 비밀번호는 보안을 위해 길이만 표시
        st.write(f"PASSWORD: `{'*' * len(st.secrets['HIVE_PASSWORD'])}`")
    except KeyError as e:
        st.error(f"secrets.toml 파일에서 키를 찾을 수 없습니다: {e}")
    
    st.write(f"PORT: `{PORT}`")
    st.write(f"TOPIC: `{TOPIC}`")
    st.write(f"TRANSPORT: `websockets`")

# --- 세션 상태 초기화 ---
# 이제 큐(queue)는 여기서 관리하지 않습니다.
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "client" not in st.session_state:
    st.session_state.client = None
if "current_status" not in st.session_state:
    st.session_state.current_status = {"message": "데이터 수신 대기 중...", "timestamp": "N/A"}
if "raw_logs" not in st.session_state:
    st.session_state.raw_logs = []


# --- MQTT 콜백 함수 ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    """
    [핵심 수정] st.session_state를 전혀 사용하지 않고,
    독립 객체인 MESSAGE_QUEUE에 직접 데이터를 넣습니다.
    """
    try:
        data = json.loads(msg.payload.decode())
        MESSAGE_QUEUE.put(data)
    except Exception:
        error_data = {"type": "error", "message": "메시지 처리 오류", "raw_payload": msg.payload.decode(errors='ignore')}
        MESSAGE_QUEUE.put(error_data)

# --- MQTT 클라이언트 설정 ---
def setup_mqtt_client():


    # ▼▼▼ Streamlit Cloud 로그 뷰어에 직접 표시되도록 수정 ▼▼▼
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,  # 로그를 파일 대신 표준 출력(콘솔)으로 보냄
        force=True,         # Streamlit이 선점한 로거를 덮어쓰기 위함
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # ▲▲▲ 수정 완료 ▲▲▲
    logger = logging.getLogger(__name__)
    # ▲▲▲ 여기까지 추가 ▲▲▲

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    
    # ▼▼▼ 클라이언트에 로거 연결 ▼▼▼
    client.enable_logger(logger)
    # ▲▲▲ 여기까지 추가 ▲▲▲
    
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
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

# [핵심 수정] st.session_state가 아닌 독립 MESSAGE_QUEUE에서 데이터를 가져옵니다.
while not MESSAGE_QUEUE.empty():
    message = MESSAGE_QUEUE.get()
    
    st.session_state.raw_logs.append(message)
    if len(st.session_state.raw_logs) > MAX_ALERTS_IN_MEMORY:
        st.session_state.raw_logs = st.session_state.raw_logs[-MAX_ALERTS_IN_MEMORY:]
    
    msg_type = message.get("type")
    
    if msg_type == "normal":
        st.session_state.current_status = message
    elif msg_type in ["fire", "safety"]:
        st.session_state.alerts.append(message)
        if len(st.session_state.alerts) > MAX_ALERTS_IN_MEMORY:
            st.session_state.alerts = st.session_state.alerts[-MAX_ALERTS_IN_MEMORY:]

# --- UI 표시 (이하 동일) ---
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
        st.success(f"{status_message} (마지막 신호: {status_time})")
except (ValueError, TypeError):
     st.warning(f"{status_message}")

st.divider()

st.subheader("🚨 실시간 경보 내역 (최근 10건)")
if not st.session_state.alerts:
    st.info("현재 수신된 경보가 없습니다.")
else:
    for alert in reversed(st.session_state.alerts[-10:]):
        msg_type = alert.get("type", "unknown"); message = alert.get("message", "내용 없음"); timestamp = alert.get("timestamp", "N/A"); source = alert.get("source_ip", "N/A")
        if msg_type == "fire": st.error(f"🔥 **화재 경보!** {message}\n\n🕓 {timestamp}\n\n📍 {source}")
        elif msg_type == "safety": st.warning(f"⚠️ **안전조끼 미착용** {message}\n\n🕓 {timestamp}\n\n📍 {source}")

with st.expander("🕵️ 전체 수신 로그 (디버깅용)"):
    if not st.session_state.raw_logs:
        st.write("수신된 메시지가 없습니다.")
    else:
        st.json(st.session_state.raw_logs[::-1])

st_autorefresh(interval=UI_REFRESH_INTERVAL_MS, key="auto_refresh")
