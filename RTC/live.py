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

    # 가장 기본적인 형태로 webrtc_streamer 호출
    webrtc_streamer(
        key="jetson-rtsp",
        mode=WebRtcMode.RECVONLY,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        media_stream_constraints={"video": True, "audio": False},
        # 이전 코드의 video_source_url 대신, 이 방식이 더 안정적일 수 있습니다.
        # Video stream source from a media file on the server side
        # source_video_track=MediaPlayer(RTSP_URL).video,
        # 위 방식 대신 더 직접적인 방법을 사용합니다.
        video_source_url=RTSP_URL
    )
else:
    st.warning("Jetson Orin IP 주소를 입력해주세요.")
