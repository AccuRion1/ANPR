import cv2

from core.pipeline import process_frame


# ================================
# загрузка моделей
# ================================

#yolo_model = YOLO("models/yolov8_plate.pt")
#reader = easyocr.Reader(['en'])

def process_image(path, camera_name="Изображение", direction="въезд"):

    image = cv2.imread(path)

    frame = process_frame(image, camera_name=camera_name, direction=direction)

    cv2.imshow("Result", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def process_video(path, camera_name="Видео", direction="въезд"):

    cap = cv2.VideoCapture(path)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = process_frame(frame, camera_name=camera_name, direction=direction)

        cv2.imshow("Video", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


def process_camera(camera_index=0, camera_name="Веб-камера 0", direction="въезд"):

    cap = cv2.VideoCapture(camera_index)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = process_frame(frame, camera_name=camera_name, direction=direction)

        cv2.imshow("Camera", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":

    mode = input("Выберите режим (image / video / camera): ")

    if mode == "image":
        process_image("test_images/car9.jpg", camera_name="Изображение", direction="выезд")

    elif mode == "video":
        path = input("Путь к видео: ")
        process_video(path, camera_name="Видео", direction="въезд")

    elif mode == "camera":
        process_camera(camera_name="Веб-камера 0", direction="въезд")
