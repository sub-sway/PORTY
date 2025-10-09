import streamlit as st
import paho.mqtt.client as mqtt
import json
import ssl
import queue
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
MESSAGE_QUEUE = queue.Queue()


# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="항만시설 안전 지킴이 대시보드 (디버깅 모드)", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링 (수신 확인용)")
st.warning("이 페이지는 MQTT 메시지 수신 여부를 확인하기 위한 디버깅용입니다.")


# --- 디버깅 정보 확인 ---
with st.expander("🐞 연결 정보 확인"):
    st.write(f"BROKER: `{BROKER}`")
    st.write(f"USERNAME: `{USERNAME}`")
    st.write(f"PASSWORD: `{'*' * len(PASSWORD)}`")
    st.write(f"PORT: `{PORT}`")
    st.write(f"TOPIC: `{TOPIC}`")


# --- 세션 상태 초기화 ---
if "client" not in st.session_state:
    st.session_state.client = None
if "raw_logs" not in st.session_state:
    st.session_state.raw_logs = []


# --- MQTT 콜백 함수 ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[연결 성공] 토픽 구독을 시작합니다:", TOPIC)
        client.subscribe(TOPIC)
    else:
        print(f"[연결 실패] 코드: {rc}")

### [핵심 수정] ###
# JSON 파싱 없이 원본 메시지를 그대로 터미널에 출력하고 큐에 넣습니다.
def on_message(client, userdata, msg, properties=None):
    """메시지 수신 시 터미널에 출력하고, 원본 데이터를 큐에 추가합니다."""
    raw_payload = msg.payload.decode(errors='ignore')
    
    # 1. 터미널에 즉시 출력 (가장 빠른 확인 방법)
    print(f"--- MQTT 메시지 수신 (터미널) ---")
    print(raw_payload)
    print(f"------------------------------------")

    # 2. 화면에 표시하기 위해 큐에 데이터 추가
    MESSAGE_QUEUE.put(raw_payload)

# --- MQTT 클라이언트 설정 ---
def setup_mqtt_client():
    client_id = f"streamlit-debug-app-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        print(f"{BROKER}:{PORT} 에 연결을 시도합니다...")
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        st.error(f"MQTT 연결 중 심각한 오류 발생: {e}")
        print(f"MQTT 연결 중 심각한 오류 발생: {e}")
        return None

# --- 메인 애플리케이션 로직 ---
if st.session_state.client is None:
    st.session_state.client = setup_mqtt_client()

# 큐에 있는 메시지를 로그에 추가
while not MESSAGE_QUEUE.empty():
    raw_message_string = MESSAGE_QUEUE.get()
    
    # 타임스탬프와 함께 로그 저장
    log_entry = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {raw_message_string}"
    st.session_state.raw_logs.append(log_entry)
    
    if len(st.session_state.raw_logs) > MAX_ALERTS_IN_MEMORY:
        st.session_state.raw_logs = st.session_state.raw_logs[-MAX_ALERTS_IN_MEMORY:]

# --- UI 표시 ---
if st.session_state.client and st.session_state.client.is_connected():
    st.success("🟢 HiveMQ Cloud 연결됨")
else:
    st.error("❌ HiveMQ Cloud에 연결되지 않았습니다. 터미널 로그와 secrets 설정을 확인하세요.")

st.divider()

### [핵심 수정] ###
# 수신된 원본 메시지를 화면에 최우선으로 보여줍니다.
st.subheader("🕵️ 수신된 전체 메시지 로그 (가장 먼저 여기를 확인하세요)")
if not st.session_state.raw_logs:
    st.info("아직 수신된 메시지가 없습니다. ROS2 노드가 실행 중인지, HiveMQ 웹소켓 클라이언트에 메시지가 보이는지 확인해주세요.")
else:
    # st.json은 JSON이 아닐 경우 에러가 나므로, st.code 또는 st.text를 사용합니다.
    st.code('\n'.join(st.session_state.raw_logs[::-1]), language='text')

st_autorefresh(interval=UI_REFRESH_INTERVAL_MS, key="auto_refresh")
