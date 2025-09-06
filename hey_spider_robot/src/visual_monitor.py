import threading
import time
import os
from datetime import datetime
from typing import List, Dict, Optional

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    print("OpenCV not available - camera disabled")
    OPENCV_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("YOLO not available - object detection disabled")
    YOLO_AVAILABLE = False

from src.oled_display import OLEDDisplay

class VisualMonitor:
    def __init__(self, oled_display: Optional[OLEDDisplay] = None):
        self.oled = oled_display
        self.camera = None
        self.model = None
        self.running = False
        self.capture_thread = None
        self.latest_detections = []
        self.latest_frame = None
        
        # Initialize camera
        if OPENCV_AVAILABLE:
            try:
                self.camera = cv2.VideoCapture(0)
                if self.camera.isOpened():
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    self.camera.set(cv2.CAP_PROP_FPS, 15)
                    print("Camera initialized successfully")
                else:
                    print("Camera not available")
                    self.camera = None
            except Exception as e:
                print(f"Camera initialization error: {e}")
                self.camera = None
        else:
            print("Camera disabled - OpenCV not available")
            
        # Initialize YOLO model
        if YOLO_AVAILABLE:
            try:
                self.model = YOLO('yolov8n.pt')
                print("YOLO model loaded successfully")
            except Exception as e:
                print(f"YOLO model loading error: {e}")
                self.model = None
        else:
            print("Object detection disabled - YOLO not available")
            
        # Create images directory
        os.makedirs('images', exist_ok=True)
        
        # Generate mock frame for testing
        if not self.camera:
            self._generate_mock_frame()
        
    def _generate_mock_frame(self):
        """Generate a mock frame for testing when camera is not available"""
        try:
            import numpy as np
            # Create a simple test image
            self.latest_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            self.latest_frame[100:380, 100:540] = [64, 64, 128]  # Dark blue rectangle
            # Add some text
            if OPENCV_AVAILABLE:
                cv2.putText(self.latest_frame, "MOCK CAMERA", (200, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        except:
            self.latest_frame = None
        
    def start_monitoring(self):
        """Start the visual monitoring thread"""
        self.running = True
        self.capture_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.capture_thread.start()
        print("Visual monitoring started")
        
    def stop_monitoring(self):
        """Stop visual monitoring"""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
            
    def _monitoring_loop(self):
        """Main monitoring loop"""
        last_capture = 0
        frame_count = 0
        
        while self.running:
            try:
                if self.camera and self.camera.isOpened():
                    # Capture frame from camera
                    ret, frame = self.camera.read()
                    if ret:
                        self.latest_frame = frame
                        frame_count += 1
                        
                        # Auto-capture and analyze every interval
                        current_time = time.time()
                        if current_time - last_capture >= 30:  # 30 seconds
                            self._process_frame(frame)
                            last_capture = current_time
                    else:
                        print("Failed to capture frame")
                        time.sleep(1)
                else:
                    # Use mock frame when camera not available
                    if frame_count % 30 == 0:  # Occasionally update mock detections
                        self._generate_mock_detections()
                    frame_count += 1
                    
                time.sleep(0.1)  # ~10 FPS
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(1)
                
    def _generate_mock_detections(self):
        """Generate mock detections for testing"""
        import random
        mock_objects = ['person', 'chair', 'laptop', 'cup', 'book', 'phone']
        
        # Randomly generate 0-3 detections
        num_detections = random.randint(0, 3)
        detections = []
        
        for _ in range(num_detections):
            obj_class = random.choice(mock_objects)
            confidence = random.uniform(0.6, 0.95)
            bbox = [
                random.randint(50, 300),  # x1
                random.randint(50, 200),  # y1
                random.randint(350, 590), # x2
                random.randint(250, 430)  # y2
            ]
            
            detections.append({
                'class': obj_class,
                'confidence': confidence,
                'bbox': bbox
            })
            
        self.latest_detections = detections
        if self.oled:
            self.oled.update_detections(detections)
            
        print(f"Mock detections: {len(detections)} objects")
        
    def _process_frame(self, frame):
        """Process frame for object detection"""
        if not self.model:
            self._generate_mock_detections()
            return self.latest_detections
            
        try:
            if self.oled:
                self.oled.update_mode("ANALYZING")
                
            # Run YOLO detection
            results = self.model(frame, verbose=False)
            
            detections = []
            for result in results:
                if hasattr(result, 'boxes') and result.boxes is not None:
                    for box in result.boxes:
                        if box.conf[0] > 0.5:  # Confidence threshold
                            class_id = int(box.cls[0])
                            class_name = self.model.names[class_id]
                            confidence = float(box.conf[0])
                            
                            detections.append({
                                'class': class_name,
                                'confidence': confidence,
                                'bbox': box.xyxy[0].tolist()
                            })
                        
            self.latest_detections = detections
            
            if self.oled:
                self.oled.update_detections(detections)
                self.oled.update_mode("READY")
                
            # Save annotated image if detections found
            if detections and OPENCV_AVAILABLE:
                try:
                    annotated_frame = results[0].plot()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"images/detection_{timestamp}.jpg"
                    cv2.imwrite(filename, annotated_frame)
                    print(f"Saved detection image: {filename}")
                except Exception as e:
                    print(f"Error saving annotated image: {e}")
                
            return detections
            
        except Exception as e:
            print(f"Frame processing error: {e}")
            if self.oled:
                self.oled.update_mode("ERROR")
            return []
        finally:
            if self.oled:
                self.oled.update_mode("READY")
            
    def capture_photo(self) -> str:
        """Manually capture and save a photo"""
        try:
            frame_to_save = self.latest_frame
            if frame_to_save is not None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"images/photo_{timestamp}.jpg"
                
                if OPENCV_AVAILABLE:
                    success = cv2.imwrite(filename, frame_to_save)
                    if success:
                        print(f"Photo saved: {filename}")
                        
                        # Also run detection on manual capture
                        detections = self._process_frame(frame_to_save)
                        return filename
                    else:
                        print("Failed to save photo")
                        return ""
                else:
                    print("Photo capture unavailable - OpenCV not available")
                    return ""
            else:
                print("No frame available for capture")
                return ""
                
        except Exception as e:
            print(f"Photo capture error: {e}")
            return ""
            
    def get_latest_detections(self) -> List[Dict]:
        """Get the latest detection results"""
        return self.latest_detections.copy()
        
    def get_detection_description(self) -> str:
        """Get natural language description of detections"""
        if not self.latest_detections:
            return "I don't see anything interesting."
            
        # Count objects by class
        object_counts = {}
        for detection in self.latest_detections:
            class_name = detection['class']
            object_counts[class_name] = object_counts.get(class_name, 0) + 1
            
        # Create description
        descriptions = []
        for obj_class, count in object_counts.items():
            if count == 1:
                descriptions.append(f"1 {obj_class}")
            else:
                descriptions.append(f"{count} {obj_class}s")
                
        if len(descriptions) == 1:
            return f"I can see {descriptions[0]}."
        elif len(descriptions) == 2:
            return f"I can see {descriptions[0]} and {descriptions[1]}."
        else:
            return f"I can see {', '.join(descriptions[:-1])}, and {descriptions[-1]}."
            
    def get_latest_frame(self):
        """Get the latest camera frame"""
        return self.latest_frame
        
    def cleanup(self):
        """Clean up camera resources"""
        if self.camera and self.camera.isOpened():
            self.camera.release()
            print("Camera resources cleaned up")