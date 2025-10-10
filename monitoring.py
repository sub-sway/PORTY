import streamlit as st
import paho.mqtt.client as mqtt
import pymongo
import json
import ssl
import queue
import pandas as pd
from datetime import datetime, timedelta, timezone
import random
from streamlit_autorefresh import st_autorefresh
import logging
import sys
import plotly.express as px
import threading
from playsound import playsound
from pathlib import Path
import os

# --- 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)

# --- 경로 설정 (배포 환경 호환성 강화) ---
BASE_DIR = Path(__file__).parent if "__file__" in locals() else Path.cwd()
SOUNDS_DIR = BASE_DIR / "sounds"
FIRE_SOUND_PATH = SOUNDS_DIR / "fire_cut_mp3.mp3"
SAFETY_SOUND_PATH = SOUNDS_DIR / "Stranger_cut_mp3.mp3"
LOG_FILE = BASE_DIR / "sensor_logs.txt"

# --- secrets.toml 설정 가져오기 ---
try:
    HIVE_BROKER = st.secrets["HIVE_BROKER"]
    MONGO_URI = st.secrets["MONGO_URI"]
    HIVE_USERNAME_ALERTS = st.secrets["HIVE_USERNAME_ALERTS"]
    HIVE_PASSWORD_ALERTS = st.secrets["HIVE_PASSWORD_ALERTS"]
    ALERTS_PORT = 8884
    ALERTS_TOPIC = "robot/alerts"
    ALERTS_DB_NAME = "AlertDB"
    ALERTS_COLLECTION_NAME = "AlertData"
    HIVE_USERNAME_SENSORS = st.secrets["HIVE_USERNAME_SENSORS"]
    HIVE_PASSWORD_SENSORS = st.secrets["HIVE_PASSWORD_SENSORS"]
    SENSORS_PORT = 8883
    SENSORS_TOPIC = "multiSensor/numeric"
    SENSORS_DB_NAME = "SensorDB"
    SENSORS_COLLECTION_NAME = "SensorData"
    OXYGEN_SAFE_MIN = 19.5
    OXYGEN_SAFE_MAX = 23.5
    NO2_WARN_LIMIT = 3.0
    NO2_DANGER_LIMIT = 5.0
except KeyError as e:
    st.error(f"⚠️ st.secrets에 {e} 값이 없습니다. secrets.toml을 확인하세요.", icon="🚨")
    st.stop()

# ==================================
# 캐시 리소스 (앱 재실행 시에도 유지)
# ==================================
@st.cache_resource
def get_alerts_queue():
    return queue.Queue()

@st.cache_resource
def get_sensors_queue():
    return queue.Queue()

@st.cache_resource
def get_mongo_collections():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        client.server_info()
        alerts_db = client[ALERTS_DB_NAME]
        sensors_db = client[SENSORS_DB_NAME]
        return {
            "alerts": alerts_db[ALERTS_COLLECTION_NAME],
            "sensors": sensors_db[SENSORS_COLLECTION_NAME],
        }
    except Exception as e:
        logging.error(f"MongoDB 연결 실패: {e}")
        return None

