import cv2
import numpy as np

# YOLO 모델 로드
net = cv2.dnn.readNet("yolov3.weights", "yolov3.cfg")
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# COCO 클래스 이름 로드
with open("coco.names", "r") as f:
    classes = [line.strip() for line in f.readlines()]

cap = cv2.VideoCapture(0)  # 웹캠 =  0, 비디오 파일 = 해당 파일 경로

while True:
    ret, frame = cap.read()
    if not ret:
        break

    height, width, channels = frame.shape

    resized_frame = cv2.resize(frame, (800, 500))
    resized_height, resized_width, _ = resized_frame.shape

    # 객체 감지 수행
    blob = cv2.dnn.blobFromImage(resized_frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
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
                center_x = int(detection[0] * resized_width)
                center_y = int(detection[1] * resized_height)
                w = int(detection[2] * resized_width)
                h = int(detection[3] * resized_height)

                # 사각형 좌표 계산
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

    # 경계 상자 그리기 및 사람 수 계산
    person_count = 0
    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            confidence = confidences[i]
            color = (0, 255, 0)  # 초록색
            cv2.rectangle(resized_frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(resized_frame, f"{label} {confidence:.2f}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            if label == "person":
                person_count += 1

    # 사람 수 화면에 표시
    cv2.putText(resized_frame, f"Person Count: {person_count}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # 출력 프레임 표시
    cv2.imshow("Frame", resized_frame)

    key = cv2.waitKey(1)
    if key == 27:  # ESC 키를 누르면 종료
        break

cap.release()
cv2.destroyAllWindows()
