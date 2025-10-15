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
import os
import base64

# --- 로거 설정 ---
# 로그 메시지를 표준 출력으로 보내어 터미널이나 로그 파일에서 확인할 수 있도록 설정합니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# --- 설정 (st.secrets 에서 가져옴) ---
# .streamlit/secrets.toml 파일에서 보안 정보를 안전하게 불러옵니다.
try:
    # 안전 모니터링 대시보드용 설정
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

    # 도로 균열 감지 대시보드용 설정
    CRACK_MONGO_URI = st.secrets["CRACK_MONGO_URI"]
    CRACK_DB_NAME = "crack_monitor"
    CRACK_COLLECTION_NAME = "crack_results"

    # 공통 센서 경고 기준 설정
    LOG_FILE = "sensor_logs.txt"
    OXYGEN_SAFE_MIN = 19.5
    OXYGEN_SAFE_MAX = 23.5
    NO2_WARN_LIMIT = 3.0
    NO2_DANGER_LIMIT = 5.0
except KeyError as e:
    st.error(f"st.secrets에 필수 설정이 누락되었습니다: {e}. secrets.toml 파일을 확인해주세요.", icon="🚨")
    st.stop()

# ==================================
# 캐시 리소스 (앱 재실행 시에도 유지)
# ==================================
@st.cache_resource
def get_alerts_queue():
    """안전 경보 메시지를 위한 스레드-안전 큐를 생성합니다."""
    return queue.Queue()

@st.cache_resource
def get_sensors_queue():
    """센서 데이터 메시지를 위한 스레드-안전 큐를 생성합니다."""
    return queue.Queue()

@st.cache_resource
def get_mongo_collections():
    """두 개의 MongoDB 데이터베이스에 연결하고 컬렉션 객체들을 반환합니다."""
    collections = {}
    try:
        # 1. 안전 모니터링 DB 연결
        logging.info("안전 모니터링 MongoDB에 연결을 시도합니다...")
        safety_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        safety_client.admin.command('ping')
        logging.info("✅ 안전 모니터링 MongoDB 연결 성공.")
        collections["alerts"] = safety_client[ALERTS_DB_NAME][ALERTS_COLLECTION_NAME]
        collections["sensors"] = safety_client[SENSORS_DB_NAME][SENSORS_COLLECTION_NAME]

        # 2. 도로 균열 감지 DB 연결
        logging.info("도로 균열 감지 MongoDB에 연결을 시도합니다...")
        crack_client = pymongo.MongoClient(CRACK_MONGO_URI, serverSelectionTimeoutMS=5000)
        crack_client.admin.command('ping')
        logging.info("✅ 도로 균열 감지 MongoDB 연결 성공.")
        collections["crack"] = crack_client[CRACK_DB_NAME][CRACK_COLLECTION_NAME]

        return collections
    except Exception as e:
        st.error(f"❌ MongoDB 연결 실패: {e}", icon="🚨")
        logging.error(f"MongoDB 연결 실패: {e}")
        return None

