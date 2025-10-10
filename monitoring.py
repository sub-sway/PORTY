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
from playsound import playsound
import threading

# --- 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# --- 알림음 파일 경로 설정 ---
SOUNDS_DIR = os.path.join(os.getcwd(), "sounds")
FIRE_SOUND_PATH = os.path.join(SOUNDS_DIR, "fire_cut_mp3.mp3")
SAFETY_SOUND_PATH = os.path.join(SOUNDS_DIR, "Stranger_cut_mp3.mp3")

# --- 설정 (st.secrets 에서 가져옴) ---
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
    return queue.Queue()
@st.cache_resource
def get_sensors_queue():
    return queue.Queue()
@st.cache_resource
def get_mongo_collections():
    try:
        logging.info("MongoDB에 연결을 시도합니다...")
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        logging.info("MongoDB 연결 성공.")
        alerts_db = client[ALERTS_DB_NAME]
        sensors_db = client[SENSORS_DB_NAME]
        return {
            "alerts": alerts_db[ALERTS_COLLECTION_NAME],
            "sensors": sensors_db[SENSORS_COLLECTION_NAME]
        }
    except Exception as e:
        st.error(f"MongoDB 연결 실패: {e}", icon="🚨")
        logging.error(f"MongoDB 연결 실패: {e}")
        return None
