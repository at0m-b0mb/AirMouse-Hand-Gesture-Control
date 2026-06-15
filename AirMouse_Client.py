"""
AirMouse Client — captures hand gestures from webcam and streams
normalized coordinates to AirMouse_Server.py over TCP.

Run on the machine with the camera:
    python AirMouse_Client.py <server_ip> [port]

Protocol: see AirMouse_Server.py for wire format details.
"""

import sys
import socket
import struct
import time
import cv2

from src.camera import detect_camera, open_camera
from src.hand_tracker import HandTracker

_FMT        = "!B4f"
_FRAME_SIZE = struct.calcsize(_FMT)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 12345


def main(server_ip: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    print(f"[Client] Connecting to {server_ip}:{port} ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((server_ip, port))
    print("[Client] Connected.\n")

    cam_idx = detect_camera()
    cap, cam_w, cam_h = open_camera(cam_idx)
    tracker = HandTracker()

    print("[Client] Streaming gestures. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        results, lm_lists = tracker.process(frame)
        tracker.draw(frame, results)

        if lm_lists:
            lm = lm_lists[0]
            cx, cy = lm[8].x, lm[8].y         # index tip
            tx, ty = lm[4].x, lm[4].y         # thumb tip
            mx, my = lm[12].x, lm[12].y       # middle tip

            d_idx = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
            d_mid = ((mx - tx) ** 2 + (my - ty) ** 2) ** 0.5

            packet = struct.pack(_FMT, 1, cx, cy, d_idx, d_mid)
        else:
            packet = struct.pack(_FMT, 0, 0.0, 0.0, 0.0, 0.0)

        try:
            sock.sendall(packet)
        except BrokenPipeError:
            print("[Client] Server disconnected.")
            break

        cv2.imshow("AirMouse Client", frame)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    tracker.close()
    cap.release()
    cv2.destroyAllWindows()
    sock.close()
    print("[Client] Done.")


if __name__ == "__main__":
    ip   = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    main(ip, port)
