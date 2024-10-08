# AirMouse-Hand-Gesture-Control

## Overview
AirMouse-Hand-Gesture-Control is a Python-based project that allows users to control their mouse with hand gestures using a webcam. The hand gestures are tracked using MediaPipe and OpenCV, while Autopy enables smooth mouse movement and clicking actions. 

This repository contains two versions of the project:
1. **Standalone Air Mouse:** A single script that runs locally and controls the mouse using hand gestures.
2. **Client-Server Version:** This version implements a client-server architecture, enabling remote control of the mouse using gestures.

## Features
- **Hand Gesture Recognition**: Tracks index finger for mouse movement, and uses pinch gestures to perform left and right clicks.
- **Smooth Mouse Movement**: The movement is smoothed for more natural control.
- **Client-Server Mode**: Allows for controlling a mouse remotely across devices.

## Gesture Controls
- **Move Mouse**: Move your hand in front of the camera to move the mouse.
- **Left Click**: Pinch index finger and thumb together.
- **Right Click**: Pinch middle finger and thumb together.

## Demo Video
[![AirMouse Demo](demo/AirMouse_Demo.png)](demo/AirMouse_Demo.mp4)

Click the image to view the demo video.

## Installation
### Clone the repository:
```bash
git clone https://github.com/at0m-b0mb/AirMouse-Hand-Gesture-Control.git
cd AirMouse-Hand-Gesture-Control
```

### Install dependencies:
```bash
pip install -r requirements.txt
```

### Dependencies
```bash
opencv-python
mediapipe
autopy
numpy
```

You can find these in the **`requirements.txt`** file.
___

## Usage
### Simple AirMouse Mode:
This is the basic version that works locally on a single machine.
- Run the **`AirMouse.py`** file:
```bash
python AirMouse.py
```
- Your webcam will open, and you can start using your hand as a mouse!


### Client-Server Mode:
This mode allows the mouse control to be transmitted from a client to a server remotely.
- Running the Server **`AirMouse_Server.py`** file:

On the machine where you want the mouse to be controlled (Server):
```bash
python AirMouse_Server.py
```
- Running the Client: **`AirMouse_Client.py`** file:

On the machine where the gestures will be captured (Client):
```bash
python AirMouse_Client.py
```
- Ensure the server and client are on the same network, and adjust the IP addresses in the script accordingly.

___

## How it Works
- The application uses the MediaPipe library for hand landmark detection and tracking.
- The index, middle, and thumb fingers' coordinates are captured and processed to determine hand gestures.
- These coordinates are mapped to the screen's resolution to simulate mouse movement.
- The left and right click events are triggered based on the distance between the fingers (pinch gesture).

## Future Improvements
- Add support for more gestures (e.g., scrolling, dragging).
- Improve the accuracy of click detection.
- Enhance robustness by using machine learning models for gesture classification.
- Adding Face Authentication

## Contributing
Feel free to fork the project, make improvements, and create a pull request. Any contribution that makes AirMouse better is welcome!

