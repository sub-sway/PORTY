import streamlit as st
import paho.mqtt.client as mqtt
import pymongo
import json
import ssl
import queue
import pandas as pd
import datetime
import random
from streamlit_autorefresh import st_autorefresh

# --- 설정 ---
# secrets.toml 파일에 아래 정보가 올바르게 입력되어 있는지 확인해주세요.
HIVE_BROKER = st.secrets["HIVE_BROKER"]
HIVE_USERNAME = st.secrets["HIVE_USERNAME"]
HIVE_PASSWORD = st.secrets["HIVE_PASSWORD"]
MONGO_URI = st.secrets["MONGO_URI"]

# MQTT 및 MongoDB 고정 설정
HIVE_PORT = 8884
HIVE_TOPIC = "robot/alerts"
# [수정] 요청하신 DB 및 컬렉션 이름으로 변경
DB_NAME = "AlertDB"
COLLECTION_NAME = "AlertData"

# 스레드 간 데이터 전달을 위한 전역 큐
MESSAGE_QUEUE = queue.Queue()

# --- 페이지 설정 ---
st.set_page_config(page_title="안전 모니터링 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링")

# --- MongoDB & MQTT 클라이언트 연결 ---
@st.cache_resource
def get_db_collection():
    try:
        client = pymongo.MongoClient(MONGO_URI)
        client.server_info()
        db = client[DB_NAME]
        return db[COLLECTION_NAME]
    except Exception as e:
        st.error(f"MongoDB 연결 실패: {e}")
        return None

@st.cache_resource
def start_mqtt_client():
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(HIVE_TOPIC)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            # [수정] 메시지에 필수 키가 모두 있는지 확인하여 데이터 무결성 강화
            if all(key in data for key in ['type', 'message', 'timestamp']):
                MESSAGE_QUEUE.put(data)
        except (json.JSONDecodeError, TypeError):
            # 잘못된 형식의 JSON이나 필수 키가 없는 메시지는 무시
            pass

    client_id = f"streamlit-listener-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, transport="websockets", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(HIVE_USERNAME, HIVE_PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(HIVE_BROKER, HIVE_PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        st.error(f"MQTT 연결 실패: {e}")
        return None

# --- 클라이언트 실행 및 세션 상태 초기화 ---
db_collection = get_db_collection()
mqtt_client = start_mqtt_client()

# 화면에 표시할 데이터들을 session_state에 보관
if "latest_alerts" not in st.session_state:
    st.session_state.latest_alerts = []
if "current_status" not in st.session_state:
    st.session_state.current_status = {"message": "데이터 수신 대기 중...", "timestamp": "N/A"}

# --- 메인 로직 ---
if db_collection is not None:
    while not MESSAGE_QUEUE.empty():
        msg = MESSAGE_QUEUE.get()
        
        # 'normal' 타입 메시지는 DB에 저장하지 않고, 현재 상태만 업데이트
        if msg.get("type") == "normal":
            st.session_state.current_status = msg
            continue

        # DB에 저장하기 직전, 'source_ip' 필드를 제거
        if 'source_ip' in msg:
            del msg['source_ip']

        # ROS2 노드가 보낸 문자열 타임스탬프를 datetime 객체로 변환
        try:
            msg['timestamp'] = datetime.datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            msg['timestamp'] = datetime.datetime.now()

        # DB에 저장 및 화면 표시용 리스트에 추가
        try:
            db_collection.insert_one(msg)
            st.session_state.latest_alerts.insert(0, msg)
            if len(st.session_state.latest_alerts) > 100:
                st.session_state.latest_alerts.pop()
        except Exception as e:
            st.warning(f"DB 저장 실패: {e}")

# 앱 시작 시 DB에서 최근 경보 데이터 일부를 미리 로드
if not st.session_state.latest_alerts and db_collection is not None:
    try:
        query = {"type": {"$ne": "normal"}}
        alerts = list(db_collection.find(query).sort("timestamp", pymongo.DESCENDING).limit(50))
        st.session_state.latest_alerts = alerts
    except Exception as e:
        st.error(f"초기 데이터 로드 실패: {e}")

# --- UI 표시 ---
col1, col2 = st.columns([3, 1])
with col1:
    st.subheader("📡 시스템 현재 상태")
    status_message = st.session_state.current_status.get("message", "상태 정보 없음")
    status_time = st.session_state.current_status.get("timestamp", "N/A")
    st.info(f"{status_message} (마지막 신호: {status_time})")
with col2:
    st.subheader("MQTT 연결 상태")
    if mqtt_client and mqtt_client.is_connected():
        st.success("🟢 실시간 수신 중")
    else:
        st.error("🔴 연결 끊김")

st.divider()
st.subheader("🚨 최근 경보 내역")

if not st.session_state.latest_alerts:
    st.info("수신된 경보가 없습니다.")
else:
    df = pd.DataFrame(st.session_state.latest_alerts)
    # MongoDB의 datetime을 한국 시간으로 변환
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
    
    # 화면 표시 컬럼 이름 변경
    display_df = df.rename(columns={
        "timestamp": "발생 시각", "type": "유형", "message": "메시지"
    })
    
    st.dataframe(
        display_df[['발생 시각', '유형', '메시지']].sort_values(by="발생 시각", ascending=False),
        use_container_width=True,
        hide_index=True
    )

st_autorefresh(interval=2000, key="ui_refresher")

