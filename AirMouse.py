import cv2
import mediapipe as mp
import autopy
import numpy as np

# Initialize MediaPipe Hand module
mp_hands = mp.solutions.hands
hands = mp_hands.Hands()
mp_draw = mp.solutions.drawing_utils

# Capture video feed
cap = cv2.VideoCapture(0)

# Initialize variables for smoothing
prev_x, prev_y = 0, 0
smooth_factor = 0.2

while True:
    success, img = cap.read()
    # Mirror the image
    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            # Get coordinates of the index finger tip
            x, y = hand_landmarks.landmark[8].x, hand_landmarks.landmark[8].y
            screen_x, screen_y = autopy.screen.size()
            # Ensure coordinates are within screen bounds
            screen_x = min(max(screen_x * x, 0), screen_x - 1)
            screen_y = min(max(screen_y * y, 0), screen_y - 1)

            # Smooth the mouse movement
            smooth_x = prev_x + (screen_x - prev_x) * smooth_factor
            smooth_y = prev_y + (screen_y - prev_y) * smooth_factor
            autopy.mouse.move(smooth_x, smooth_y)

            # Update previous coordinates
            prev_x, prev_y = smooth_x, smooth_y

            # Get coordinates of the thumb tip
            thumb_x, thumb_y = hand_landmarks.landmark[4].x, hand_landmarks.landmark[4].y
            # Get coordinates of the middle finger tip
            middle_x, middle_y = hand_landmarks.landmark[12].x, hand_landmarks.landmark[12].y

            # Calculate distance between thumb and index finger
            distance_index_thumb = ((x - thumb_x) ** 2 + (y - thumb_y) ** 2) ** 0.5
            # Calculate distance between thumb and middle finger
            distance_middle_thumb = ((middle_x - thumb_x) ** 2 + (middle_y - thumb_y) ** 2) ** 0.5

            # Define a threshold for clicking
            click_threshold = 0.05

            # Left click
            if distance_index_thumb < click_threshold:
                autopy.mouse.click(autopy.mouse.Button.LEFT)

            # Right click
            if distance_middle_thumb < click_threshold:
                autopy.mouse.click(autopy.mouse.Button.RIGHT)

    cv2.imshow("Image", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
