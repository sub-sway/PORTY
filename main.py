import pymongo
import datetime

# Streamlit secrets.toml에 있는 정보와 완전히 동일하게 입력해주세요.
MONGO_URI = "mongodb+srv://jystarwow_db_user:zf01VaAW4jYH0dVP@porty.oqiwzud.mongodb.net/"
DB_NAME = "AlertDB"
COLLECTION_NAME = "AlertData"

print("="*50)
print("MongoDB 연결 및 쓰기 권한 최종 점검을 시작합니다.")
print("="*50)
print(f" > 목표 클러스터: porty.oqiwzud.mongodb.net")
print(f" > 목표 데이터베이스: {DB_NAME}")
print(f" > 목표 컬렉션: {COLLECTION_NAME}")
print("-" * 50)

client = None  # client 변수를 try 블록 외부에서 초기화

try:
    # 1. 연결 시도
    print("\n[1단계] MongoDB에 연결을 시도합니다...")
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    
    # 서버 정보 요청을 통해 실제 연결을 강제하고 검증합니다.
    client.server_info()
    print("✅ [성공] MongoDB 서버에 성공적으로 연결되었습니다.")

    # 2. 데이터베이스 및 컬렉션 선택
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # 3. 테스트 데이터 생성
    test_data = {
        "type": "final_write_test",
        "message": "이 데이터가 보이면 DB 쓰기 권한이 정상입니다.",
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "verified": True
    }
    
    # 4. 데이터 저장(쓰기) 시도
    print(f"\n[2단계] '{COLLECTION_NAME}' 컬렉션에 테스트 데이터 저장을 시도합니다...")
    result = collection.insert_one(test_data)
    print("✅ [성공] 데이터가 성공적으로 저장되었습니다!")
    print(f" > 저장된 데이터의 고유 ID: {result.inserted_id}")

    # 5. 저장된 데이터 즉시 조회(읽기)
    print("\n[3단계] 방금 저장한 데이터를 다시 조회하여 검증합니다...")
    retrieved_data = collection.find_one({"_id": result.inserted_id})
    if retrieved_data:
        print("✅ [성공] 저장된 데이터를 성공적으로 다시 읽었습니다.")
        print(" > 조회된 데이터:", retrieved_data)
    else:
        print("❗️ [경고] 데이터를 저장했지만 즉시 조회가 되지 않았습니다. (인덱싱 지연 가능성)")

except pymongo.errors.ConfigurationError as e:
    print("\n❌ [실패] MongoDB 연결 문자열(URI)에 문제가 있습니다.")
    print(" > 에러 원인:", e)
    print(" > 해결 방법: MONGO_URI의 사용자 이름, 비밀번호, 주소가 올바른지 다시 확인해주세요.")

except pymongo.errors.OperationFailure as e:
    print("\n❌ [실패] 인증 또는 권한에 문제가 있습니다.")
    print(" > 에러 원인:", e)
    print(" > 해결 방법: MongoDB Atlas의 Database Access 탭에서 사용자에게 'readWrite' 권한이 있는지,")
    print(" >           Network Access 탭에서 현재 IP가 허용되었는지 확인해주세요.")

except pymongo.errors.ServerSelectionTimeoutError as e:
    print("\n❌ [실패] MongoDB 서버에 연결할 수 없습니다 (타임아웃).")
    print(" > 에러 원인:", e)
    print(" > 해결 방법: Network Access 탭에서 현재 IP가 허용되었는지 확인하거나, 방화벽 문제를 점검해주세요.")

except Exception as e:
    print(f"\n❌ [실패] 예측하지 못한 에러가 발생했습니다.")
    print(" > 에러 원인:", e)

finally:
    if client:
        client.close()
        print("\n[완료] MongoDB 연결을 닫았습니다.")
    print("=" * 50)
