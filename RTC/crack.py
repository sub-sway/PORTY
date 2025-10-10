import streamlit as st
from fastapi import FastAPI, Request
from threading import Thread
import uvicorn
import base64
import io
from PIL import Image
from ultralytics import YOLO
from pymongo import MongoClient
from datetime import datetime
import os

# =========================
# 설정
# =========================
st.set_page_config(page_title="균열 감지 대시보드", layout="wide")

MODEL_PATH = "crack_analysis.pt"  # 스트림릿에서 사용할 재추론용 .pt 모델
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "crack_monitor"
COLLECTION = "crack_results"
SAVE_DIR = "received_images"
os.makedirs(SAVE_DIR, exist_ok=True)

# =========================
# FastAPI 서버 초기화
# =========================
app = FastAPI()
latest_image = None
latest_info = None

# MongoDB 연결
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]

# 재추론 모델 로드
st.sidebar.success("🔍 균열 분석 모델 로드 중...")
try:
    analysis_model = YOLO(MODEL_PATH)
    st.sidebar.success(f"✅ 모델 로드 완료: {MODEL_PATH}")
except Exception as e:
    st.sidebar.error(f"❌ 모델 로드 실패: {e}")

# =========================
# API: Jetson에서 균열 이미지 수신
# =========================
@app.post("/crack_event")
async def crack_event(request: Request):
    global latest_image, latest_info
    data = await request.json()

    # base64 → 이미지 복원
    img_data = base64.b64decode(data["image"])
    image = Image.open(io.BytesIO(img_data)).convert("RGB")
    latest_image = image
    latest_info = data

    # 로컬 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_path = os.path.join(SAVE_DIR, f"{timestamp}.jpg")
    image.save(img_path)

    # Streamlit UI에서 자동 갱신 가능하도록 데이터 유지
    return {"status": "ok", "file": img_path}


def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8501, log_level="error")


# =========================
# FastAPI 백엔드 스레드 실행
# =========================
Thread(target=run_fastapi, daemon=True).start()

# =========================
# Streamlit UI
# =========================
st.title("🧠 균열 감지 분석 대시보드")
st.info("Jetson Orin에서 전송된 이미지를 재분석하고 결과를 MongoDB에 저장합니다.")

# 이미지 표시 영역
image_placeholder = st.empty()

# 균열 결과 리스트
st.subheader("📋 최근 저장된 분석 결과")
log_placeholder = st.empty()

# =========================
# 실시간 갱신 루프
# =========================
while True:
    if latest_image is not None:
        st.subheader("📸 최근 수신 이미지")
        image_placeholder.image(latest_image, caption="Jetson 감지 이미지", use_container_width=True)

        # 재추론 수행
        with st.spinner("재분석 중..."):
            results = analysis_model.predict(latest_image, verbose=False)
            annotated = results[0].plot()

            st.image(annotated, caption="재추론 결과", use_container_width=True)

            # MongoDB에 결과 저장
            doc = {
                "timestamp": datetime.now().isoformat(),
                "num_detections": len(results[0].boxes),
                "confidences": [float(c) for c in results[0].boxes.conf.tolist()],
            }
            collection.insert_one(doc)

            st.success("✅ MongoDB 저장 완료")

            # 로그 출력
            records = list(collection.find().sort("_id", -1).limit(5))
            log_placeholder.write(records)

        # 재사용 방지
        latest_image = None

    st.stop()
