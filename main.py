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
import sys # sys 모듈 추가

# --- 로거 설정 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# --- 설정 ---
HIVE_BROKER = st.secrets["HIVE_BROKER"]
HIVE_USERNAME = st.secrets["HIVE_USERNAME"]
HIVE_PASSWORD = st.secrets["HIVE_PASSWORD"]
MONGO_URI = st.secrets["MONGO_URI"]

# MQTT 및 MongoDB 고정 설정
HIVE_PORT = 8884
HIVE_TOPIC = "robot/alerts"
DB_NAME = "AlertDB"
COLLECTION_NAME = "AlertData"

# 스레드 간 데이터 전달을 위한 전역 큐
MESSAGE_QUEUE = queue.Queue()

# --- 페이지 설정 ---
st.set_page_config(page_title="안전 모니터링 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링")
logger.info("================ 스트림릿 앱 시작 ================")

# --- MongoDB & MQTT 클라이언트 연결 ---
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
def start_mqtt_client():
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
                MESSAGE_QUEUE.put(data)
                logger.info("유효한 메시지를 큐에 추가했습니다.")
            else:
                logger.warning(f"메시지 형식 오류 (필수 키 누락): {data}")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"MQTT 메시지 처리 중 오류 발생: {e}")

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

# --- 클라이언트 실행 및 세션 상태 초기화 ---
db_collection = get_db_collection()
mqtt_client = start_mqtt_client()

if "latest_alerts" not in st.session_state:
    st.session_state.latest_alerts = []
if "current_status" not in st.session_state:
    st.session_state.current_status = {"message": "데이터 수신 대기 중...", "timestamp": "N/A"}

# --- 메인 로직 ---
if db_collection is not None:
    while not MESSAGE_QUEUE.empty():
        msg = MESSAGE_QUEUE.get()
        logger.info(f"큐에서 메시지 처리 시작: {msg.get('type')}")
        
        if msg.get("type") == "normal":
            logger.info("'normal' 타입 메시지입니다. 현재 상태를 업데이트합니다.")
            st.session_state.current_status = msg
            continue

        if 'source_ip' in msg:
            del msg['source_ip']
            logger.info("'source_ip' 필드를 제거했습니다.")

        try:
            msg['timestamp'] = datetime.datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            msg['timestamp'] = datetime.datetime.now()

        st.session_state.latest_alerts.insert(0, msg)
        if len(st.session_state.latest_alerts) > 100:
            st.session_state.latest_alerts.pop()
        logger.info(f"UI에 메시지를 즉시 반영했습니다: {msg.get('type')}")
        
        try:
            db_collection.insert_one(msg)
            # [핵심 수정] 터미널 로그와 함께, 화면에도 저장 성공 알림을 띄웁니다.
            logger.info(f"메시지를 MongoDB에 성공적으로 저장했습니다.")
            alert_type = msg.get("type", "알 수 없음")
            st.toast(f"✅ '{alert_type}' 경보가 DB에 저장되었습니다.", icon="💾")
        except Exception as e:
            st.warning(f"DB 저장 실패! 화면에는 표시됩니다. ({e})")
            logger.error(f"MongoDB 저장 실패: {e}")

if not st.session_state.latest_alerts and db_collection is not None:
    try:
        logger.info("초기 데이터 로드를 위해 DB를 조회합니다...")
        query = {"type": {"$ne": "normal"}}
        alerts = list(db_collection.find(query).sort("timestamp", pymongo.DESCENDING).limit(5))
        st.session_state.latest_alerts = alerts
        logger.info(f"초기 데이터 {len(alerts)}건을 DB에서 로드했습니다.")
    except Exception as e:
        st.error(f"초기 데이터 로드 실패: {e}")
        logger.error(f"초기 데이터 로드 실패: {e}")

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
        use_container_width=True,
        hide_index=True
    )

st_autorefresh(interval=2000, key="ui_refresher")
