import streamlit as st
import pymongo
import base64
from datetime import datetime

# --- 페이지 기본 설정 ---
st.set_page_config(layout="wide", page_title="안전 조끼 감지 대시보드")

# --- MongoDB Atlas 연결 ---
# st.secrets를 사용하여 .streamlit/secrets.toml 파일의 정보에 접근
@st.cache_resource
def init_connection():
    try:
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
st.title("🦺 실시간 안전 조끼(Hivis) 감지 대시보드")

if client is None:
    st.warning("데이터베이스에 연결할 수 없습니다.")
else:
    # ⭐️ DB 및 컬렉션 이름 변경
    db = client["HIvisDB"]
    collection = db["HivisData"]

    st.sidebar.header("🔍 필터 옵션")
    limit = st.sidebar.slider("표시할 최근 항목 수", 1, 100, 10)

    if st.sidebar.button("새로고침 🔄"):
        st.rerun()

    st.header(f"최근 감지된 안전 조끼 착용 현황 (상위 {limit}개)")

    for doc in collection.find({}).sort("timestamp", -1).limit(limit):
        
        timestamp_local = doc['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        device_name = doc.get('source_device', 'N/A')
        num_detections = len(doc.get('detections', []))

        with st.expander(f"**감지 시간:** {timestamp_local} | **감지 장치:** {device_name} | **감지된 객체 수:** {num_detections}"):
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                img_bytes = base64.b64decode(doc['annotated_image_base64'])
                st.image(img_bytes, caption="감지 결과 이미지", use_container_width=True)

            with col2:
                st.subheader("상세 감지 정보")
                
                for i, detection in enumerate(doc.get('detections', [])):
                    st.metric(
                        label=f"#{i+1}: {detection['class_name']}",
                        value=f"{detection['confidence']:.2%}"
                    )
                    st.code(f"Box: {[int(c) for c in detection['box_xyxy']]}", language="text")
                
                st.caption(f"DB ID: {doc['_id']}")
