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
# MQTT 설정
HIVE_BROKER = st.secrets["HIVE_BROKER"]
HIVE_USERNAME = st.secrets["HIVE_USERNAME"]
HIVE_PASSWORD = st.secrets["HIVE_PASSWORD"]
HIVE_PORT = 8884
HIVE_TOPIC = "robot/alerts"

# MongoDB 설정 (제공된 정보로 업데이트)
MONGO_URI = st.secrets["MONGO_URI"]
DB_NAME = "AlertDB"
COLLECTION_NAME = "AlertData"

# 스레드 간 데이터 전달을 위한 전역 큐
MESSAGE_QUEUE = queue.Queue()

# --- 페이지 설정 ---
st.set_page_config(page_title="안전 모니터링 대시보드", layout="wide")
st.title("🛡️ 항만시설 현장 안전 모니터링")

# --- MongoDB & MQTT 클라이언트 연결 (Singleton으로 캐싱) ---
@st.singleton
def get_db_collection():
    try:
        client = pymongo.MongoClient(MONGO_URI)
        client.server_info()
        db = client[DB_NAME]
        return db[COLLECTION_NAME]
    except Exception as e:
        st.error(f"MongoDB 연결 실패: {e}")
        return None

@st.singleton
def start_mqtt_client():
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(HIVE_TOPIC)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            # MongoDB는 UTC datetime 객체를 선호합니다.
            data['timestamp'] = datetime.datetime.fromisoformat(data['timestamp'])
            MESSAGE_QUEUE.put(data)
        except Exception:
            pass # 잘못된 형식의 메시지는 무시

    client_id = f"streamlit-listener-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, transport="websockets")
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

if "latest_alerts" not in st.session_state:
    st.session_state.latest_alerts = []

# --- 메인 로직 ---
# 1. 큐에서 새 메시지를 가져와 DB에 저장하고, 화면에 표시할 리스트에 추가
if db_collection:
    while not MESSAGE_QUEUE.empty():
        msg = MESSAGE_QUEUE.get()
        try:
            db_collection.insert_one(msg)
            # 최신 메시지를 리스트 맨 앞에 추가
            st.session_state.latest_alerts.insert(0, msg)
            # 리스트 길이를 100으로 제한
            if len(st.session_state.latest_alerts) > 100:
                st.session_state.latest_alerts.pop()
        except Exception as e:
            st.warning(f"DB 저장 실패: {e}")

# 2. (선택사항) 앱 시작 시 DB에서 최근 데이터 일부를 미리 로드
if not st.session_state.latest_alerts and db_collection:
    try:
        alerts = list(db_collection.find().sort("timestamp", pymongo.DESCENDING).limit(50))
        st.session_state.latest_alerts = alerts
    except Exception as e:
        st.error(f"초기 데이터 로드 실패: {e}")

# --- UI 표시 ---
if mqtt_client and mqtt_client.is_connected():
    st.success("🟢 실시간 수신 중 (MQTT Connected)")
else:
    st.error("🔴 MQTT 연결 끊김")

st.divider()
st.subheader("🚨 최근 경보 내역")

if not st.session_state.latest_alerts:
    st.info("수신된 경보가 없습니다.")
else:
    # Pandas DataFrame으로 변환하여 표시
    df = pd.DataFrame(st.session_state.latest_alerts)
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('Asia/Seoul')
    
    display_df = df.rename(columns={
        "timestamp": "발생 시각", "type": "유형",
        "message": "메시지", "source_ip": "발생지 IP"
    })
    
    # 시간순으로 정렬하여 표시
    st.dataframe(
        display_df[['발생 시각', '유형', '메시지', '발생지 IP']].sort_values(by="발생 시각", ascending=False),
        use_container_width=True,
        hide_index=True
    )

# 1초마다 화면을 새로고침하여 최신 데이터를 반영
st_autorefresh(interval=1000, key="ui_refresher")

