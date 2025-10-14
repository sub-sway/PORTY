import streamlit as st
import pymongo
import base64
from datetime import datetime

# --- 페이지 기본 설정 ---
st.set_page_config(layout="wide", page_title="균열 감지 대시보드")

# --- MongoDB Atlas 연결 ---
# st.secrets를 사용하여 .streamlit/secrets.toml 파일의 정보에 접근합니다.
@st.cache_resource
def init_connection():
    try:
        # "mongo_uri"는 secrets.toml 파일에 정의한 키(key) 이름입니다.
        mongo_uri = st.secrets["mongo_uri"]
        client = pymongo.MongoClient(mongo_uri)
        client.admin.command('ping') # 연결 테스트
        return client
    except KeyError:
        st.error("❌ secrets.toml 파일에 'mongo_uri'가 설정되지 않았습니다.")
        return None
    except Exception as e:
        st.error(f"DB 연결 실패: {e}")
        return None

client = init_connection()

# --- 메인 대시보드 UI ---
st.title("🛣️ 실시간 도로 균열 감지 대시보드")

if client is None:
    st.warning("데이터베이스에 연결할 수 없어 데이터를 표시할 수 없습니다.")
else:
    db = client["crack_monitor"]
    collection = db["crack_results"]

    st.sidebar.header("🔍 필터 옵션")
    limit = st.sidebar.slider("표시할 최근 항목 수", 1, 100, 10)

    if st.sidebar.button("새로고침 🔄"):
        st.rerun()

    st.header(f"최근 감지된 균열 목록 (상위 {limit}개)")

    # DB에서 timestamp 필드를 기준으로 최신순 정렬하여 데이터 조회
    for doc in collection.find({}).sort("timestamp", -1).limit(limit):
        
        # 날짜/시간 포맷 변경
        timestamp_local = doc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        with st.expander(f"**감지 시간:** {timestamp_local} | **장치:** {doc['source_device']} | **균열 수:** {len(doc['detections'])}"):
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Base64 문자열을 이미지로 디코딩하여 표시
                img_bytes = base64.b64decode(doc['annotated_image_base64'])
                st.image(img_bytes, caption="감지 결과 이미지", use_column_width=True)

            with col2:
                st.subheader("상세 감지 정보")
                
                for i, detection in enumerate(doc['detections']):
                    st.metric(
                        label=f"#{i+1}: {detection['class_name']}",
                        value=f"{detection['confidence']:.2%}"
                    )
                    st.code(f"Box: {[int(c) for c in detection['box_xyxy']]}", language="text")
                
                st.caption(f"DB ID: {doc['_id']}")
