import streamlit as st
import cv2
import threading
import time

# --- 페이지 설정 ---
st.set_page_config(page_title="Jetson RTSP 스트리밍", layout="wide")
st.title("📹 Jetson Orin 실시간 RTSP 영상 보기")
st.markdown("Jetson Orin에서 송출 중인 RTSP 영상을 실시간으로 확인합니다.")

# --- Jetson IP 입력 ---
JETSON_IP = st.text_input("Jetson Orin IP 주소를 입력하세요:", "192.168.0.42")
RTSP_URL = f"rtsp://{JETSON_IP}:8554/stream"

# --- 상태 및 표시 영역 ---
frame_placeholder = st.empty()
status_placeholder = st.empty()
stop_flag = False

def rtsp_worker(url):
    global stop_flag
    cap = cv2.VideoCapture(url)

    if not cap.isOpened():
        status_placeholder.error("❌ RTSP 연결 실패: IP 또는 네트워크를 확인하세요.")
        return

    status_placeholder.success(f"✅ RTSP 연결 성공: {url}")

    while not stop_flag:
        ret, frame = cap.read()
        if not ret:
            status_placeholder.warning("⚠️ 프레임 수신 실패, 재시도 중...")
            time.sleep(0.5)
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_placeholder.image(frame_rgb, use_column_width=True)

    cap.release()
    status_placeholder.info("🛑 스트리밍 종료됨")

# --- 실행 버튼 ---
col1, col2 = st.columns(2)
with col1:
    if st.button("▶️ 스트리밍 시작"):
        stop_flag = False
        thread = threading.Thread(target=rtsp_worker, args=(RTSP_URL,), daemon=True)
        thread.start()

with col2:
    if st.button("⏹ 스트리밍 중지"):
        stop_flag = True
        time.sleep(1)
        st.rerun()
