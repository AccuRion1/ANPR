import cv2


def straighten_plate(plate):

    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 120)

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
