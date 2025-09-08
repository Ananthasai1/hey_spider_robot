import base64
import json
import threading
import time
from typing import Optional

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from src.oled_display import OLEDDisplay

class WebInterface:
    def __init__(self, spider_controller, visual_monitor, ai_thinking, 
                 oled_display: Optional[OLEDDisplay] = None):
        self.spider = spider_controller
        self.vision = visual_monitor
        self.ai = ai_thinking
        self.oled = oled_display
        
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'hey_spider_secret_key_2024'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", 
                                logger=False, engineio_logger=False)
        
        self.setup_routes()
        self.setup_socket_events()
        
        # Start background tasks
        self.start_background_tasks()
        
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
            
        @self.app.route('/api/status')
        def get_status():
            try:
                detections = self.vision.get_latest_detections()
                return jsonify({
                    'distance': self.spider.get_distance(),
                    'detections': detections,
                    'detection_description': self.vision.get_detection_description(),
                    'ai_thought': self.ai.get_current_thought(),
                    'is_moving': self.spider.is_moving,
                    'emotional_state': getattr(self.ai, 'emotional_state', 'curious')
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
            
        @self.app.route('/api/command', methods=['POST'])
        def execute_command():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'message': 'No data provided'}), 400
                    
                command = data.get('command', '')
                result = self._execute_command(command)
                return jsonify(result)
            except Exception as e:
                return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
            
        @self.app.route('/api/photo', methods=['POST'])
        def take_photo():
            try:
                filename = self.vision.capture_photo()
                return jsonify({'filename': filename, 'success': bool(filename)})
            except Exception as e:
                return jsonify({'filename': '', 'success': False, 'error': str(e)})
            
    def setup_socket_events(self):
        """Setup SocketIO events"""
        
        @self.socketio.on('connect')
        def handle_connect():
            print('Web client connected')
            emit('status', 'Connected to Hey Spider Robot')
            
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print('Web client disconnected')
            
        @self.socketio.on('command')
        def handle_command(data):
            try:
                command = data.get('command', '') if data else ''
                result = self._execute_command(command)
                emit('command_result', result)
            except Exception as e:
                emit('command_result', {'success': False, 'message': f'Error: {str(e)}'})
            
    def _execute_command(self, command: str) -> dict:
        """Execute a robot command"""
        if not command:
            return {'success': False, 'message': 'Empty command'}
            
        command = command.lower().strip()
        
        if self.oled:
            self.oled.update_command(command)
            
        try:
            if any(word in command for word in ['forward', 'walk', 'move']):
                self.spider.walk_forward()
                return {'success': True, 'message': 'Walking forward'}
                
            elif 'left' in command:
                self.spider.turn_left()
                return {'success': True, 'message': 'Turning left'}
                
            elif 'right' in command:
                self.spider.turn_right()
                return {'success': True, 'message': 'Turning right'}
                
            elif 'dance' in command:
                self.spider.dance()
                return {'success': True, 'message': 'Dancing!'}
                
            elif 'wave' in command:
                self.spider.wave()
                return {'success': True, 'message': 'Waving hello!'}
                
            elif any(word in command for word in ['photo', 'picture', 'capture']):
                filename = self.vision.capture_photo()
                return {'success': bool(filename), 'message': f'Photo saved: {filename}' if filename else 'Photo capture failed'}
                
            elif 'stop' in command:
                return {'success': True, 'message': 'Stopped'}
                
            else:
                # Use AI to process unknown commands
                try:
                    ai_response = self.ai.process_command(command)
                    parsed_response = json.loads(ai_response)
                    action = parsed_response.get('action', 'unknown')
                    
                    if action == 'walk_forward':
                        self.spider.walk_forward()
                    elif action == 'turn_left':
                        self.spider.turn_left()
                    elif action == 'turn_right':
                        self.spider.turn_right()
                    elif action == 'dance':
                        self.spider.dance()
                    elif action == 'wave':
                        self.spider.wave()
                    elif action == 'take_photo':
                        self.vision.capture_photo()
                        
                    return {
                        'success': action != 'unknown',
                        'message': parsed_response.get('response', 'Command processed by AI')
                    }
                except (json.JSONDecodeError, KeyError):
                    return {'success': False, 'message': 'AI could not process command'}
                    
        except Exception as e:
            print(f"Command execution error: {e}")
            return {'success': False, 'message': f'Error: {str(e)}'}
            
    def start_background_tasks(self):
        """Start background tasks for real-time updates"""
        
        def broadcast_status():
            while True:
                try:
                    # Prepare status data
                    status_data = {
                        'distance': self.spider.get_distance(),
                        'detections': self.vision.get_latest_detections(),
                        'ai_thought': self.ai.get_current_thought(),
                        'is_moving': self.spider.is_moving,
                        'emotional_state': getattr(self.ai, 'emotional_state', 'curious')
                    }
                    
                    # Add video frame if available
                    frame = self.vision.get_latest_frame()
                    if frame is not None and OPENCV_AVAILABLE:
                        try:
                            # Resize frame for web streaming
                            frame_resized = cv2.resize(frame, (320, 240))
                            _, buffer = cv2.imencode('.jpg', frame_resized, 
                                                   [cv2.IMWRITE_JPEG_QUALITY, 70])
                            frame_data = base64.b64encode(buffer).decode('utf-8')
                            status_data['video_frame'] = frame_data
                        except Exception as e:
                            print(f"Frame encoding error: {e}")
                            status_data['video_frame'] = None
                    else:
                        status_data['video_frame'] = None
                        
                    # Broadcast to all connected clients
                    self.socketio.emit('status_update', status_data)
                    
                    time.sleep(1)  # Update every second
                    
                except Exception as e:
                    print(f"Broadcast error: {e}")
                    time.sleep(5)
                    
        # Start background thread
        threading.Thread(target=broadcast_status, daemon=True).start()
        
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the web interface"""
        print(f"Starting web interface on http://{host}:{port}")
        try:
            self.socketio.run(self.app, host=host, port=port, debug=debug,
                            allow_unsafe_werkzeug=True)  # For development only
        except Exception as e:
            print(f"Web interface error: {e}")
            raise