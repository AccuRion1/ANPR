from ultralytics import YOLO
import cv2
import easyocr
import re
import psycopg2

conn = psycopg2.connect(
    dbname="plates",
    user="postgres",
    password="201720122004",
    host="localhost",
    port="5432",
    client_encoding='UTF8'
)

cursor = conn.cursor()

# ================================
# проверка номера в базе
# ================================

def check_plate_in_db(plate_number):

    cursor = conn.cursor()

    query = """
    SELECT 1 
    FROM register_plates 
    WHERE plate_number = %s
    """

    cursor.execute(query, (plate_number,))

    result = cursor.fetchone()

    cursor.close()

    if result:
        print("Доступ разрешен")
    else:
        print("Отказано")

# ================================
# загрузка моделей
# ================================

yolo_model = YOLO("models/yolov8_plate.pt")
reader = easyocr.Reader(['en'])

# ================================
# исправление ошибок OCR
# ================================

def fix_plate(plate):

    if len(plate) < 6:
        return plate

    plate = list(plate)

    digit_to_letter = {
        '0': 'O',
        '1': 'I',
        '5': 'S',
        '8': 'B'
    }

    letter_to_digit = {
        'O': '0',
        'I': '1',
        'S': '5',
        'B': '8'
    }

    # первая позиция — буква
    if plate[0] in digit_to_letter:
        plate[0] = digit_to_letter[plate[0]]

    # позиции 2-4 — цифры
    for i in range(1,4):
        if plate[i] in letter_to_digit:
            plate[i] = letter_to_digit[plate[i]]

    # позиции 5-6 — буквы
    for i in range(4,6):
        if plate[i] in digit_to_letter:
            plate[i] = digit_to_letter[plate[i]]

    # регион — цифры
    for i in range(6,len(plate)):
        if plate[i] in letter_to_digit:
            plate[i] = letter_to_digit[plate[i]]

    return "".join(plate)

# ================================
# распознавание номера
# ================================

def recognize_plate(plate_img):

    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2)
    gray = cv2.GaussianBlur(gray, (5,5), 0)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)

    detections = reader.readtext(thresh)

    best_text = ""

    for detection in detections:
        candidate = re.sub(r'[^A-Za-z0-9]', '', detection[1])
        if candidate.lower() == "rus":
            continue
        if len(candidate) > len(best_text):
            best_text = candidate

    plate_number = best_text.upper()
    plate_number = fix_plate(plate_number)

    # фильтр допустимых символов
    allowed_letters = "ABCEHKMOPTXY0123456789"
    plate_number = ''.join([c for c in plate_number if c in allowed_letters])

    # проверка минимальной длины
    if len(plate_number) < 6:
        return ""  # слишком короткий номер — игнорируем

    # опционально: проверка формата с предупреждением
    pattern = r'^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}[0-9]{2,3}$'
    if not re.match(pattern, plate_number):
        print(f"Номер {plate_number} не полностью соответствует формату, проверяем как есть")

    return plate_number

def straighten_plate(plate):

    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return plate

    cnt = max(contours, key=cv2.contourArea)

    rect = cv2.minAreaRect(cnt)
    angle = rect[-1]

    if angle < -45:
        angle = 90 + angle

    (h, w) = plate.shape[:2]
    center = (w // 2, h // 2)

    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(plate, M, (w, h))

    return rotated

# ================================
# обработка одного кадра
# ================================

def process_frame(frame):

    results = yolo_model(frame)

    # создаём затемнённую копию изображения
    dark_frame = (frame * 0.35).astype("uint8")

    for result in results:

        for box in result.boxes.xyxy:

            x1, y1, x2, y2 = map(int, box)

            # вырезаем номер
            plate = frame[y1:y2, x1:x2]

            # ВАЖНО: выравниваем номер
            plate = straighten_plate(plate)

            plate_number = recognize_plate(plate)

            # возвращаем оригинальную область номера на затемнённый фон
            dark_frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2]

            # рисуем рамку
            cv2.rectangle(dark_frame, (x1, y1), (x2, y2), (0,255,0), 2)

            # выводим текст
            cv2.putText(
                dark_frame,
                plate_number,
                (x1, y1-10),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0,255,0),
                2
            )

            print("Detected plate:", plate_number)

            check_plate_in_db(plate_number)

    return dark_frame


# ================================
# обработка изображения
# ================================

def process_image(image_path):

    image = cv2.imread(image_path)

    if image is None:
        print("Ошибка: изображение не найдено")
        return

    frame = process_frame(image)

    print("Изображение обработано")

    cv2.imshow("Result", frame)

    cv2.waitKey(0)

    cv2.destroyAllWindows()


# ================================
# обработка видео
# ================================

def process_video(video_path):

    cap = cv2.VideoCapture(video_path)

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame = process_frame(frame)

        cv2.imshow("Video", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()

    cv2.destroyAllWindows()


# ================================
# обработка вебкамеры
# ================================

def process_webcam():

    cap = cv2.VideoCapture(0)

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame = process_frame(frame)

        cv2.imshow("Webcam", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()

    cv2.destroyAllWindows()


# ================================
# выбор режима работы
# ================================

if __name__ == "__main__":

    mode = input("Выберите режим (image / video / webcam): ")

    if mode == "image":

        #path = input("Введите путь к изображению")
        path = "test_images/car4.jpg"
        process_image(path)

    elif mode == "video":

        path = input("Путь к видео: ")
        process_video(path)

    elif mode == "webcam":

        process_webcam()

    else:

        print("Неизвестный режим")