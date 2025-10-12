import streamlit as st
import pymongo
import base64
from datetime import datetime

# --- 설정 ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "crack_monitor"
COLLECTION_NAME = "crack_results"

# --- DB 연결 ---
@st.cache_resource
def init_connection():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # 연결 테스트
        client.server_info()
        return client
    except pymongo.errors.ServerSelectionTimeoutError as err:
        st.error(f"MongoDB 연결 실패: {err}")
        return None

client = init_connection()

# --- Streamlit 페이지 구성 ---
st.set_page_config(layout="wide")
st.title("🛣️ 도로 균열 감지 모니터링 대시보드")

if client is None:
    st.warning("DB에 연결할 수 없어 데이터를 표시할 수 없습니다.")
else:
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    st.sidebar.header("필터")
    limit = st.sidebar.slider("표시할 최근 항목 수", 1, 100, 10)

    if st.sidebar.button("새로고침 🔄"):
        st.rerun()

    st.header(f"최근 감지된 균열 목록 (최대 {limit}개)")

    # DB에서 최신 데이터를 가져와서 표시
    # timestamp 필드를 기준으로 내림차순 정렬
    for doc in collection.find({}).sort("timestamp", -1).limit(limit):
        
        with st.expander(f"감지 시간: {doc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} UTC - 감지된 균열 {doc['num_detections']}개"):
            
            col1, col2 = st.columns([2, 1]) # 이미지 컬럼을 더 넓게
            
            with col1:
                # Base64 이미지를 디코딩하여 표시
                img_bytes = base64.b64decode(doc['annotated_image_base64'])
                st.image(img_bytes, caption="감지 결과 이미지", use_column_width=True)

            with col2:
                st.subheader("상세 정보")
                
                for i, detection in enumerate(doc['detections']):
                    st.markdown(f"**균열 #{i+1}**")
                    st.metric(
                        label=f"종류: {detection['class_name']}",
                        value=f"{detection['confidence']:.2%}"
                    )
                
                st.caption(f"MongoDB ID: {doc['_id']}")
