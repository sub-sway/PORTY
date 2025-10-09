import streamlit as st
import paho.mqtt.client as mqtt
import json
import ssl
import queue
import datetime
import logging
import sys  # Streamlit Cloud 로깅을 위해 추가
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

# --- 디버깅 정보 확인 ---
with st.expander("🐞 디버깅 정보 확인"):
    st.write("--- 연결에 사용되는 실제 값 ---")
    try:
        st.write(f"BROKER: `{st.secrets['HIVE_BROKER']}`")
        st.write(f"USERNAME: `{st.secrets['HIVE_USERNAME']}`")
        st.write(f"PASSWORD: `{'*' * len(st.secrets['HIVE_PASSWORD'])}`")
    except KeyError as e:
        st.error(f"secrets.toml 파일 또는 Streamlit Cloud Secrets 설정에서 키를 찾을 수 없습니다: {e}")
    st.write(f"PORT: `{PORT}`")
    st.write(f"TOPIC: `{TOPIC}`")
    st.write(f"TRANSPORT: `websockets`")

# --- 세션 상태 초기화 ---
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
    try:
        data = json.loads(msg.payload.decode())
        MESSAGE_QUEUE.put(data)
    except Exception:
        error_data = {"type": "error", "message": "메시지 처리 오류", "raw_payload": msg.payload.decode(errors='ignore')}
        MESSAGE_QUEUE.put(error_data)

# --- MQTT 클라이언트 설정 ---
def setup_mqtt_client():
    # Streamlit Cloud 로그 뷰어에 직접 표시되도록 설정
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        force=True,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    # [수정] client = mqtt.Client(...) 중복 코드 삭제
    # 아래 한 줄만 남겨서 로거가 올바르게 적용되도록 수정했습니다.
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.enable_logger(logger)
    
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        # st.error는 UI에 표시되지만, 로그로도 남겨서 확인
        logger.error(f"MQTT 연결 시도 중 예외 발생: {e}")
        st.error(f"MQTT 연결 중 오류 발생: {e}")
        return None

# --- 이하 코드는 수정 없음 ---

# --- 메인 애플리케이션 로직 ---
if st.session_state.client is None:
    st.session_state.client = setup_mqtt_client()

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

# --- UI 표시 ---
if st.session_state.client and st.session_state.client.is_connected():
    st.success("🟢 HiveMQ Cloud 연결됨")
else:
    st.warning("🔄 HiveMQ Cloud에 연결 중이거나 연결에 실패했습니다.")

st.divider()

# (이하 UI 코드는 기존과 동일하므로 생략)
# ...
