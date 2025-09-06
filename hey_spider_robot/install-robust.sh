# Optimized requirements for Raspberry Pi installation
# Core web framework
Flask==3.0.0
Flask-SocketIO==5.3.6

# Computer vision (install from piwheels for Pi)
opencv-python==4.8.1.78

# YOLO - use lighter version for Pi
ultralytics==8.0.196

# Hardware control libraries
adafruit-circuitpython-pca9685==3.4.15
adafruit-circuitpython-servokit==1.3.13
adafruit-circuitpython-ssd1306==2.12.14

# Image processing
Pillow==10.1.0

# Audio processing
SpeechRecognition==3.10.0
# PyAudio - may need system packages first
pyaudio==0.2.11

# OpenAI API - modern version
openai==1.3.0

# Scientific computing
numpy==1.24.3

# Communication
python-socketio==5.8.0

# Raspberry Pi GPIO (only install on Pi)
RPi.GPIO==0.7.1; platform_machine=="armv7l" or platform_machine=="aarch64"
gpiozero==1.6.2; platform_machine=="armv7l" or platform_machine=="aarch64"