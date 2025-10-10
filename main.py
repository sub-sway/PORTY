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
import logging
import sys

# --- 로거 설정 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# --- 알림음 종류별 Base64 데이터 ---
FIRE_ALARM_SOUND_BASE64 = "data:audio/wav;base64,UklGRiSAAQBXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAAABkYXRhgQEAIAAAAAYWGRo3doN1l3p8gH+Cf4J/in+LgY2Pjp+RlpWXl5iYmJeXlpeXlpeXlpeXlpeXlpeXl5eXl5aXk5iUlpWXl5aXlpeVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWVlJWV"
SAFETY_ALERT_SOUND_BASE64 = "data:audio/mpeg;base64,SUQzBAAAAAAAIVRYdEnDTPOq/3/3v/2/gAAAAAAAAAAAAAAB/2/g2/gAAA4SAAAEzGgAAAAAAD+kAzYAAAAAAAnnjk8eDEGANjBEyA/IjsgEyA7YEKkC5AlMBNkG/g2/gAAAAAAAAAAAAAAB/2/g2/gAAAA4SAAAEzGgAAAAAAD+kAzYAAAAAAAnnjk8eDEGANjBEyA/IjsgEyA7YEKkC5AlMBNk"

# --- 설정 ---
HIVE_BROKER = st.secrets["HIVE_BROKER"]
HIVE_USERNAME = st.secrets["HIVE_USERNAME"]
HIVE_PASSWORD = st.secrets["HIVE_PASSWORD"]
MONGO_URI = st.secrets["MONGO_URI"]

HIVE_PORT = 8884
HIVE_TOPIC = "robot/alerts"
DB_NAME = "AlertDB"
COLLECTION_NAME = "AlertData"
CONNECTION_TIMEOUT_SECONDS = 30

# --- 페이지 설정 및 캐시된 리소스 ---
st.set_page_config(page_title="안전 모니터링 대시보드", layout="wide")

@st.cache_resource
def get_message_queue():
    return queue.Queue()

@st.cache_resource
def get_db_collection():
    try:
        logger.info("MongoDB에 연결을 시도합니다...")
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client[DB_NAME]
        logger.info(f"MongoDB 연결 성공. DB: '{DB_NAME}', Collection: '{COLLECTION_NAME}'")
        return db[COLLECTION_NAME]
    except Exception as e:
        st.error(f"MongoDB 연결 실패: {e}")
        logger.error(f"MongoDB 연결 실패: {e}")
        return None

@st.cache_resource
def start_mqtt_client(_message_queue):
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"MQTT 브로커 연결 성공. 토픽 구독: '{HIVE_TOPIC}'")
            client.subscribe(HIVE_TOPIC)
        else:
            logger.error(f"MQTT 브로커 연결 실패, 코드: {rc}")

    def on_message(client, userdata, msg):
        try:
            payload = msg.payload.decode()
            logger.info(f"MQTT 메시지 수신 (토픽: '{msg.topic}'): {payload}")
            data = json.loads(payload)
            if all(key in data for key in ['type', 'message', 'timestamp']):
                _message_queue.put(data)
                logger.info("유효한 메시지를 큐에 추가했습니다.")
        except (json.JSONDecodeError, TypeError):
            pass

    client_id = f"streamlit-listener-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, transport="websockets", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(HIVE_USERNAME, HIVE_PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        logger.info("MQTT 브로커에 연결을 시도합니다...")
        client.connect(HIVE_BROKER, HIVE_PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        st.error(f"MQTT 연결 실패: {e}")
        logger.error(f"MQTT 연결 실패: {e}")
        return None

# --- 알림음 재생 함수 ---
def play_notification_sound(sound_type="safety"):
    if sound_type == "fire":
        sound_data = FIRE_ALARM_SOUND_BASE64
    else:
        sound_data = SAFETY_ALERT_SOUND_BASE64
    
    audio_html = f'<audio autoplay><source src="{sound_data}" type="audio/mpeg"></audio>'
    st.html(audio_html)

# --- 클라이언트 및 큐 실행/초기화 ---
message_queue = get_message_queue()
db_collection = get_db_collection()
mqtt_client = start_mqtt_client(message_queue)

# --- 세션 상태 초기화 ---
if "latest_alerts" not in st.session_state:
    st.session_state.latest_alerts = []
if "current_status" not in st.session_state:
    st.session_state.current_status = {"message": "데이터 수신 대기 중...", "timestamp": "N/A"}
if "last_message_time" not in st.session_state:
    st.session_state.last_message_time = datetime.datetime.now()

# --- 자동 재연결 로직 ---
time_since_last_message = (datetime.datetime.now() - st.session_state.last_message_time).total_seconds()
if time_since_last_message > CONNECTION_TIMEOUT_SECONDS:
    st.warning(f"{CONNECTION_TIMEOUT_SECONDS}초 이상 신호 없음. MQTT 재연결을 시도합니다...")
    logger.warning("MQTT 연결 시간 초과. 모든 캐시를 지우고 재연결을 시도합니다.")
    st.cache_resource.clear()
    st.session_state.last_message_time = datetime.datetime.now()
    st.rerun()

# --- UI 제목 ---
st.title("🛡️ 항만시설 현장 안전 모니터링")
logger.info("================ 스트림릿 앱 UI 렌더링 ================")

# --- 메인 로직: 큐에서 메시지 처리 ---
if db_collection is not None:
    while not message_queue.empty():
        msg = message_queue.get()
        st.session_state.last_message_time = datetime.datetime.now()
        logger.info(f"큐에서 메시지 처리 시작: {msg.get('type')}")
        
        alert_type = msg.get("type")
        if alert_type in ["fire", "safety"]:
            play_notification_sound(alert_type)
            st.toast(f"🚨 {msg.get('message')}", icon="🔥" if alert_type == "fire" else "⚠️")
        
        if alert_type == "normal":
            st.session_state.current_status = msg
            continue

        if 'source_ip' in msg:
            del msg['source_ip']

        try:
            msg['timestamp'] = datetime.datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            msg['timestamp'] = datetime.datetime.now()

        st.session_state.latest_alerts.insert(0, msg)
        if len(st.session_state.latest_alerts) > 100:
            st.session_state.latest_alerts.pop()
        
        try:
            db_collection.insert_one(msg)
            logger.info("메시지를 MongoDB에 성공적으로 저장했습니다.")
        except Exception as e:
            st.warning(f"DB 저장 실패! 화면에는 표시됩니다. ({e})")
            logger.error(f"MongoDB 저장 실패: {e}")

# --- 초기 데이터 로드 ---
if not st.session_state.latest_alerts and db_collection is not None:
    try:
        logger.info("초기 데이터 로드를 위해 DB를 조회합니다...")
        query = {"type": {"$ne": "normal"}}
        alerts = list(db_collection.find(query).sort("timestamp", pymongo.DESCENDING).limit(5))
        st.session_state.latest_alerts = alerts
        logger.info(f"초기 데이터 {len(alerts)}건을 DB에서 로드했습니다.")
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
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
    
    display_df = df.rename(columns={
        "timestamp": "발생 시각", "type": "유형", "message": "메시지"
    })
    
    st.dataframe(
        display_df[['발생 시각', '유형', '메시지']].sort_values(by="발생 시각", ascending=False),
        width='stretch',
        hide_index=True
    )

st_autorefresh(interval=2000, key="ui_refresher")
