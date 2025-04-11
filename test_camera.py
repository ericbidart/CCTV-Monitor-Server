import cv2
import json
import os
import time
import argparse
from datetime import datetime

def test_camera(camera_url, output_dir=None, duration=10):
    """Test connection to a camera and optionally save snapshots."""
    # Create output directory if specified
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"Connecting to camera: {camera_url}")
    
    # Open video capture
    cap = cv2.VideoCapture(camera_url)
    
    if not cap.isOpened():
        print("Failed to open camera stream!")
        return False
    
    print("Camera connected successfully")
    
    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    print(f"Camera properties: {width}x{height} @ {fps:.2f} FPS")
    
    # Record start time
    start_time = time.time()
    frame_count = 0
    
    try:
        while time.time() - start_time < duration:
            # Read frame
            ret, frame = cap.read()
            
            if not ret:
                print("Failed to read frame!")
                break
            
            frame_count += 1
            
            # Save snapshot if output directory specified
            if output_dir and frame_count % 30 == 0:  # Save every 30 frames
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(output_dir, f"snapshot_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                print(f"Saved snapshot to {filename}")
            
            # Display stats every second
            if frame_count % 10 == 0:
                elapsed = time.time() - start_time
                current_fps = frame_count / elapsed
                print(f"Received {frame_count} frames in {elapsed:.2f} seconds ({current_fps:.2f} FPS)")
    
    except KeyboardInterrupt:
        print("Test interrupted by user")
    
    finally:
        # Release camera
        cap.release()
        
        if frame_count > 0:
            total_time = time.time() - start_time
            avg_fps = frame_count / total_time
            print(f"\nTest completed. Captured {frame_count} frames in {total_time:.2f} seconds")
            print(f"Average FPS: {avg_fps:.2f}")
            return True
        else:
            print("\nTest failed. No frames were captured.")
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test camera connection")
    parser.add_argument("--url", help="Camera URL (e.g., rtsp://admin:password@192.168.1.100:554/cam/realmonitor)")
    parser.add_argument("--config", help="Path to config file with camera information")
    parser.add_argument("--camera", help="Camera name from config file")
    parser.add_argument("--output", help="Directory to save snapshots")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    
    args = parser.parse_args()
    
    camera_url = None
    
    # Get camera URL from config if specified
    if args.config and args.camera:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
                
            for camera in config.get("cameras", []):
                if camera.get("name") == args.camera:
                    camera_url = camera.get("url")
                    break
                    
            if not camera_url:
                print(f"Camera '{args.camera}' not found in config")
                exit(1)
                
        except Exception as e:
            print(f"Error loading config: {e}")
            exit(1)
    
    # Use direct URL if provided
    elif args.url:
        camera_url = args.url
    
    # No camera specified
    else:
        print("Please specify either --url or both --config and --camera")
        exit(1)
    
    # Run the test
    success = test_camera(camera_url, args.output, args.duration)
    
    # Exit with appropriate code
    exit(0 if success else 1)
