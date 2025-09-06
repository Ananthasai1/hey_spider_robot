#!/usr/bin/env python3
"""
Hey Spider Robot with OLED Display - Main Application
Complete AI-powered spider robot system with visual feedback and modern OpenAI API integration
"""

import sys
import time
import signal
import json
from config.settings import settings
from src.spider_controller import SpiderController
from src.voice_activation import VoiceActivation
from src.visual_monitor import VisualMonitor
from src.ai_thinking import AIThinking
from src.oled_display import OLEDDisplay
from src.web_interface import WebInterface

class HeySpiderRobot:
    def __init__(self):
        print("Initializing Hey Spider Robot with OLED Display...")
        print(f"OpenAI API Key configured: {'Yes' if settings.OPENAI_API_KEY else 'No (set OPENAI_API_KEY environment variable)'}")
        
        # Initialize OLED display first
        self.oled = OLEDDisplay()
        self.oled.show_startup_message()
        self.oled.start()
        
        # Initialize core systems
        print("Initializing spider controller...")
        self.spider = SpiderController(self.oled)
        
        print("Initializing visual monitoring...")
        self.vision = VisualMonitor(self.oled)
        
        print("Initializing AI thinking...")
        self.ai = AIThinking(self.spider, self.vision, self.oled)
        
        # Initialize voice system with command handler
        print("Initializing voice activation...")
        self.voice = VoiceActivation(self.handle_voice_command, self.oled)
        
        # Initialize web interface
        print("Initializing web interface...")
        self.web = WebInterface(self.spider, self.vision, self.ai, self.oled)
        
        self.running = False
        print("Hey Spider Robot initialization complete!")
        
    def handle_voice_command(self, command: str):
        """Handle voice commands"""
        print(f"Processing voice command: {command}")
        
        if self.oled:
            self.oled.update_command(command)
            
        try:
            # Basic movement commands
            if any(word in command for word in ['forward', 'walk', 'move']):
                self.spider.walk_forward()
                
            elif 'left' in command:
                self.spider.turn_left()
                
            elif 'right' in command:
                self.spider.turn_right()
                
            elif 'dance' in command:
                self.spider.dance()
                
            elif 'wave' in command:
                self.spider.wave()
                
            elif any(word in command for word in ['photo', 'picture', 'capture']):
                filename = self.vision.capture_photo()
                print(f"Photo captured: {filename}" if filename else "Photo capture failed")
                
            elif 'stop' in command:
                print("Stopping robot...")
                if self.oled:
                    self.oled.update_mode("STOPPED")
                    
            else:
                # Use AI to process unknown commands
                try:
                    ai_response = self.ai.process_command(command)
                    parsed_response = json.loads(ai_response)
                    action = parsed_response.get('action', 'unknown')
                    response_message = parsed_response.get('response', 'Command processed')
                    
                    print(f"AI Response: {response_message}")
                    
                    # Execute AI-determined action
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
                    elif action == 'unknown':
                        print(f"Unknown command: {command}")
                        
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"AI response parsing error: {e}")
                    print("Could not understand command")
                
        except Exception as e:
            print(f"Command execution error: {e}")
            if self.oled:
                self.oled.update_mode("ERROR")
                time.sleep(2)
                
        finally:
            if self.oled:
                self.oled.update_mode("LISTENING")
                
    def start(self):
        """Start all robot systems"""
        print("\n" + "="*50)
        print("Starting Hey Spider Robot systems...")
        print("="*50)
        
        self.running = True
        
        # Start all subsystems
        print("Starting visual monitoring...")
        self.vision.start_monitoring()
        
        print("Starting AI thinking...")
        self.ai.start_thinking()
        
        print("Starting voice activation...")
        self.voice.start_listening()
        
        if self.oled:
            self.oled.update_mode("ACTIVE")
            
        print("\n" + "="*50)
        print("🕷️  HEY SPIDER ROBOT IS NOW ACTIVE! 🕷️")
        print("="*50)
        print("📢 Voice Commands:")
        print("   - Say 'Hey Spider' followed by a command")
        print("   - Available commands: walk forward, turn left/right, dance, wave, take photo")
        print("🌐 Web Interface:")
        print(f"   - Available at: http://localhost:{settings.WEB_PORT}")
        print("📺 OLED Display:")
        print("   - Showing real-time status")
        print("🤖 AI Features:")
        print("   - Object detection with YOLO")
        print("   - Natural language processing")
        print("   - Autonomous thinking")
        print("="*50)
        print("Press Ctrl+C to stop")
        print("="*50 + "\n")
        
        # Start web interface (this will block)
        try:
            self.web.run(host='0.0.0.0', port=settings.WEB_PORT, debug=False)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            print(f"Web interface error: {e}")
            self.stop()
            
    def stop(self):
        """Stop all robot systems"""
        print("\n" + "="*40)
        print("Stopping Hey Spider Robot...")
        print("="*40)
        
        self.running = False
        
        if self.oled:
            self.oled.update_mode("SHUTDOWN")
            
        # Stop all subsystems
        print("Stopping voice activation...")
        self.voice.stop_listening()
        
        print("Stopping visual monitoring...")
        self.vision.stop_monitoring()
        
        print("Stopping AI thinking...")
        self.ai.stop_thinking()
        
        print("Stopping OLED display...")
        self.oled.stop()
        
        # Cleanup hardware
        print("Cleaning up hardware...")
        self.spider.cleanup()
        self.vision.cleanup()
        
        print("="*40)
        print("Hey Spider Robot stopped safely.")
        print("="*40)
        
    def signal_handler(self, signum, frame):
        """Handle system signals"""
        print(f"\nReceived signal {signum}")
        self.stop()
        sys.exit(0)

def main():
    """Main application entry point"""
    print("🕷️ HEY SPIDER ROBOT - Starting up...")
    print("Hardware compatibility: Raspberry Pi with servo/camera/sensor support")
    print("Software compatibility: Can run with or without hardware (mock mode)")
    
    try:
        robot = HeySpiderRobot()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, robot.signal_handler)
        signal.signal(signal.SIGTERM, robot.signal_handler)
        
        robot.start()
        
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()