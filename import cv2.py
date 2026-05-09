import cv2
i = 0
frames = 1
cam = cv2.VideoCapture(0)
while True:
    if i == 300:
        break
    if i % frames == 0:  # Capture every 30 frames
        ret, frame = cam.read()
        if not ret:
            break
        cv2.imshow('Frame', frame)
        brightness = frame.mean()
        if brightness < 100:
            print("gelap")
        else:
            print("terang")
    i += 1
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    ret, frame = cam.read()
cam.release()
cv2.destroyAllWindows()