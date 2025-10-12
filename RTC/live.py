import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode

# --- 페이지 설정 ---
st.set_page_config(page_title="Jetson RTSP 스트리밍", layout="wide")
st.title("📹 Jetson Orin 실시간 RTSP 영상 보기")
st.markdown("Jetson Orin에서 송출 중인 RTSP 영상을 실시간으로 확인합니다.")

# --- Jetson IP 입력 ---
JETSON_IP = st.text_input("Jetson Orin IP 주소를 입력하세요:", "192.168.0.42")

if JETSON_IP:
    RTSP_URL = f"rtsp://{JETSON_IP}:8554/stream"

    st.info(f"아래 박스에서 RTSP 스트리밍을 시작하세요. URL: {RTSP_URL}")

    # 버전 업그레이드 후 이 코드가 정상적으로 작동합니다.
    webrtc_streamer(
        key="jetson-rtsp",
        mode=WebRtcMode.RECVONLY,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        media_stream_constraints={"video": True, "audio": False},
        video_source_url=RTSP_URL,
    )
else:
    st.warning("Jetson Orin IP 주소를 입력해주세요.")
