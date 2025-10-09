# publisher.py
import paho.mqtt.client as mqtt
import time
import json
import random
import ssl

BROKER = "8e008ba716c74e97a3c1588818ddb209.s1.eu.hivemq.cloud"
USERNAME = "JetsonOrin"
PASSWORD = "One24511" # 실제 비밀번호로 변경하세요
TOPIC = "robot/alerts"

# 테스트할 설정 목록
configs = [
    {
        "port": 8884,
        "desc": "사용자 지정 포트 (8884) 테스트"
    },
    {
        "port": 8084,
        "desc": "HiveMQ 공식 WebSockets 포트 (8084) 테스트"
    }
]

# 각 설정을 순서대로 테스트
for config in configs:
    print(f"\n--- [테스트 시작] {config['desc']} ---")
    client_id = f"diagnostic-tester-{random.randint(0, 1000)}"
    client = mqtt.Client(client_id=client_id, transport="websockets")
    client.username_pw_set(USERNAME, PASSWORD)
    
    # 보안(TLS) 설정을 다시 추가합니다.
    client.tls_set(cert_reqs=ssl.CERT_NONE)

    try:
        # 연결 타임아웃을 10초로 짧게 설정
        client.connect(BROKER, config["port"], 10)
        
        # 연결이 성공하면 루프를 시작하고 메시지를 한 번 보낸다.
        print(f"✅ [연결 성공] {config['desc']}")
        client.loop_start()
        time.sleep(1) # 연결 안정화를 위해 잠시 대기
        
        data = {"type": "normal", "message": f"Connection test successful on port {config['port']}"}
        client.publish(TOPIC, json.dumps(data))
        print(f"   > 테스트 메시지 전송 완료!")
        
        client.loop_stop()
        client.disconnect()
        print("--- [테스트 종료] ---")
        break # 성공했으므로 루프 중단

    except Exception as e:
        print(f"❌ [연결 실패] 원인: {e}")
        print("--- [테스트 종료] ---")