@st.cache_resource
def start_mqtt_clients():
    """안전 및 센서 데이터 수신을 위한 MQTT 클라이언트를 시작합니다."""
    clients = {}

    # 1. 안전 모니터링 클라이언트 (WebSockets)
    alerts_queue = get_alerts_queue()
    def on_connect_alerts(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logging.info(f"안전 모니터링 MQTT 연결 성공. 토픽 구독: '{ALERTS_TOPIC}'")
            client.subscribe(ALERTS_TOPIC)
        else:
            logging.error(f"안전 모니터링 MQTT 연결 실패, 코드: {rc}")

    def on_message_alerts(client, userdata, msg):
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            alerts_queue.put(data)
        except Exception as e:
            logging.error(f"ALERT MESSAGE 처리 실패. Error: {e}. Payload: {msg.payload.decode()}", exc_info=True)

    try:
        alerts_client = mqtt.Client(client_id=f"st-alerts-{random.randint(0, 1000)}", transport="websockets", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        alerts_client.username_pw_set(HIVE_USERNAME_ALERTS, HIVE_PASSWORD_ALERTS)
        alerts_client.tls_set(cert_reqs=ssl.CERT_NONE)
        alerts_client.on_connect = on_connect_alerts
        alerts_client.on_message = on_message_alerts
        alerts_client.connect(HIVE_BROKER, ALERTS_PORT, 60)
        alerts_client.loop_start()
        clients['alerts'] = alerts_client
    except Exception as e:
        st.error(f"안전 모니터링 MQTT 연결 실패: {e}", icon="🚨")

    # 2. 센서 모니터링 클라이언트 (TLS)
    sensors_queue = get_sensors_queue()
    def on_connect_sensors(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logging.info(f"센서 MQTT 연결 성공. 토픽 구독: '{SENSORS_TOPIC}'")
            client.subscribe(SENSORS_TOPIC)
        else:
            logging.error(f"센서 MQTT 연결 실패, 코드: {rc}")

    def on_message_sensors(client, userdata, msg):
        try:
            payload = msg.payload.decode().strip()
            sensors_queue.put(payload)
        except Exception as e:
            logging.error(f"SENSOR MESSAGE 처리 실패. Error: {e}. Payload: {msg.payload.decode()}", exc_info=True)

    try:
        sensors_client = mqtt.Client(client_id=f"st-sensors-{random.randint(0, 1000)}", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        sensors_client.username_pw_set(HIVE_USERNAME_SENSORS, HIVE_PASSWORD_SENSORS)
        sensors_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        sensors_client.on_connect = on_connect_sensors
        sensors_client.on_message = on_message_sensors
        sensors_client.connect(HIVE_BROKER, SENSORS_PORT, 60)
        sensors_client.loop_start()
        clients['sensors'] = sensors_client
    except Exception as e:
        st.error(f"센서 MQTT 연결 실패: {e}", icon="🚨")

    return clients

# ==================================
# Streamlit 앱 클래스
# ==================================
class UnifiedDashboard:
    """통합 모니터링 대시보드 Streamlit 앱"""

    def __init__(self):
        """앱 초기화"""
        st.set_page_config(page_title="통합 모니터링 대시보드", layout="wide")
        self.collections = get_mongo_collections()
        self.clients = start_mqtt_clients()
        self.alerts_queue = get_alerts_queue()
        self.sensors_queue = get_sensors_queue()
        self._initialize_state()

    def _initialize_state(self):
        """세션 상태 변수 초기화"""
        defaults = {
            'page': 'main',
            'latest_alerts': [],
            'current_status': {"message": "데이터 수신 대기 중...", "timestamp": "N/A"},
            'sound_enabled': False,
            'live_df': pd.DataFrame(),
            'last_sensor_values': {"CH4": 0.0, "EtOH": 0.0, "H2": 0.0, "NH3": 0.0, "CO": 0.0},
            'sound_primed': False,
            'play_sound_trigger': None,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def _process_queues(self):
        """MQTT 메시지 큐를 처리하여 데이터를 업데이트합니다."""
        # 1. 안전 경보 큐 처리
        while not self.alerts_queue.empty():
            msg = self.alerts_queue.get()
            alert_type = msg.get("type")
            if alert_type in ["fire", "safety"]:
                if st.session_state.get('sound_enabled', False):
                    st.session_state.play_sound_trigger = alert_type
                st.toast(f"🔥 긴급: 화재 경보 발생!" if alert_type == "fire" else f"⚠️ 주의: 안전조끼 미착용 감지!", icon="🔥" if alert_type == "fire" else "⚠️")

            if msg.get("type") == "normal":
                st.session_state.current_status = msg
                continue

            try:
                msg['timestamp'] = datetime.strptime(msg['timestamp'], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                msg['timestamp'] = datetime.now()

            st.session_state.latest_alerts.insert(0, msg)
            if len(st.session_state.latest_alerts) > 100:
                st.session_state.latest_alerts.pop()
            if self.collections:
                self.collections['alerts'].insert_one(msg.copy())

        # 2. 센서 데이터 큐 처리
        sensor_keys = ["CH4", "EtOH", "H2", "NH3", "CO", "NO2", "Oxygen", "Distance", "Flame"]
        new_data = []
        while not self.sensors_queue.empty():
            payload = self.sensors_queue.get()
            try:
                values = [float(v.strip()) for v in payload.split(',')]
                if len(values) != len(sensor_keys):
                    logging.warning(f"센서 데이터 값 개수 불일치. 페이로드: {payload}")
                    continue

                data_dict = dict(zip(sensor_keys, values))
                data_dict['Flame'] = int(data_dict['Flame'])
                data_dict['timestamp'] = datetime.now(timezone.utc)
                self._check_and_trigger_sensor_alerts(data_dict)
                new_data.append(data_dict)
                if self.collections:
                    self.collections['sensors'].insert_one(data_dict.copy())
            except (ValueError, IndexError) as e:
                logging.warning(f"센서 데이터 파싱 오류: {e} - 페이로드: {payload}")

        if new_data:
            new_df = pd.DataFrame(new_data)
            new_df['timestamp'] = pd.to_datetime(new_df['timestamp']).dt.tz_convert('UTC')
            st.session_state.live_df = pd.concat([st.session_state.live_df, new_df], ignore_index=True)
            if len(st.session_state.live_df) > 1000:
                st.session_state.live_df = st.session_state.live_df.iloc[-1000:]

    def _check_and_trigger_sensor_alerts(self, data_dict):
        """센서 데이터를 확인하고 조건에 따라 경고를 발생시킵니다."""
        def log_alert(message):
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as log_file:
                    log_file.write(f"{datetime.now(timezone.utc).isoformat()} - {message}\n")
            except Exception as e:
                logging.error(f"로그 파일 작성 오류: {e}")

        if data_dict.get("Flame") == 0:
            log_alert("🔥 긴급: 불꽃 감지됨!")
            st.toast("🔥 긴급: 불꽃 감지됨!", icon="🔥")
            if st.session_state.sound_enabled:
                st.session_state.play_sound_trigger = 'fire'
        # ... (기타 센서 알림 로직)
        
    def _render_header_and_nav(self):
        """페이지 상단의 제목과 네비게이션 버튼을 렌더링합니다."""
        st.title("🛡️ 통합 모니터링 대시보드")
        pages = {
            'main': '🏠 안전 모니터링',
            'sensor_dashboard': '📈 실시간 센서', 
            'sensor_log': '📜 센서 로그',
            'crack_monitor': '🛣️ 도로 균열 감지'
        }
        cols = st.columns(len(pages))
        for i, (page_key, page_title) in enumerate(pages.items()):
            with cols[i]:
                if st.button(page_title, use_container_width=True, type="primary" if st.session_state.page == page_key else "secondary"):
                    st.session_state.page = page_key
                    st.rerun()
        st.divider()

    def _render_sidebar(self):
        """사이드바의 설정 옵션을 렌더링합니다."""
        with st.sidebar:
            st.header("⚙️ 설정")

            if st.session_state.page == 'crack_monitor':
                st.subheader("도로 균열 필터")
                st.session_state.crack_limit = st.slider("표시할 최근 항목 수", 1, 100, st.session_state.get('crack_limit', 10))
                if st.button("새로고침 🔄"):
                    st.rerun()
                st.divider()

            st.subheader("알림음 설정")
            if not st.session_state.sound_primed:
                if st.button("🔔 알림음 활성화 (최초 1회 클릭)"):
                    st.session_state.sound_enabled = True
                    st.session_state.sound_primed = True
                    st.rerun()
            else:
                st.session_state.sound_enabled = st.toggle("알림음 활성화/비활성화", value=st.session_state.sound_enabled)
            
            st.success("알림음 활성화 상태") if st.session_state.sound_enabled else st.warning("알림음 비활성화 상태")

    def _render_main_page(self):
        """메인 대시보드 페이지(안전 모니터링)를 렌더링합니다."""
        st.header("항만시설 현장 안전 모니터링")
        if not st.session_state.latest_alerts and self.collections:
            try:
                query = {"type": {"$ne": "normal"}}
                alerts = list(self.collections['alerts'].find(query).sort("timestamp", pymongo.DESCENDING).limit(5))
                st.session_state.latest_alerts = alerts
            except Exception as e:
                st.error(f"초기 경보 데이터 로드 실패: {e}")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("📡 시스템 현재 상태")
            status_message = st.session_state.current_status.get("message", "상태 정보 없음")
            status_time = st.session_state.current_status.get("timestamp", "N/A")
            st.info(f"{status_message} (마지막 신호: {status_time})")
        with col2:
            st.subheader("MQTT 연결 상태")
            client = self.clients.get('alerts')
            st.success("🟢 실시간 수신 중") if client and client.is_connected() else st.error("🔴 연결 끊김")

        st.divider()
        st.subheader("🚨 최근 경보 내역")
        if not st.session_state.latest_alerts:
            st.info("수신된 경보가 없습니다.")
        else:
            df = pd.DataFrame(st.session_state.latest_alerts)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
            display_df = df.rename(columns={"timestamp": "발생 시각", "type": "유형", "message": "메시지"})
            st.dataframe(display_df[['발생 시각', '유형', '메시지']].sort_values(by="발생 시각", ascending=False), use_container_width=True, hide_index=True)

    def _render_sensor_dashboard(self):
        """실시간 센서 모니터링 페이지를 렌더링합니다."""
        st.header("실시간 센서 모니터링")
        # ... (이전 코드와 로직 동일)
        
    def _render_sensor_log_page(self):
        """센서 이벤트 로그 페이지를 렌더링합니다."""
        st.header("센서 이벤트 로그")
        # ... (이전 코드와 로직 동일)

    def _render_crack_monitor_page(self):
        """도로 균열 감지 대시보드 페이지를 렌더링합니다."""
        st.header(f"최근 감지된 균열 목록 (상위 {st.session_state.get('crack_limit', 10)}개)")

        if self.collections and 'crack' in self.collections:
            collection = self.collections['crack']
            limit = st.session_state.get('crack_limit', 10)
            try:
                for doc in collection.find({}).sort("timestamp", -1).limit(limit):
                    timestamp_local = doc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    device_name = doc.get('source_device', 'N/A')
                    num_detections = len(doc.get('detections', []))

                    with st.expander(f"**감지 시간:** {timestamp_local} | **장치:** {device_name} | **균열 수:** {num_detections}"):
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            if 'annotated_image_base64' in doc:
                                img_bytes = base64.b64decode(doc['annotated_image_base64'])
                                st.image(img_bytes, caption="감지 결과 이미지", use_column_width=True)
                        with col2:
                            st.subheader("상세 감지 정보")
                            detections = doc.get('detections', [])
                            if not detections:
                                st.info("상세 감지 정보가 없습니다.")
                            else:
                                for i, d in enumerate(detections):
                                    st.metric(label=f"#{i+1}: {d.get('class_name', 'N/A')}", value=f"{d.get('confidence', 0):.2%}")
                                    st.code(f"Box: {[int(c) for c in d.get('box_xyxy', [])]}", language="text")
                            st.caption(f"DB ID: {doc.get('_id', 'N/A')}")
            except Exception as e:
                st.error(f"도로 균열 데이터 로딩 중 오류 발생: {e}")
        else:
            st.warning("데이터베이스에 연결할 수 없어 도로 균열 데이터를 표시할 수 없습니다.")

    def _handle_audio_playback(self):
        """경고음 재생을 처리합니다."""
        st.html("""
            <audio id="fire-alert-sound" preload="auto"></audio>
            <audio id="safety-alert-sound" preload="auto"></audio>
        """)
        # 경고음 파일 경로는 실제 환경에 맞게 설정 필요
        # 예: <source src="https://.../fire_alert.mp3" type="audio/mpeg">
        
        if trigger := st.session_state.play_sound_trigger:
            sound_id = 'fire-alert-sound' if trigger == 'fire' else 'safety-alert-sound'
            st.html(f"<script>document.getElementById('{sound_id}').play();</script>")
            st.session_state.play_sound_trigger = None

    def run(self):
        """Streamlit 앱을 실행합니다."""
        self._render_header_and_nav()
        self._render_sidebar()
        self._process_queues()

        page_map = {
            'main': self._render_main_page,
            'sensor_dashboard': self._render_sensor_dashboard,
            'sensor_log': self._render_sensor_log_page,
            'crack_monitor': self._render_crack_monitor_page
        }
        render_function = page_map.get(st.session_state.page, self._render_main_page)
        render_function()
        
        self._handle_audio_playback()
        st_autorefresh(interval=2000, key="refresher")

if __name__ == "__main__":
    app = UnifiedDashboard()
    app.run()

