#!/usr/bin/env python3
import os
import json
import logging
import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("../logs/webui.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("WebUI")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()  # Generate a random secret key
app.config['EVENTS_DIR'] = '../events'
app.config['CONFIG_FILE'] = '../config/system.json'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for authentication
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Load system configuration
def load_config():
    try:
        with open(app.config['CONFIG_FILE'], 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {
            "cameras": [],
            "notifications": {
                "email": {"enabled": False},
                "push": {"enabled": False}
            },
            "web_interface": {
                "port": 8080,
                "username": "admin",
                "password": "admin"
            }
        }

# Save system configuration
def save_config(config):
    try:
        with open(app.config['CONFIG_FILE'], 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

# Load user from config
@login_manager.user_loader
def load_user(user_id):
    if user_id != '1':  # We only have one user for now
        return None
        
    config = load_config()
    web_config = config.get('web_interface', {})
    username = web_config.get('username', 'admin')
    password_hash = web_config.get('password_hash')
    
    # If no password hash exists, use default password
    if not password_hash:
        password_hash = generate_password_hash('admin')
        
    return User('1', username, password_hash)

# Routes
@app.route('/')
@login_required
def index():
    """Home page with system overview."""
    config = load_config()
    cameras = config.get('cameras', [])
    
    # Get recent events
    events = []
    events_dir = Path(app.config['EVENTS_DIR'])
    if events_dir.exists():
        event_files = list(events_dir.glob("*.json"))
        event_files.sort(key=os.path.getmtime, reverse=True)
        
        # Load the 10 most recent events
        for event_file in event_files[:10]:
            try:
                with open(event_file, 'r') as f:
                    event_data = json.load(f)
                    # Fix image path for web display
                    if 'image_path' in event_data:
                        image_name = os.path.basename(event_data['image_path'])
                        event_data['web_image_path'] = f'/events/{image_name}'
                    events.append(event_data)
            except Exception as e:
                logger.error(f"Error loading event file {event_file}: {e}")
    
    return render_template('index.html', 
                           cameras=cameras, 
                           events=events, 
                           config=config)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = load_user('1')  # We only have one user
        
        if user and user.username == username and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout."""
    logout_user()
    return redirect(url_for('login'))

@app.route('/cameras')
@login_required
def cameras():
    """Camera management page."""
    config = load_config()
    cameras = config.get('cameras', [])
    return render_template('cameras.html', cameras=cameras)

@app.route('/camera/add', methods=['POST'])
@login_required
def camera_add():
    """Add a new camera."""
    try:
        name = request.form.get('name')
        url = request.form.get('url')
        fps = int(request.form.get('fps', 5))
        
        # Get detections
        detections = []
        if request.form.get('detect_person'):
            detections.append('person')
        if request.form.get('detect_vehicle'):
            detections.append('vehicle')
        if request.form.get('detect_animal'):
            detections.append('animal')
        if request.form.get('detect_fire'):
            detections.append('fire')
        if request.form.get('detect_face'):
            detections.append('face')
            
        # Create camera config
        camera = {
            "name": name,
            "url": url,
            "enabled": True,
            "fps": fps,
            "detections": detections
        }
        
        # Load current config
        config = load_config()
        if 'cameras' not in config:
            config['cameras'] = []
            
        # Add camera
        config['cameras'].append(camera)
        
        # Save config
        if save_config(config):
            flash(f'Camera "{name}" added successfully')
        else:
            flash('Failed to save configuration')
            
    except Exception as e:
        logger.error(f"Error adding camera: {e}")
        flash(f'Error adding camera: {str(e)}')
        
    return redirect(url_for('cameras'))

@app.route('/camera/delete/<camera_name>')
@login_required
def camera_delete(camera_name):
    """Delete a camera."""
    try:
        config = load_config()
        cameras = config.get('cameras', [])
        
        # Find and remove the camera
        for i, camera in enumerate(cameras):
            if camera.get('name') == camera_name:
                cameras.pop(i)
                break
                
        # Save config
        if save_config(config):
            flash(f'Camera "{camera_name}" deleted successfully')
        else:
            flash('Failed to save configuration')
            
    except Exception as e:
        logger.error(f"Error deleting camera: {e}")
        flash(f'Error deleting camera: {str(e)}')
        
    return redirect(url_for('cameras'))

@app.route('/events')
@login_required
def events_page():
    """Events page."""
    # Get parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    camera = request.args.get('camera', None)
    event_type = request.args.get('type', None)
    
    # Get events
    events = []
    events_dir = Path(app.config['EVENTS_DIR'])
    if events_dir.exists():
        event_files = list(events_dir.glob("*.json"))
        event_files.sort(key=os.path.getmtime, reverse=True)
        
        # Filter events
        filtered_events = []
        for event_file in event_files:
            try:
                with open(event_file, 'r') as f:
                    event_data = json.load(f)
                    
                    # Apply filters
                    if camera and event_data.get('camera') != camera:
                        continue
                    if event_type and event_data.get('type') != event_type:
                        continue
                        
                    # Fix image path for web display
                    if 'image_path' in event_data:
                        image_name = os.path.basename(event_data['image_path'])
                        event_data['web_image_path'] = f'/events/{image_name}'
                        
                    filtered_events.append(event_data)
            except Exception as e:
                logger.error(f"Error loading event file {event_file}: {e}")
                
        # Paginate
        start = (page - 1) * per_page
        end = start + per_page
        events = filtered_events[start:end]
        total_pages = (len(filtered_events) + per_page - 1) // per_page
        
        # Get camera and event type lists for filtering
        config = load_config()
        cameras = [camera.get('name') for camera in config.get('cameras', [])]
        event_types = list(set(event.get('type') for event in filtered_events if 'type' in event))
        
    return render_template('events.html', 
                           events=events,
                           page=page,
                           total_pages=total_pages,
                           camera_filter=camera,
                           type_filter=event_type,
                           cameras=cameras,
                           event_types=event_types)

@app.route('/events/<path:filename>')
@login_required
def event_image(filename):
    """Serve event images."""
    return send_from_directory(app.config['EVENTS_DIR'], filename)

@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    config = load_config()
    return render_template('settings.html', config=config)

@app.route('/settings/save', methods=['POST'])
@login_required
def settings_save():
    """Save settings."""
    try:
        config = load_config()
        
        # Update web interface settings
        if 'web_interface' not in config:
            config['web_interface'] = {}
            
        web_config = config['web_interface']
        web_config['port'] = int(request.form.get('port', 8080))
        
        # Update username if provided
        new_username = request.form.get('username')
        if new_username and new_username != web_config.get('username'):
            web_config['username'] = new_username
            
        # Update password if provided
        new_password = request.form.get('password')
        if new_password:
            web_config['password_hash'] = generate_password_hash(new_password)
            
        # Update email settings
        if 'notifications' not in config:
            config['notifications'] = {}
        if 'email' not in config['notifications']:
            config['notifications']['email'] = {}
            
        email_config = config['notifications']['email']
        email_config['enabled'] = request.form.get('email_enabled') == 'on'
        email_config['smtp_server'] = request.form.get('smtp_server', '')
        email_config['smtp_port'] = int(request.form.get('smtp_port', 587))
        email_config['username'] = request.form.get('email_username', '')
        
        # Only update password if provided
        email_password = request.form.get('email_password')
        if email_password:
            email_config['password'] = email_password
            
        email_recipients = request.form.get('email_recipients', '')
        email_config['recipients'] = [r.strip() for r in email_recipients.split(',') if r.strip()]
        
        # Update push notification settings
        if 'push' not in config['notifications']:
            config['notifications']['push'] = {}
            
        push_config = config['notifications']['push']
        push_config['enabled'] = request.form.get('push_enabled') == 'on'
        push_config['service'] = request.form.get('push_service', 'firebase')
        
        # Only update API key if provided
        push_api_key = request.form.get('push_api_key')
        if push_api_key:
            push_config['api_key'] = push_api_key
            
        # Save config
        if save_config(config):
            flash('Settings saved successfully')
        else:
            flash('Failed to save settings')
            
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        flash(f'Error saving settings: {str(e)}')
        
    return redirect(url_for('settings'))

@app.route('/api/restart', methods=['POST'])
@login_required
def api_restart():
    """API endpoint to restart the system."""
    # Implement system restart logic here
    return jsonify({"status": "success", "message": "System restart initiated"})

@app.route('/security_zones/<camera_name>')
@login_required
def security_zones(camera_name):
    """Security zones configuration page."""
    try:
        config = load_config()
        cameras = config.get('cameras', [])
        
        # Find the specific camera
        camera = next((cam for cam in cameras if cam.get('name') == camera_name), None)
        if not camera:
            flash(f'Camera "{camera_name}" not found')
            return redirect(url_for('cameras'))
            
        # Get security zones for this camera
        security_zones = camera.get('security_zones', [])
        
        return render_template('security_zones.html', 
                              camera_name=camera_name, 
                              camera=camera,
                              security_zones=security_zones)
    except Exception as e:
        logger.error(f"Error loading security zones: {e}")
        flash(f'Error: {str(e)}')
        return redirect(url_for('cameras'))

@app.route('/camera_snapshot/<camera_name>')
@login_required
def camera_snapshot(camera_name):
    """Get a snapshot from the camera for zone configuration."""
    try:
        config = load_config()
        cameras = config.get('cameras', [])
        
        # Find the specific camera
        camera = next((cam for cam in cameras if cam.get('name') == camera_name), None)
        if not camera:
            return "Camera not found", 404
            
        # Try to get a snapshot
        import cv2
        cap = cv2.VideoCapture(camera.get('url'))
        if not cap.isOpened():
            return "Could not connect to camera", 500
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return "Could not get frame from camera", 500
            
        # Save snapshot to a temporary file
        snapshot_dir = Path("static/img/snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_path = snapshot_dir / f"{camera_name}_snapshot.jpg"
        cv2.imwrite(str(snapshot_path), frame)
        
        # Return the image
        return send_from_directory("static/img/snapshots", f"{camera_name}_snapshot.jpg")
    except Exception as e:
        logger.error(f"Error getting camera snapshot: {e}")
        return "Error getting snapshot", 500

@app.route('/save_security_zones/<camera_name>', methods=['POST'])
@login_required
def save_security_zones(camera_name):
    """Save security zones for a camera."""
    try:
        # Get zone data from form
        zone_coordinates = request.form.get('zoneCoordinates')
        if not zone_coordinates:
            flash('No zone coordinates provided')
            return redirect(url_for('security_zones', camera_name=camera_name))
            
        # Parse zones
        zones = json.loads(zone_coordinates)
        
        # Update config
        config = load_config()
        cameras = config.get('cameras', [])
        
        for i, camera in enumerate(cameras):
            if camera.get('name') == camera_name:
                cameras[i]['security_zones'] = zones
                break
        
        # Save updated config
        if save_config(config):
            flash('Security zones saved successfully')
        else:
            flash('Failed to save security zones')
            
        return redirect(url_for('security_zones', camera_name=camera_name))
    except Exception as e:
        logger.error(f"Error saving security zones: {e}")
        flash(f'Error: {str(e)}')
        return redirect(url_for('cameras'))


# Run the app
if __name__ == '__main__':
    # Get web interface port from config
    config = load_config()
    port = config.get('web_interface', {}).get('port', 8080)
    
    app.run(host='0.0.0.0', port=port, debug=True)
