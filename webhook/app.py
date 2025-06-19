from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import cv2
import numpy as np
import threading
import requests
import json

app = Flask(__name__)

DATABASE = 'classroom.db'
logging.basicConfig(level=logging.DEBUG)

scheduler = BackgroundScheduler()

# YOLO 모델 로드
net = cv2.dnn.readNet("yolov3.weights", "yolov3.cfg")
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# names 열기
with open("coco.names", "r") as f:
    classes = [line.strip() for line in f.readlines()]

# 비디오 캡처 초기화 웹캠 : 0번, 비디오 파일 : 주소
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) 

person_count = 0
lock = threading.Lock()

# 객체 감지
def detect_person():
    global person_count
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        height, width, channels = frame.shape

        # 객체 감지 수행
        blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
        net.setInput(blob)
        outs = net.forward(output_layers)

        # 화면에 표시할 정보 초기화
        class_ids = []
        confidences = []
        boxes = []

        # 각 출력 레이어에서 각 감지된 객체에 대해 처리
        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if confidence > 0.5 and classes[class_id] == "person":
                    # 객체 감지됨
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)

                    # 사각형 좌표 계산
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)

                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

        # 경계 상자 그리기 및 사람 수 계산
        count = 0
        for i in range(len(boxes)):
            if i in indexes:
                x, y, w, h = boxes[i]
                label = str(classes[class_ids[i]])
                if label == "person":
                    count += 1
                    # 경계 상자 그리기
                    color = (0, 255, 0)  # Green color for 'person'
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # 현재 사람 수 로그 출력
        with lock:
            person_count = count
        logging.debug(f"현재 사람 수: {person_count}")

        # 1초 간격으로 감지
        cv2.waitKey(1000)
        return person_count

# 객체 감지 스레드 시작
# threading.Thread(target=detect_person, daemon=True).start()

