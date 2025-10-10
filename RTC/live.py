import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode

st.set_page_config(page_title="실시간 영상 스트리밍", layout="wide")
st.title("📹 Jetson Orin 실시간 스트리밍")
st.markdown("Jetson Orin의 USB 카메라 영상을 WebRTC를 통해 실시간으로 표시합니다.")

# Jetson Orin의 WebRTC 노드와 연결
webrtc_streamer(
    key="live_stream",
    mode=WebRtcMode.RECVONLY,
    media_stream_constraints={"video": True, "audio": False},
)
