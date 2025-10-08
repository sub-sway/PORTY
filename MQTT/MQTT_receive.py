import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import psutil, json, threading
import folium, random
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import paho.mqtt.client as mqtt

# -----------------------------------------
# 기본 설정
# -----------------------------------------
st.set_page_config(page_title="Arduino Sensor Dashboard", layout="wide")

# MQTT 브로커 설정 (Arduino에서 publish하는 주소)
MQTT_BROKER = "192.168.0.10"
MQTT_PORT = 1883
MQTT_TOPIC = "arduino/sensors"

# MQTT 데이터 저장용
if "latest_data" not in st.session_state:
    st.session_state.latest_data = {}
if "data" not in st.session_state:
    st.session_state.data = pd.DataFrame(columns=["CH4","CO","Oxygen","Distance","Flame"])

# -----------------------------------------
# MQTT 콜백 함수 정의
# -----------------------------------------
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        st.session_state.latest_data = data
    except Exception as e:
        print("데이터 파싱 오류:", e)

def mqtt_thread():
    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT)
        client.subscribe(MQTT_TOPIC)
        print("✅ MQTT 브로커 연결 성공")
        client.loop_forever()
    except Exception as e:
        print("❌ MQTT 연결 실패:", e)

# MQTT 수신 스레드 실행
threading.Thread(target=mqtt_thread, daemon=True).start()

# -----------------------------------------
# Streamlit UI
# -----------------------------------------
if "page" not in st.session_state:
    st.session_state.page = 1

st_autorefresh(interval=2000, key="refresh")

col1, col2, col3, col4 = st.columns(4)
if col1.button("📊 대시보드"): st.session_state.page = 1
if col2.button("📜 로그"): st.session_state.page = 2
if col3.button("🗺 지도"): st.session_state.page = 3
if col4.button("⚙️ 시스템 상태"): st.session_state.page = 4
st.write("---")

# -----------------------------------------
# 1. 대시보드
# -----------------------------------------
if st.session_state.page == 1:
    st.header("📊 센서 대시보드")

    if st.session_state.latest_data:
        # 새 데이터 추가
        st.session_state.data = pd.concat(
            [st.session_state.data, pd.DataFrame([st.session_state.latest_data])],
            ignore_index=True
        ).tail(100).reset_index(drop=True)

    if len(st.session_state.data) == 0:
        st.info("아직 MQTT 데이터가 수신되지 않았습니다.")
        st.stop()

    latest = st.session_state.data.iloc[-1]

    # 센서 카드 표시
    st.subheader("📟 Latest Sensor Values")
    col1, col2, col3 = st.columns(3)
    col1.metric("CH4", f"{latest['CH4']:.3f} ppm")
    col2.metric("CO", f"{latest['CO']:.3f} ppm")
    col3.metric("Oxygen", f"{latest['Oxygen']:.2f} %vol")

    col1, col2, col3 = st.columns(3)
    col1.metric("Distance", f"{latest['Distance']:.2f} cm")
    col2.metric("Flame", "🔥 Detected" if latest['Flame']==0 else "None")
    col3.metric("데이터 수신 수", len(st.session_state.data))

    # 시각화
    st.subheader("📈 Sensor Visualization")
    col1, col2 = st.columns(2)

    fig_line = px.line(st.session_state.data,
                       y=["CH4","CO","Oxygen","Distance"],
                       title="Sensor Trends (Line)")
    with col1:
        st.plotly_chart(fig_line, use_container_width=True)

    bar_df = latest[["CH4","CO","Oxygen","Distance"]].to_frame().reset_index()
    bar_df.columns = ["Sensor", "Value"]
    fig_bar = px.bar(bar_df, x="Sensor", y="Value", title="Latest Sensor Values (Bar)")
    with col2:
        st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------------------------
# 2. 로그 페이지
# -----------------------------------------
elif st.session_state.page == 2:
    st.header("📜 데이터 로그")
    if len(st.session_state.data) == 0:
        st.warning("데이터 없음")
    else:
        st.dataframe(st.session_state.data.tail(30))

# -----------------------------------------
# 3. 지도 (가상 위치)
# -----------------------------------------
elif st.session_state.page == 3:
    st.header("🗺 위치 추적 (예시)")
    if "lat" not in st.session_state:
        st.session_state.lat, st.session_state.lon = 37.5665, 126.9780
    st.session_state.lat += np.random.uniform(-0.0005, 0.0005)
    st.session_state.lon += np.random.uniform(-0.0005, 0.0005)
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=15)
    folium.Marker([st.session_state.lat, st.session_state.lon], popup="현재 위치").add_to(m)
    st_folium(m, width=700, height=500)

# -----------------------------------------
# 4. 시스템 상태
# -----------------------------------------
elif st.session_state.page == 4:
    st.header("⚙️ 시스템 상태 모니터링")
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    col1, col2, col3 = st.columns(3)
    col1.metric("CPU", f"{cpu}%")
    col2.metric("메모리", f"{mem}%")
    col3.metric("디스크", f"{disk}%")