# 데이터베이스 연결 및 테이블 생성
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            name TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            exited INTEGER DEFAULT 0
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL
        )
        ''')
        conn.commit()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    action = data.get('action', {}).get('name')
    response_text = "오류가 발생했습니다. 다시 입력해주세요."
    conn = None
    
    try:
        if action == "신청 처리":
           content = data['action']['params']['content']
           lines = content.split('\n')
           if not all(len(line.split()) >= 3 for line in lines):
               raise ValueError("잘못된 입력 형식입니다.")
           conn = get_db_connection()
           cursor = conn.cursor()
           for line in lines:
               parts = line.split()
               if len(parts) < 3:
                   raise ValueError("잘못된 입력 형식입니다.")
               student_id = parts[0].strip()
               name = parts[1].strip()
               times = " ".join(parts[2:]).strip()
               if '~' not in times:
                   raise ValueError("잘못된 시간 형식입니다. '시작시간 ~ 종료시간' 형식으로 입력해주세요.")
               entry_time, exit_time = [time.strip() for time in times.split('~')]
               cursor.execute('''
               INSERT INTO applications (student_id, name, entry_time, exit_time)
               VALUES (?, ?, ?, ?)
               ''', (student_id, name, entry_time, exit_time))
           conn.commit()
           response_text = "신청되었습니다"

        elif action == "연장 처리":
            content = data['action']['params']['content']
            parts = content.split()
            if len(parts) < 3:
                raise ValueError("잘못된 입력 형식입니다.")
            student_id, name, new_exit_time = parts[:3]
            conn = get_db_connection()
            cursor = conn.cursor()
            # exit_time을 시간 형식으로 맞춰서 업데이트
            cursor.execute('''
            UPDATE applications
            SET exit_time = ?
            WHERE student_id = ? AND name = ?
            ''', (new_exit_time, student_id, name))
            conn.commit()
            if cursor.rowcount > 0:
                response_text = "연장되었습니다"
            else:
                response_text = "일치하는 사용자 정보가 없습니다"

        elif action == "조기퇴실 처리":
            content = data['action']['params']['content']
            parts = content.split()
            if len(parts) < 2:
                raise ValueError("잘못된 입력 형식입니다.")
            student_id, name = parts[:2]
            conn = get_db_connection()
            cursor = conn.cursor()
            exit_time = datetime.now().strftime('%I:%M').lstrip('0')
            cursor.execute('''
            UPDATE applications
            SET exited = 1, exit_time = ?
            WHERE student_id = ? AND name = ?
            ''', (exit_time, student_id, name))
            conn.commit()
            if cursor.rowcount > 0:
                response_text = "조기퇴실 처리되었습니다"
            else:
                response_text = "일치하는 사용자 정보가 없습니다"

        elif action == "신청현황 조회":
            current_time = datetime.now().strftime('%I:%M').lstrip('0')
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM applications ORDER BY id')
            users = cursor.fetchall()
            if users:
                status_list = []
                for i, user in enumerate(users):
                    exit_status = "퇴실" if user['exited'] else ""
                    if not user['exited'] and user['exit_time'] < current_time:
                        exit_status = "퇴실"
                        cursor.execute('''
                        UPDATE applications
                        SET exited = 1
                        WHERE id = ?
                        ''', (user['id'],))
                        conn.commit()
                    status_list.append(f"{i+1}. {user['student_id']} {user['name']} {user['entry_time']} ~ {user['exit_time']} {exit_status}")
                response_text = "\n".join(status_list)
            else:
                response_text = "신청된 사용자가 없습니다."

        elif action == "제보 처리":
            report_content = data['action']['params']['content']

            with open(r"C:\\Users\\Admin\\Documents\\2024Hackathon\\kakao\\tokens.json", "r") as fp:
                tokens = json.load(fp)

            url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

            headers = {
                "Authorization": "Bearer " + tokens["access_token"],
                "Content-Type": "application/x-www-form-urlencoded"
            }

            template_object = {
                "object_type": "text",
                "text": report_content,
                "link": {
                    "web_url": "https://example.com",
                    "mobile_web_url": "https://example.com"
                },
                "button_title": ""
            }

            data = {
                "template_object": json.dumps(template_object)
            }

            response = requests.post(url, headers=headers, data=data)

            print(response.status_code)
            if response.json().get('result_code') == 0:
                print('메시지 발송 성공')
            else:
                print('메시지 발송 실패\n' + str(response.json()))

            response_text = "제보해주셔서 감사합니다. 확인 후 조치하겠습니다"


        elif action == "현재인원":
            count = detect_person()
            response_text = f"현재 AI융합실 내 인원은 {count}명 입니다."


    except ValueError as e:
        response_text = str(e)
    except Exception as e:
        response_text = f"오류가 발생했습니다: {str(e)}"
    finally:
        if conn:
            conn.close()

    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": response_text
                }
            }]
        }
    })

def check_last_user():
    current_time = datetime.now()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM applications WHERE exited = 0 ORDER BY exit_time ASC')
    users = cursor.fetchall()
    conn.close()
    if users:
        last_user = users[-1]
        exit_time = datetime.strptime(last_user['exit_time'], '%H:%M')
        if current_time + timedelta(minutes=10) >= exit_time > current_time:
            print(f"AI융합실 사용 종료 10분 전 입니다. {last_user['name']}님, 자리를 잘 정돈하시고 사진을 찍어 올려주세요")

def init_db_daily():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('DROP TABLE IF EXISTS applications')
        cursor.execute('DROP TABLE IF EXISTS reports')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            name TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            exited INTEGER DEFAULT 0
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL
        )
        ''')
        conn.commit()

scheduler.add_job(check_last_user, 'interval', minutes=1)
scheduler.add_job(init_db_daily, CronTrigger.from_crontab('0 0 * * *'))  

if __name__ == "__main__":
    init_db()
    app.run(port=5000)
