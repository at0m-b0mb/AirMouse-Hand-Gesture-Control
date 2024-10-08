import cv2
import mediapipe as mp
import socket
import pickle

# Initialize MediaPipe Hand module
mp_hands = mp.solutions.hands
hands = mp_hands.Hands()
mp_draw = mp.solutions.drawing_utils

# Capture video feed
cap = cv2.VideoCapture(0)

# Set up socket connection
server_ip = '127.0.0.1'  # Replace with the server's IP address
server_port = 12345
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_ip, server_port))

while True:
    success, img = cap.read()
    # Mirror the image
    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    data = None
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            # Get coordinates of the index finger tip
            x, y = hand_landmarks.landmark[8].x, hand_landmarks.landmark[8].y
            # Get coordinates of the thumb tip
            thumb_x, thumb_y = hand_landmarks.landmark[4].x, hand_landmarks.landmark[4].y
            # Get coordinates of the middle finger tip
            middle_x, middle_y = hand_landmarks.landmark[12].x, hand_landmarks.landmark[12].y

            # Calculate distances
            distance_index_thumb = ((x - thumb_x) ** 2 + (y - thumb_y) ** 2) ** 0.5
            distance_middle_thumb = ((middle_x - thumb_x) ** 2 + (middle_y - thumb_y) ** 2) ** 0.5

            data = (x, y, distance_index_thumb, distance_middle_thumb)

    # Send data to server
    client_socket.send(pickle.dumps(data))

    cv2.imshow("Image", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
client_socket.close()