@st.cache_resource
def start_mqtt_clients():
    clients = {}
    alerts_queue = get_alerts_queue()

    def on_connect_alerts(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logging.info(f"MQTT 연결 성공: {ALERTS_TOPIC}")
            client.subscribe(ALERTS_TOPIC)
        else:
            logging.error(f"MQTT 연결 실패: 코드 {rc}")

    def on_message_alerts(client, userdata, msg):
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            if all(k in data for k in ["type", "message", "timestamp"]):
                alerts_queue.put(data)
        except Exception as e:
            logging.error(f"MQTT 메시지 처리 오류: {e}")

    try:
        alerts_client = mqtt.Client(
            client_id=f"st-alerts-{random.randint(0, 999)}",
            transport="websockets",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        alerts_client.username_pw_set(HIVE_USERNAME_ALERTS, HIVE_PASSWORD_ALERTS)
        alerts_client.tls_set(cert_reqs=ssl.CERT_NONE)
        alerts_client.on_connect = on_connect_alerts
        alerts_client.on_message = on_message_alerts
        alerts_client.connect(HIVE_BROKER, ALERTS_PORT, 60)
        alerts_client.loop_start()
        clients["alerts"] = alerts_client
        logging.info("MQTT 클라이언트 시작됨.")
    except Exception as e:
        logging.error(f"MQTT 연결 실패: {e}")

    return clients


# ==================================
# Streamlit 앱 클래스
# ==================================
class UnifiedDashboard:
    def __init__(self):
        st.set_page_config(page_title="통합 안전 모니터링 대시보드", layout="wide")
        self.collections = get_mongo_collections()
        self.clients = start_mqtt_clients()
        self.alerts_queue = get_alerts_queue()
        self.sensors_queue = get_sensors_queue()
        self._initialize_state()

    def _initialize_state(self):
        defaults = {
            "page": "main",
            "latest_alerts": [],
            "current_status": {"message": "데이터 수신 대기 중...", "timestamp": "N/A"},
            "live_df": pd.DataFrame(),
            "last_sensor_values": {},
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    def _play_local_sound(self, sound_path):
        """Jetson/서버에서 직접 음성 재생"""
        if sound_path.exists():
            def play_thread():
                try:
                    playsound(str(sound_path))
                except Exception as e:
                    logging.error(f"음성 재생 실패: {e}")
            threading.Thread(target=play_thread, daemon=True).start()
        else:
            logging.warning(f"⚠️ 파일 없음: {sound_path}")

    def _process_queues(self):
        """MQTT 수신 메시지 처리"""
        while not self.alerts_queue.empty():
            msg = self.alerts_queue.get()
            alert_type = msg.get("type")

            if alert_type in ["fire", "safety"]:
                if alert_type == "fire":
                    st.toast("🔥 화재 경보 발생!", icon="🔥")
                    self._play_local_sound(FIRE_SOUND_PATH)
                elif alert_type == "safety":
                    st.toast("⚠️ 안전조끼 미착용 감지!", icon="⚠️")
                    self._play_local_sound(SAFETY_SOUND_PATH)

            if msg.get("type") == "normal":
                st.session_state.current_status = msg
                continue

            msg["timestamp"] = datetime.now()
            st.session_state.latest_alerts.insert(0, msg)
            if len(st.session_state.latest_alerts) > 100:
                st.session_state.latest_alerts.pop()

            if self.collections:
                try:
                    self.collections["alerts"].insert_one(msg)
                except Exception as e:
                    logging.error(f"MongoDB 저장 실패: {e}")

    def _render_header_and_nav(self):
        st.title("🛡️ 통합 안전 모니터링 대시보드")
        cols = st.columns(3)
        with cols[0]:
            if st.button("🏠 메인 대시보드", use_container_width=True):
                st.session_state.page = "main"
        with cols[1]:
            if st.button("📈 센서 모니터링", use_container_width=True):
                st.session_state.page = "sensor_dashboard"
        with cols[2]:
            if st.button("📜 로그", use_container_width=True):
                st.session_state.page = "sensor_log"
        st.divider()

    def _render_sidebar(self):
        with st.sidebar:
            st.header("⚙️ 설정")
            st.success("Jetson/서버 현장 알림음은 자동으로 재생됩니다 🔊")
            st.info("이 Streamlit 인터페이스는 원격 대시보드 용입니다.")
            st.divider()

    def _render_main_page(self):
        st.header("항만시설 현장 안전 모니터링")
        col1, col2 = st.columns([3, 1])

        with col1:
            msg = st.session_state.current_status.get("message", "상태 정보 없음")
            t = st.session_state.current_status.get("timestamp", "N/A")
            st.info(f"{msg} (마지막 신호: {t})")

        with col2:
            client = self.clients.get("alerts")
            if client and client.is_connected():
                st.success("🟢 MQTT 연결 중")
            else:
                st.error("🔴 연결 끊김")

        st.divider()
        st.subheader("🚨 최근 경보 내역")
        if not st.session_state.latest_alerts:
            st.info("수신된 경보가 없습니다.")
        else:
            df = pd.DataFrame(st.session_state.latest_alerts)
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Seoul")
            st.dataframe(df[["timestamp", "type", "message"]].rename(columns={
                "timestamp": "발생 시각", "type": "유형", "message": "메시지"
            }), use_container_width=True, hide_index=True)

    def _render_sensor_dashboard(self):
        st.header("📡 센서 모니터링 (준비 중)")
        st.info("센서 데이터 수신 대기 중...")

    def _render_sensor_log_page(self):
        st.header("📜 센서 이벤트 로그")
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                st.text_area("로그 내용", "".join(lines), height=300)
                if st.button("🧹 로그 삭제"):
                    LOG_FILE.unlink()
                    st.success("삭제 완료")
                    st.rerun()
            else:
                st.info("로그가 비어 있습니다.")
        else:
            st.info("아직 로그 파일이 생성되지 않았습니다.")

    def run(self):
        self._render_header_and_nav()
        self._render_sidebar()
        self._process_queues()

        page = st.session_state.page
        if page == "main":
            self._render_main_page()
        elif page == "sensor_dashboard":
            self._render_sensor_dashboard()
        elif page == "sensor_log":
            self._render_sensor_log_page()

        st_autorefresh(interval=2000, key="refresh")

# --- 메인 실행 ---
if __name__ == "__main__":
    app = UnifiedDashboard()
    app.run()
