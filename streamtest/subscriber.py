# subscriber.py
import streamlit as st
import paho.mqtt.client as mqtt
import json
import random

st.set_page_config(page_title="MQTT 최소 기능 테스트")
st.title("MQTT Subscriber Test")

BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
PORT = 8884
USERNAME = "JetsonOrin"
PASSWORD = "One24511"
TOPIC = "robot/alerts"

# --- 세션 상태 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "client" not in st.session_state:
    st.session_state.client = None

# --- 콜백 함수 ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        st.session_state.messages.append(data)
        # st.rerun() # 최신 버전이 아닐 수 있으므로 일단 제외
    except:
        pass

# --- 클라이언트 설정 ---
def setup_client():
    client_id = f"simple-subscriber-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, transport="websockets")
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return None

# --- 메인 로직 ---
if st.session_state.client is None:
    st.session_state.client = setup_client()

if st.session_state.client and st.session_state.client.is_connected():
    st.success("✅ Subscriber connected to HiveMQ (WebSocket)")
else:
    st.warning("🔄 Connecting...")

st.write("--- Received Messages ---")
# 수동 새로고침 버튼
if st.button("새로고침"):
    pass

st.write(st.session_state.messages)
