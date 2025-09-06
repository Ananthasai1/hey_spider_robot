import base64
import json
import threading
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.warning("OpenCV not available - video streaming disabled")

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from src.oled_display import OLEDDisplay


class CommandType(Enum):
    """Enumeration of supported command types"""
    MOVEMENT = "movement"
    ACTION = "action"
    CAMERA = "camera"
    SYSTEM = "system"
    AI_PROCESSED = "ai_processed"


@dataclass
class CommandResult:
    """Result of command execution"""
    success: bool
    message: str
    command_type: CommandType
    execution_time: float = 0.0
    data: Optional[Dict[str, Any]] = None


class SpiderWebInterface:
    """
    Enhanced web interface for the Hey Spider Robot with improved error handling,
    logging, and modern Python practices.
    """
    
    def __init__(self, spider_controller, visual_monitor, ai_thinking, 
                 oled_display: Optional[OLEDDisplay] = None, 
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize the web interface
        
        Args:
            spider_controller: Robot movement controller
            visual_monitor: Computer vision and monitoring system
            ai_thinking: AI processing system
            oled_display: Optional OLED display controller
            config: Optional configuration dictionary
        """
        self.spider = spider_controller
        self.vision = visual_monitor
        self.ai = ai_thinking
        self.oled = oled_display
        self.config = config or {}
        
        # Setup logging
        self._setup_logging()
        
        # Initialize Flask app and SocketIO
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = self.config.get(
            'secret_key', 'hey_spider_secret_key_2024'
        )
        
        # SocketIO configuration
        socketio_config = {
            'cors_allowed_origins': self.config.get('cors_origins', "*"),
            'logger': self.config.get('socketio_logging', False),
            'engineio_logger': self.config.get('engineio_logging', False),
            'ping_timeout': self.config.get('ping_timeout', 60),
            'ping_interval': self.config.get('ping_interval', 25)
        }
        self.socketio = SocketIO(self.app, **socketio_config)
        
        # Connection tracking
        self.connected_clients = set()
        self.command_history = []
        self.max_command_history = self.config.get('max_command_history', 100)
        
        # Background task control
        self._stop_background_tasks = threading.Event()
        self._background_thread = None
        
        # Setup routes and events
        self._setup_routes()
        self._setup_socket_events()
        
        self.logger.info("Spider Web Interface initialized successfully")
        
    def _setup_logging(self):
        """Setup logging configuration"""
        log_level = self.config.get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def _setup_routes(self):
        """Setup Flask HTTP routes"""
        
        @self.app.route('/')
        def index():
            """Serve the main dashboard"""
            try:
                return render_template('dashboard.html')
            except Exception as e:
                self.logger.error(f"Error serving dashboard: {e}")
                return jsonify({'error': 'Dashboard unavailable'}), 500
            
        @self.app.route('/api/status')
        def get_status():
            """Get current robot status"""
            try:
                status = self._get_robot_status()
                return jsonify(status)
            except Exception as e:
                self.logger.error(f"Status API error: {e}")
                return jsonify({'error': 'Status unavailable'}), 500
            
        @self.app.route('/api/command', methods=['POST'])
        def execute_command():
            """Execute robot command via HTTP"""
            try:
                data = request.get_json()
                if not data or 'command' not in data:
                    return jsonify({
                        'success': False, 
                        'message': 'Invalid request - command required'
                    }), 400
                    
                command = data['command']
                result = self._execute_command(command)
                
                return jsonify({
                    'success': result.success,
                    'message': result.message,
                    'command_type': result.command_type.value,
                    'execution_time': result.execution_time,
                    'data': result.data
                })
                
            except Exception as e:
                self.logger.error(f"Command API error: {e}")
                return jsonify({
                    'success': False, 
                    'message': f'Server error: {str(e)}'
                }), 500
            
        @self.app.route('/api/photo', methods=['POST'])
        def take_photo():
            """Capture photo endpoint"""
            try:
                start_time = time.time()
                filename = self.vision.capture_photo()
                execution_time = time.time() - start_time
                
                result = {
                    'success': bool(filename),
                    'filename': filename or '',
                    'execution_time': execution_time
                }
                
                if not filename:
                    result['error'] = 'Photo capture failed'
                    
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Photo capture error: {e}")
                return jsonify({
                    'success': False, 
                    'filename': '', 
                    'error': str(e)
                })
                
        @self.app.route('/api/history')
        def get_command_history():
            """Get recent command history"""
            try:
                return jsonify({
                    'commands': self.command_history[-20:],  # Last 20 commands
                    'total_commands': len(self.command_history)
                })
            except Exception as e:
                self.logger.error(f"History API error: {e}")
                return jsonify({'error': 'History unavailable'}), 500
            
    def _setup_socket_events(self):
        """Setup SocketIO event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            client_id = request.sid
            self.connected_clients.add(client_id)
            self.logger.info(f'Web client connected: {client_id}')
            
            emit('connection_status', {
                'status': 'connected',
                'message': 'Connected to Hey Spider Robot',
                'server_time': datetime.now().isoformat(),
                'client_id': client_id
            })
            
            # Send initial status
            try:
                initial_status = self._get_robot_status()
                emit('status_update', initial_status)
            except Exception as e:
                self.logger.error(f"Error sending initial status: {e}")
                
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            client_id = request.sid
            self.connected_clients.discard(client_id)
            self.logger.info(f'Web client disconnected: {client_id}')
            
        @self.socketio.on('command')
        def handle_socket_command(data):
            """Handle command via SocketIO"""
            try:
                command = data.get('command', '') if data else ''
                if not command:
                    emit('command_result', {
                        'success': False, 
                        'message': 'Empty command received'
                    })
                    return
                    
                result = self._execute_command(command)
                
                emit('command_result', {
                    'success': result.success,
                    'message': result.message,
                    'command_type': result.command_type.value,
                    'execution_time': result.execution_time,
                    'data': result.data
                })
                
            except Exception as e:
                self.logger.error(f"Socket command error: {e}")
                emit('command_result', {
                    'success': False, 
                    'message': f'Error: {str(e)}'
                })
                
        @self.socketio.on('ping')
        def handle_ping(data):
            """Handle client ping for connection testing"""
            emit('pong', {
                'timestamp': datetime.now().isoformat(),
                'data': data
            })
            
    def _get_robot_status(self) -> Dict[str, Any]:
        """Get comprehensive robot status"""
        try:
            detections = self.vision.get_latest_detections() if self.vision else []
            
            status = {
                'timestamp': datetime.now().isoformat(),
                'distance': self.spider.get_distance() if hasattr(self.spider, 'get_distance') else 0.0,
                'detections': detections,
                'detection_description': (
                    self.vision.get_detection_description() 
                    if self.vision and hasattr(self.vision, 'get_detection_description') 
                    else ''
                ),
                'ai_thought': (
                    self.ai.get_current_thought() 
                    if self.ai and hasattr(self.ai, 'get_current_thought') 
                    else ''
                ),
                'is_moving': getattr(self.spider, 'is_moving', False),
                'emotional_state': getattr(self.ai, 'emotional_state', 'curious'),
                'connected_clients': len(self.connected_clients),
                'system_status': 'operational'
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting robot status: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'system_status': 'error'
            }
            
    def _execute_command(self, command: str) -> CommandResult:
        """
        Execute a robot command with comprehensive error handling
        
        Args:
            command: Command string to execute
            
        Returns:
            CommandResult with execution details
        """
        start_time = time.time()
        command = command.lower().strip()
        
        # Log command
        command_entry = {
            'command': command,
            'timestamp': datetime.now().isoformat(),
            'client_count': len(self.connected_clients)
        }
        
        if not command:
            return CommandResult(
                success=False,
                message='Empty command',
                command_type=CommandType.SYSTEM,
                execution_time=time.time() - start_time
            )
            
        # Update OLED if available
        if self.oled:
            try:
                self.oled.update_command(command)
            except Exception as e:
                self.logger.warning(f"OLED update failed: {e}")
                
        try:
            # Movement commands
            if any(word in command for word in ['forward', 'walk', 'move', 'ahead']):
                self.spider.walk_forward()
                result = CommandResult(
                    success=True,
                    message='Walking forward',
                    command_type=CommandType.MOVEMENT,
                    execution_time=time.time() - start_time
                )
                
            elif any(word in command for word in ['left', 'turn left', 'rotate left']):
                self.spider.turn_left()
                result = CommandResult(
                    success=True,
                    message='Turning left',
                    command_type=CommandType.MOVEMENT,
                    execution_time=time.time() - start_time
                )
                
            elif any(word in command for word in ['right', 'turn right', 'rotate right']):
                self.spider.turn_right()
                result = CommandResult(
                    success=True,
                    message='Turning right',
                    command_type=CommandType.MOVEMENT,
                    execution_time=time.time() - start_time
                )
                
            elif any(word in command for word in ['back', 'backward', 'reverse']):
                if hasattr(self.spider, 'walk_backward'):
                    self.spider.walk_backward()
                    result = CommandResult(
                        success=True,
                        message='Walking backward',
                        command_type=CommandType.MOVEMENT,
                        execution_time=time.time() - start_time
                    )
                else:
                    result = CommandResult(
                        success=False,
                        message='Backward movement not supported',
                        command_type=CommandType.MOVEMENT,
                        execution_time=time.time() - start_time
                    )
                
            # Action commands
            elif 'dance' in command:
                self.spider.dance()
                result = CommandResult(
                    success=True,
                    message='Dancing! 💃',
                    command_type=CommandType.ACTION,
                    execution_time=time.time() - start_time
                )
                
            elif 'wave' in command:
                self.spider.wave()
                result = CommandResult(
                    success=True,
                    message='Waving hello! 👋',
                    command_type=CommandType.ACTION,
                    execution_time=time.time() - start_time
                )
                
            # Camera commands
            elif any(word in command for word in ['photo', 'picture', 'capture', 'snap']):
                filename = self.vision.capture_photo() if self.vision else None
                result = CommandResult(
                    success=bool(filename),
                    message=f'Photo saved: {filename}' if filename else 'Photo capture failed',
                    command_type=CommandType.CAMERA,
                    execution_time=time.time() - start_time,
                    data={'filename': filename} if filename else None
                )
                
            # System commands
            elif any(word in command for word in ['stop', 'halt', 'freeze']):
                if hasattr(self.spider, 'stop'):
                    self.spider.stop()
                result = CommandResult(
                    success=True,
                    message='Stopped',
                    command_type=CommandType.SYSTEM,
                    execution_time=time.time() - start_time
                )
                
            else:
                # Try AI processing for unknown commands
                result = self._process_ai_command(command, start_time)
                
            # Update command history
            command_entry['result'] = {
                'success': result.success,
                'message': result.message,
                'command_type': result.command_type.value,
                'execution_time': result.execution_time
            }
            
            self.command_history.append(command_entry)
            if len(self.command_history) > self.max_command_history:
                self.command_history.pop(0)
                
            return result
            
        except Exception as e:
            error_msg = f'Command execution error: {str(e)}'
            self.logger.error(error_msg)
            
            command_entry['result'] = {
                'success': False,
                'message': error_msg,
                'execution_time': time.time() - start_time
            }
            self.command_history.append(command_entry)
            
            return CommandResult(
                success=False,
                message=error_msg,
                command_type=CommandType.SYSTEM,
                execution_time=time.time() - start_time
            )
            
    def _process_ai_command(self, command: str, start_time: float) -> CommandResult:
        """Process command using AI system"""
        try:
            if not self.ai or not hasattr(self.ai, 'process_command'):
                return CommandResult(
                    success=False,
                    message='AI processing not available',
                    command_type=CommandType.AI_PROCESSED,
                    execution_time=time.time() - start_time
                )
                
            ai_response = self.ai.process_command(command)
            
            try:
                parsed_response = json.loads(ai_response)
                action = parsed_response.get('action', 'unknown')
                
                # Execute AI-determined action
                if action == 'walk_forward' and hasattr(self.spider, 'walk_forward'):
                    self.spider.walk_forward()
                elif action == 'turn_left' and hasattr(self.spider, 'turn_left'):
                    self.spider.turn_left()
                elif action == 'turn_right' and hasattr(self.spider, 'turn_right'):
                    self.spider.turn_right()
                elif action == 'dance' and hasattr(self.spider, 'dance'):
                    self.spider.dance()
                elif action == 'wave' and hasattr(self.spider, 'wave'):
                    self.spider.wave()
                elif action == 'take_photo' and self.vision:
                    self.vision.capture_photo()
                    
                return CommandResult(
                    success=action != 'unknown',
                    message=parsed_response.get('response', 'Command processed by AI'),
                    command_type=CommandType.AI_PROCESSED,
                    execution_time=time.time() - start_time,
                    data={'ai_action': action, 'ai_response': parsed_response}
                )
                
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.warning(f"AI response parsing error: {e}")
                return CommandResult(
                    success=False,
                    message='AI could not process command',
                    command_type=CommandType.AI_PROCESSED,
                    execution_time=time.time() - start_time
                )
                
        except Exception as e:
            self.logger.error(f"AI command processing error: {e}")
            return CommandResult(
                success=False,
                message=f'AI processing error: {str(e)}',
                command_type=CommandType.AI_PROCESSED,
                execution_time=time.time() - start_time
            )
            
    def _start_background_tasks(self):
        """Start background tasks for real-time updates"""
        
        def status_broadcast_loop():
            """Main loop for broadcasting status updates"""
            update_interval = self.config.get('status_update_interval', 1.0)
            
            while not self._stop_background_tasks.is_set():
                try:
                    if not self.connected_clients:
                        time.sleep(update_interval)
                        continue
                        
                    # Get status data
                    status_data = self._get_robot_status()
                    
                    # Add video frame if available
                    if OPENCV_AVAILABLE and self.vision:
                        frame = self._get_video_frame()
                        if frame:
                            status_data['video_frame'] = frame
                            
                    # Broadcast to all connected clients
                    self.socketio.emit('status_update', status_data)
                    
                    # Wait for next update
                    self._stop_background_tasks.wait(update_interval)
                    
                except Exception as e:
                    self.logger.error(f"Broadcast error: {e}")
                    self._stop_background_tasks.wait(5)  # Wait longer on error
                    
        # Start background thread
        self._background_thread = threading.Thread(
            target=status_broadcast_loop, 
            daemon=True, 
            name="StatusBroadcast"
        )
        self._background_thread.start()
        self.logger.info("Background status broadcast started")
        
    def _get_video_frame(self) -> Optional[str]:
        """Get encoded video frame for streaming"""
        try:
            if not self.vision or not hasattr(self.vision, 'get_latest_frame'):
                return None
                
            frame = self.vision.get_latest_frame()
            if frame is None:
                return None
                
            # Resize for web streaming
            target_size = self.config.get('video_frame_size', (320, 240))
            quality = self.config.get('video_quality', 70)
            
            frame_resized = cv2.resize(frame, target_size)
            _, buffer = cv2.imencode('.jpg', frame_resized, 
                                   [cv2.IMWRITE_JPEG_QUALITY, quality])
            
            return base64.b64encode(buffer).decode('utf-8')
            
        except Exception as e:
            self.logger.warning(f"Video frame encoding error: {e}")
            return None
            
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """
        Run the web interface
        
        Args:
            host: Host address to bind to
            port: Port number to use
            debug: Enable debug mode
        """
        self.logger.info(f"Starting Spider Web Interface on http://{host}:{port}")
        
        try:
            # Start background tasks
            self._start_background_tasks()
            
            # Run the server
            self.socketio.run(
                self.app, 
                host=host, 
                port=port, 
                debug=debug,
                allow_unsafe_werkzeug=debug  # Only for development
            )
            
        except KeyboardInterrupt:
            self.logger.info("Shutting down web interface...")
            self.shutdown()
        except Exception as e:
            self.logger.error(f"Web interface error: {e}")
            raise
            
    def shutdown(self):
        """Gracefully shutdown the web interface"""
        self.logger.info("Shutting down Spider Web Interface...")
        
        # Stop background tasks
        if self._stop_background_tasks:
            self._stop_background_tasks.set()
            
        if self._background_thread and self._background_thread.is_alive():
            self._background_thread.join(timeout=5)
            
        # Disconnect all clients
        for client_id in list(self.connected_clients):
            self.socketio.emit('server_shutdown', 
                             {'message': 'Server shutting down'}, 
                             room=client_id)
            
        self.connected_clients.clear()
        self.logger.info("Web interface shutdown complete")


# Factory function for easy instantiation
def create_spider_web_interface(spider_controller, visual_monitor, ai_thinking,
                               oled_display: Optional[OLEDDisplay] = None,
                               config: Optional[Dict[str, Any]] = None) -> SpiderWebInterface:
    """
    Factory function to create a SpiderWebInterface instance
    
    Args:
        spider_controller: Robot movement controller
        visual_monitor: Computer vision system
        ai_thinking: AI processing system
        oled_display: Optional OLED display
        config: Optional configuration
        
    Returns:
        Configured SpiderWebInterface instance
    """
    default_config = {
        'secret_key': 'hey_spider_secret_key_2024',
        'cors_origins': "*",
        'socketio_logging': False,
        'engineio_logging': False,
        'log_level': 'INFO',
        'status_update_interval': 1.0,
        'video_frame_size': (320, 240),
        'video_quality': 70,
        'max_command_history': 100,
        'ping_timeout': 60,
        'ping_interval': 25
    }
    
    if config:
        default_config.update(config)
        
    return SpiderWebInterface(
        spider_controller=spider_controller,
        visual_monitor=visual_monitor,
        ai_thinking=ai_thinking,
        oled_display=oled_display,
        config=default_config
    )