@st.cache_resource
def start_mqtt_clients():
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
            if all(key in data for key in ['type', 'message', 'timestamp']):
                alerts_queue.put(data)
        except Exception as e:
            logging.error(f"안전 모니터링 메시지 처리 중 오류: {e}")

    try:
        alerts_client = mqtt.Client(client_id=f"st-alerts-{random.randint(0, 1000)}", transport="websockets", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        alerts_client.username_pw_set(HIVE_USERNAME_ALERTS, HIVE_PASSWORD_ALERTS)
        alerts_client.tls_set(cert_reqs=ssl.CERT_NONE)
        alerts_client.on_connect = on_connect_alerts
        alerts_client.on_message = on_message_alerts
        alerts_client.connect(HIVE_BROKER, ALERTS_PORT, 60)
        alerts_client.loop_start()
        clients['alerts'] = alerts_client
        logging.info("안전 모니터링 MQTT 클라이언트 시작됨.")
    except Exception as e:
        st.error(f"안전 모니터링 MQTT 연결 실패: {e}", icon="🚨")
        logging.error(f"안전 모니터링 MQTT 연결 실패: {e}")

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
            sensors_queue.put(msg.payload.decode().strip())
        except Exception as e:
            logging.error(f"센서 메시지 수신 중 오류: {e}")

    try:
        sensors_client = mqtt.Client(client_id=f"st-sensors-{random.randint(0, 1000)}", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        sensors_client.username_pw_set(HIVE_USERNAME_SENSORS, HIVE_PASSWORD_SENSORS)
        sensors_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        sensors_client.on_connect = on_connect_sensors
        sensors_client.on_message = on_message_sensors
        sensors_client.connect(HIVE_BROKER, SENSORS_PORT, 60)
        sensors_client.loop_start()
        clients['sensors'] = sensors_client
        logging.info("센서 MQTT 클라이언트 시작됨.")
    except Exception as e:
        st.error(f"센서 MQTT 연결 실패: {e}", icon="🚨")
        logging.error(f"센서 MQTT 연결 실패: {e}")

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
        while not self.alerts_queue.empty():
            msg = self.alerts_queue.get()

            alert_type = msg.get("type")
            if alert_type in ["fire", "safety"]:
                # 알림음 재생 (별도 스레드로 실행)
                def play_alert():
                    try:
                        if alert_type == "fire":
                            playsound("sounds/fire_cut_mp3.mp3")
                        elif alert_type == "safety":
                            playsound("sounds/Stranger_cut_mp3.mp3")
                    except Exception as e:
                        print(f"❌ 소리 재생 실패: {e}")

                threading.Thread(target=play_alert, daemon=True).start()

                if alert_type == "fire":
                    st.toast("🔥 긴급: 화재 경보 발생!", icon="🔥")
                elif alert_type == "safety":
                    st.toast("⚠️ 주의: 안전조끼 미착용 감지!", icon="⚠️")

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
                try:
                    self.collections['alerts'].insert_one(msg)
                except Exception as e:
                    logging.error(f"MongoDB 저장 실패 (alerts): {e}")


    def _check_and_trigger_sensor_alerts(self, data_dict):
        def log_alert(message):
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as log_file:
                    log_file.write(f"{datetime.now(timezone.utc).isoformat()} - {message}\n")
            except Exception as e:
                logging.error(f"로그 파일 작성 오류: {e}")

        def trigger_ui_alert(message, icon, sound_type):
            st.toast(message, icon=icon)
            if st.session_state.sound_enabled:
                st.session_state.play_sound_trigger = sound_type

        if data_dict.get("Flame") == 0:
            msg = "🔥 긴급: 불꽃 감지됨! 즉시 확인이 필요합니다!"
            log_alert(msg)
            trigger_ui_alert(msg, "🔥", "fire")
        
        oxygen_val = data_dict.get("Oxygen")
        if oxygen_val is not None and not (OXYGEN_SAFE_MIN <= oxygen_val <= OXYGEN_SAFE_MAX):
            msg = f"🟠 산소 농도 경고! 현재 값: {oxygen_val:.1f}%"
            log_alert(msg)
            
        no2_val = data_dict.get("NO2")
        if no2_val is not None:
            if no2_val >= NO2_DANGER_LIMIT:
                msg = f"🔴 이산화질소(NO2) 위험! 현재 값: {no2_val:.3f} ppm"
                log_alert(msg)
            elif no2_val >= NO2_WARN_LIMIT:
                msg = f"🟡 이산화질소(NO2) 주의! 현재 값: {no2_val:.3f} ppm"
                log_alert(msg)
        
        for sensor in ["CH4", "EtOH", "H2", "NH3", "CO"]:
            new_value = data_dict.get(sensor, 0.0)
            if new_value > 0 and st.session_state.last_sensor_values.get(sensor, 0.0) == 0:
                log_alert(f"🟡 {sensor} 가스 감지됨! 현재 값: {new_value:.3f}")
            st.session_state.last_sensor_values[sensor] = new_value

    def _render_header_and_nav(self):
        st.title("🛡️ 통합 안전 모니터링 대시보드")
        cols = st.columns(3)
        with cols[0]:
            if st.button("🏠 메인 대시보드", width="stretch", type="primary" if st.session_state.page == 'main' else "secondary"):
                st.session_state.page = 'main'
        with cols[1]:
            if st.button("📈 실시간 센서 모니터링", width="stretch", type="primary" if st.session_state.page == 'sensor_dashboard' else "secondary"):
                st.session_state.page = 'sensor_dashboard'
        with cols[2]:
            if st.button("📜 센서 이벤트 로그", width="stretch", type="primary" if st.session_state.page == 'sensor_log' else "secondary"):
                st.session_state.page = 'sensor_log'
        st.divider()
    
    def _render_sidebar(self):
        with st.sidebar:
            st.header("⚙️ 설정")
            st.info("브라우저 정책으로 인해, 알림음을 들으시려면 먼저 아래 버튼을 눌러 오디오를 활성화해야 합니다.")
            
            if not st.session_state.sound_primed:
                if st.button("🔔 알림음 활성화 (최초 1회 클릭)", width="stretch"):
                    st.session_state.sound_enabled = True
                    st.session_state.sound_primed = True
                    
                    st.html("""
                        <script>
                            var fireSound = document.getElementById('fire-alert-sound');
                            var safetySound = document.getElementById('safety-alert-sound');
                            if (fireSound && safetySound) {
                                fireSound.play().then(() => { fireSound.pause(); fireSound.currentTime = 0; });
                                safetySound.play().then(() => { safetySound.pause(); safetySound.currentTime = 0; });
                            }
                        </script>
                    """)
                    st.success("✅ 알림음이 활성화되었습니다.")
                    st.rerun()
            else:
                st.session_state.sound_enabled = st.toggle(
                    "알림음 활성화/비활성화", 
                    value=st.session_state.sound_enabled
                )

            if st.session_state.sound_enabled:
                st.success("알림음 활성화 상태")
            else:
                st.warning("알림음 비활성화 상태")

    def _render_main_page(self):
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
            if client and client.is_connected():
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
            display_df = df.rename(columns={"timestamp": "발생 시각", "type": "유형", "message": "메시지"})
            st.dataframe(
                display_df[['발생 시각', '유형', '메시지']].sort_values(by="발생 시각", ascending=False),
                width="stretch", hide_index=True
            )

    def _render_sensor_dashboard(self):
        st.header("실시간 센서 모니터링")
        df = st.session_state.live_df
        if df.empty and self.collections:
            try:
                records = list(self.collections['sensors'].find().sort("timestamp", -1).limit(1000))
                if records:
                    st.session_state.live_df = pd.DataFrame(reversed(records))
                    df = st.session_state.live_df
            except Exception as e:
                st.error(f"초기 센서 데이터 로드 실패: {e}")

        st.subheader("📡 실시간 수신 상태")
        status_cols = st.columns(3)
        now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
        status_cols[0].metric("현재 시간 (KST)", now_kst.strftime("%H:%M:%S"))

        if not df.empty:
            last_reception_utc = pd.to_datetime(df['timestamp'].iloc[-1])
            time_diff = datetime.now(timezone.utc) - last_reception_utc.to_pydatetime()
            status_cols[1].metric("마지막 수신 (KST)", (last_reception_utc + timedelta(hours=9)).strftime("%H:%M:%S"))
            if time_diff.total_seconds() < 10:
                status_cols[2].success("🟢 실시간 수신 중")
            else:
                status_cols[2].warning(f"🟠 {int(time_diff.total_seconds())}초 수신 없음")
        else:
            status_cols[1].metric("마지막 수신", "N/A")
            status_cols[2].info("수신 대기 중...")
        
        st.subheader("🚨 종합 현재 상태")
        if not df.empty:
            latest_data = df.iloc[-1]
            flame_detected = latest_data["Flame"] == 0
            oxygen_unsafe = not (OXYGEN_SAFE_MIN <= latest_data["Oxygen"] <= OXYGEN_SAFE_MAX)
            no2_dangerous = latest_data["NO2"] >= NO2_DANGER_LIMIT
            no2_warning = latest_data["NO2"] >= NO2_WARN_LIMIT
            
            conditions = [flame_detected, oxygen_unsafe, no2_dangerous, no2_warning]
            
            if flame_detected: st.error("🔥 불꽃 감지됨!", icon="🔥")
            if oxygen_unsafe: st.warning(f"🟠 산소 농도 경고! 현재 {latest_data['Oxygen']:.1f}%", icon="⚠️")
            if no2_dangerous: st.error(f"🔴 이산화질소(NO2) 농도 위험! 현재 {latest_data['NO2']:.3f} ppm", icon="☣️")
            elif no2_warning: st.warning(f"🟡 이산화질소(NO2) 농도 주의! 현재 {latest_data['NO2']:.3f} ppm", icon="⚠️")
            
            if not any(conditions):
                st.success("✅ 안정 범위 내에 있습니다.", icon="👍")
        else:
            st.info("데이터 수신 대기 중...")

        if not df.empty:
            st.subheader("📊 현재 센서 값")
            latest_data = df.iloc[-1]
            sensors = ["CH4", "EtOH", "H2", "NH3", "CO", "NO2", "Oxygen", "Distance", "Flame"]
            metric_cols = st.columns(5)
            for i, sensor in enumerate(sensors):
                with metric_cols[i % 5]:
                    if sensor in latest_data:
                        if sensor == "Flame":
                            state = "🔥 감지됨" if latest_data[sensor] == 0 else "🟢 정상"
                            st.metric(label="불꽃 상태", value=state)
                        else:
                            st.metric(label=f"{sensor}", value=f"{latest_data[sensor]:.3f}")
        
            st.divider()
            st.subheader("📈 센서별 실시간 변화 추세")
            sensors_for_graph = ["CH4", "EtOH", "H2", "NH3", "CO", "NO2", "Oxygen", "Distance"]
            for i in range(0, len(sensors_for_graph), 2):
                graph_cols = st.columns(2)
                for j, sensor in enumerate(sensors_for_graph[i:i+2]):
                    if sensor in df.columns:
                        with graph_cols[j]:
                            fig = px.line(df, x="timestamp", y=sensor, title=f"{sensor} 변화 추세")
                            fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                            st.plotly_chart(fig, width="stretch")

    def _render_sensor_log_page(self):
        st.header("센서 이벤트 로그")
        st.write("불꽃, 위험 가스 농도 등 주요 이벤트가 감지될 때의 기록입니다.")
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    log_lines = f.readlines()
                if log_lines:
                    log_entries = []
                    for line in reversed(log_lines):
                        if " - " in line:
                            parts = line.split(" - ", 1)
                            utc_dt = datetime.fromisoformat(parts[0])
                            kst_dt = utc_dt.astimezone(timezone(timedelta(hours=9)))
                            log_entries.append({
                                "감지 시간 (KST)": kst_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                "메시지": parts[1].strip()
                            })
                    log_df = pd.DataFrame(log_entries)
                    st.dataframe(log_df, width="stretch", hide_index=True)
                    
                    st.divider()
                    if st.button("🚨 로그 전체 삭제", type="primary"):
                        os.remove(LOG_FILE)
                        st.success("✅ 모든 로그 기록이 삭제되었습니다.")
                        st.rerun()
                else:
                    st.info("👀 로그 파일이 비어있습니다.")
            except Exception as e:
                st.error(f"로그 파일을 읽는 중 오류가 발생했습니다: {e}")
        else:
            st.info("👍 아직 감지된 이벤트가 없어 로그 파일이 생성되지 않았습니다.")

    def run(self):
        self._render_header_and_nav()
        self._render_sidebar()
        self._process_queues()

        page = st.session_state.page
        if page == 'main':
            self._render_main_page()
        elif page == 'sensor_dashboard':
            self._render_sensor_dashboard()
        elif page == 'sensor_log':
            self._render_sensor_log_page()
        
        st_autorefresh(interval=2000, key="refresher")

if __name__ == "__main__":
    app = UnifiedDashboard()
    app.run()
