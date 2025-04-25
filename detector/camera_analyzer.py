#!/usr/bin/env python3
import os
import cv2
import time
import json
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime
import numpy as np
from ultralytics import YOLO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/camera_analyzer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CameraAnalyzer")

class CameraAnalyzer:
    def __init__(self, config_path):
        """Initialize the Camera Analyzer with the provided configuration."""
        self.config_path = config_path
        self.load_config()
        self.setup_models()
        self.last_detection_time = {}
        self.running = False
        self.threads = []
        
        # Create output directories
        os.makedirs("events", exist_ok=True)
        
    def load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
            
    def setup_models(self):
        """Initialize detection models."""
        try:
            logger.info("Loading YOLOv8 model...")
            # Load YOLOv8 model
            self.model = YOLO("yolov8n.pt")  # Use small model for speed
            logger.info("YOLOv8 model loaded successfully")
            
        except Exception as e:
            logger.error(f"Error setting up models: {e}")
            raise
    
    def process_camera(self, camera_config):
        """Process video from a camera."""
        camera_name = camera_config.get("name", "Unknown")
        camera_url = camera_config.get("url")
        
        if not camera_url:
            logger.error(f"No URL provided for camera {camera_name}")
            return
            
        logger.info(f"Starting processing for camera: {camera_name}")
        
        # Get detection settings
        detections_enabled = camera_config.get("detections", ["person", "vehicle"])
        fps = camera_config.get("fps", 5)
        frame_interval = 1.0 / fps
        
        try:
            # Open the video stream
            cap = cv2.VideoCapture(camera_url)
            if not cap.isOpened():
                logger.error(f"Failed to open camera stream: {camera_url}")
                return
                
            last_frame_time = 0
                
            while self.running:
                # Control processing rate
                current_time = time.time()
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.01)  # Sleep to prevent CPU overuse
                    continue
                    
                last_frame_time = current_time
                
                # Read frame
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame from {camera_name}, reconnecting...")
                    cap.release()
                    time.sleep(5)
                    cap = cv2.VideoCapture(camera_url)
                    continue
                
                # Process frame - object detection
                if any(d in ["person", "vehicle", "animal"] for d in detections_enabled):
                    self.detect_objects(frame, camera_name, detections_enabled)
                    
        except Exception as e:
            logger.error(f"Error processing camera {camera_name}: {e}")
        finally:
            if 'cap' in locals() and cap is not None:
                cap.release()
    
    def detect_objects(self, frame, camera_name, enabled_detections):
        """Detect objects in frame using YOLOv8."""
        try:
            # Detection classes of interest
            class_mapping = {
                "person": ["person"],
                "vehicle": ["car", "truck", "bus", "motorcycle"],
                "animal": ["dog", "cat", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"]
            }
            
            # Classes to detect
            classes_to_detect = []
            for detection_type in enabled_detections:
                if detection_type in class_mapping:
                    classes_to_detect.extend(class_mapping[detection_type])
            
            # Run YOLOv8 detection
            results = self.model(frame, verbose=False)
            
            # Process results
            for result in results:
                boxes = result.boxes
                found_objects = {}
                
                for box in boxes:
                    # Get class information
                    class_id = int(box.cls[0])
                    class_name = result.names[class_id]
                    confidence = float(box.conf[0])
                    
                    # Check if this class is one we want to detect
                    detection_type = None
                    for d_type, classes in class_mapping.items():
                        if class_name in classes and d_type in enabled_detections:
                            detection_type = d_type
                            break
                            
                    if not detection_type:
                        continue
                        
                    # Check minimum confidence (0.5 by default)
                    if confidence < 0.5:
                        continue
                        
                    # Get bounding box
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    
                    # Add to found objects
                    if detection_type not in found_objects:
                        found_objects[detection_type] = []
                        
                    found_objects[detection_type].append({
                        "confidence": confidence,
                        "bbox": [x1, y1, x2, y2],
                        "class": class_name
                    })
                    
                # Process detected objects
                for detection_type, objects in found_objects.items():
                    if objects:
                        # Check cooldown period (1 minute by default)
                        current_time = time.time()
                        key = f"{camera_name}_{detection_type}"
                        
                        if key in self.last_detection_time:
                            time_since_last = current_time - self.last_detection_time[key]
                            if time_since_last < 60:  # 60 seconds cooldown
                                continue
                                
                        # Update last detection time
                        self.last_detection_time[key] = current_time
                        
                        # Save event
                        self.save_detection_event(frame, camera_name, detection_type, objects)
                        
        except Exception as e:
            logger.error(f"Error in object detection: {e}")
    
    def save_detection_event(self, frame, camera_name, detection_type, objects):
        """Save detection event with annotated image."""
        try:
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            event_dir = Path("events")
            image_filename = f"{camera_name}_{detection_type}_{timestamp}.jpg"
            image_path = event_dir / image_filename
            
            # Create annotated image
            annotated_frame = frame.copy()
            
            # Draw bounding boxes
            for obj in objects:
                bbox = obj["bbox"]
                conf = obj["confidence"]
                class_name = obj["class"]
                
                # Draw box
                cv2.rectangle(annotated_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
                
                # Add label
                label = f"{class_name}: {conf:.2f}"
                cv2.putText(
                    annotated_frame, 
                    label, 
                    (bbox[0], bbox[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    (0, 255, 0), 
                    2
                )
            
            # Save image
            cv2.imwrite(str(image_path), annotated_frame)
            
            # Convert NumPy types to Python native types
            serializable_objects = []
            for obj in objects:
                serializable_obj = {
                    "confidence": float(obj["confidence"]),
                    "class": str(obj["class"]),
                    "bbox": [int(x) for x in obj["bbox"]]
                }
                serializable_objects.append(serializable_obj)
            
            # Create event data
            event_data = {
                "camera": camera_name,
                "type": detection_type,
                "timestamp": timestamp,
                "image_path": str(image_path),
                "objects": serializable_objects
            }
            
            # Save event data
            event_data_path = event_dir / f"{camera_name}_{detection_type}_{timestamp}.json"
            with open(event_data_path, 'w') as f:
                json.dump(event_data, f, indent=2)
                
            logger.info(f"Saved detection event: {camera_name} - {detection_type} - {timestamp}")
            
            # Print detection notification to console
            print(f"DETECTION: {camera_name} - {detection_type} - {len(objects)} objects found")
            
            # Send notifications
            try:
                # Import email notifier
                import sys
                sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
                from notifications.email_notifier import EmailNotifier
                
                # Send email notification
                email_notifier = EmailNotifier(self.config_path)
                email_notifier.send_notification(event_data)
            except Exception as e:
                logger.error(f"Error sending notifications: {e}")
            
        except Exception as e:
            logger.error(f"Error saving detection event: {e}")
    
    def start(self):
        """Start processing all cameras."""
        if self.running:
            logger.warning("Camera analyzer is already running")
            return
            
        self.running = True
        self.threads = []
        
        # Start a thread for each camera
        for camera in self.config.get("cameras", []):
            if camera.get("enabled", True):
                thread = threading.Thread(
                    target=self.process_camera,
                    args=(camera,),
                    daemon=True
                )
                self.threads.append(thread)
                thread.start()
                
        logger.info(f"Started processing {len(self.threads)} cameras")
    
    def stop(self):
        """Stop all processing."""
        if not self.running:
            logger.warning("Camera analyzer is not running")
            return
            
        logger.info("Stopping camera analyzer...")
        self.running = False
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5.0)
            
        self.threads = []
        logger.info("Camera analyzer stopped")

    def cleanup_old_images(self, max_age_days=7, max_files=1000):
    """
    Clean up old detection images to prevent storage issues.
    
    Args:
        max_age_days: Delete images older than this many days
        max_files: Maximum number of image files to keep
    """
    try:
        event_dir = Path("events")
        if not event_dir.exists():
            return
            
        # Get all image files
        image_files = list(event_dir.glob("*.jpg"))
        
        # Sort by modification time (oldest first)
        image_files.sort(key=lambda x: x.stat().st_mtime)
        
        # Calculate cutoff date
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        # Track how many files were deleted
        deleted_count = 0
        
        # Delete old files and ensure we don't exceed max_files
        for file_path in image_files:
            should_delete = False
            
            # Check if file is older than max_age_days
            if file_path.stat().st_mtime < cutoff_time:
                should_delete = True
                
            # Check if we have too many files (leave room for new ones)
            if len(image_files) - deleted_count > max_files:
                should_delete = True
                
            if should_delete:
                # Also delete corresponding JSON file if it exists
                json_path = file_path.with_suffix('.json')
                if json_path.exists():
                    json_path.unlink()
                    
                # Delete the image
                file_path.unlink()
                deleted_count += 1
                
        if deleted_count > 0:
            logger.info(f"Cleanup: Deleted {deleted_count} old image files")
            
    except Exception as e:
        logger.error(f"Error cleaning up old images: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Camera Analyzer")
    parser.add_argument("--config", default="config/system.json", help="Path to configuration file")
    args = parser.parse_args()
    
    analyzer = CameraAnalyzer(args.config)
    analyzer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        analyzer.stop()
