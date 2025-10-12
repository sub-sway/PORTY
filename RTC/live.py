import streamlit as st
import cv2
import av
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase

# --- 페이지 설정 ---
st.set_page_config(page_title="Jetson RTSP 스트리밍", layout="wide")
st.title("📹 Jetson Orin 실시간 RTSP 영상 보기")
st.markdown("Jetson Orin에서 송출 중인 RTSP 영상을 실시간으로 확인합니다.")

# --- Jetson IP 입력 ---
JETSON_IP = st.text_input("Jetson Orin IP 주소를 입력하세요:", "172.30.1.15") # 찾으신 IP를 기본값으로 설정

if JETSON_IP:
    RTSP_URL = f"rtsp://{JETSON_IP}:8554/stream"

    # 1. VideoCapture를 안전하게 처리하는 클래스를 정의합니다.
    class RTSPVideoProcessor(VideoProcessorBase):
        def __init__(self, rtsp_url):
            self.rtsp_url = rtsp_url
            self.cap = None

        def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
            # 이 메서드는 webrtc_streamer에 의해 내부적으로 호출됩니다.
            # 하지만 우리는 자체 VideoCapture를 사용할 것이므로,
            # 입력 프레임(frame)은 무시하고 우리 소스의 프레임을 반환합니다.

            if self.cap is None:
                # VideoCapture 객체를 recv 메서드 안에서 처음 호출될 때 생성
                self.cap = cv2.VideoCapture(self.rtsp_url)
                if not self.cap.isOpened():
                    st.error("RTSP 연결 실패. IP 주소나 네트워크를 확인하세요.")
                    return None # 연결 실패 시 아무것도 하지 않음

            ret, frame_bgr = self.cap.read()
            if not ret:
                st.warning("프레임을 받아오지 못했습니다. 재연결 시도 중...")
                self.cap.release()
                self.cap = None # 연결이 끊어지면 cap을 None으로 만들어 재연결 시도
                return av.VideoFrame.from_ndarray(
                    cv2.cvtColor(
                        cv2.putText(
                            np.zeros((480, 640, 3), dtype=np.uint8),
                            "Reconnecting...",
                            (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (255, 255, 255),
                            2
                        ),
                        cv2.COLOR_BGR2RGB
                    ),
                    format="rgb24"
                )

            # OpenCV(BGR) 프레임을 WebRTC(RGB)가 이해하는 포맷으로 변환
            return av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")

    st.info(f"아래 박스에서 RTSP 스트리밍을 시작하세요. URL: {RTSP_URL}")

    webrtc_streamer(
        key="jetson-rtsp",
        mode=WebRtcMode.RECVONLY,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        # 2. video_processor_factory에 우리가 정의한 클래스를 전달합니다.
        video_processor_factory=lambda: RTSPVideoProcessor(rtsp_url=RTSP_URL),
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )
else:
    st.warning("Jetson Orin IP 주소를 입력해주세요.")
