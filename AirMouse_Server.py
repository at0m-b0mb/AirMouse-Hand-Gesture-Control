import socket
import pickle
import autopy

# Set up socket connection
server_ip = '0.0.0.0'  # Listen on all available interfaces
server_port = 12345
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(1)

print("Waiting for connection...")
client_socket, client_address = server_socket.accept()
print(f"Connected to {client_address}")

# Initialize variables for smoothing
prev_x, prev_y = 0, 0
smooth_factor = 0.2
click_threshold = 0.05

while True:
    data = client_socket.recv(1024)
    if not data:
        break

    coordinates = pickle.loads(data)
    if coordinates:
        x, y, distance_index_thumb, distance_middle_thumb = coordinates
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

        # Left click
        if distance_index_thumb < click_threshold:
            autopy.mouse.click(autopy.mouse.Button.LEFT)

        # Right click
        if distance_middle_thumb < click_threshold:
            autopy.mouse.click(autopy.mouse.Button.RIGHT)

client_socket.close()
server_socket.close()
