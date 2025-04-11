#!/usr/bin/env python3
import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/email_notifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EmailNotifier")

class EmailNotifier:
    def __init__(self, config_path="config/system.json"):
        """Initialize the email notifier."""
        self.config_path = config_path
        self.load_config()
        
    def load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
            # Get email configuration
            self.email_config = config.get('notifications', {}).get('email', {})
            self.enabled = self.email_config.get('enabled', False)
            
            if not self.enabled:
                logger.info("Email notifications are disabled")
                return
                
            # Check required fields
            required_fields = ['smtp_server', 'smtp_port', 'username', 'password', 'recipients']
            for field in required_fields:
                if not self.email_config.get(field):
                    logger.warning(f"Missing required field '{field}' in email configuration")
                    self.enabled = False
                    return
                    
            logger.info("Email notifier initialized successfully")
            
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.enabled = False
            
    def send_notification(self, event_data):
        """Send email notification for an event."""
        if not self.enabled:
            logger.info("Email notifications are disabled, not sending")
            return False
            
        try:
            # Extract event information
            camera = event_data.get('camera', 'Unknown')
            event_type = event_data.get('type', 'Unknown')
            timestamp = event_data.get('timestamp', 'Unknown')
            image_path = event_data.get('image_path')
            objects = event_data.get('objects', [])
            
            # Create email subject
            subject = f"CCTV Alert: {event_type.capitalize()} detected on {camera}"
            
            # Create email body
            html_body = f"""
            <html>
            <body>
                <h2>CCTV Intelligence System Alert</h2>
                <p><strong>Camera:</strong> {camera}</p>
                <p><strong>Detection:</strong> {event_type.capitalize()}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                <p><strong>Objects Detected:</strong> {len(objects)}</p>
                <div>
                    <p>Detection Image:</p>
                    <img src="cid:detection_image" style="max-width: 100%; height: auto;" />
                </div>
                <p>
                    <em>This is an automated notification from your CCTV Intelligence System.</em>
                </p>
            </body>
            </html>
            """
            
            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.email_config['username']
            msg['To'] = ', '.join(self.email_config['recipients'])
            
            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Attach image if available
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as img_file:
                    img_data = img_file.read()
                    image = MIMEImage(img_data)
                    image.add_header('Content-ID', '<detection_image>')
                    image.add_header('Content-Disposition', 'inline', filename=os.path.basename(image_path))
                    msg.attach(image)
            
            # Connect to SMTP server
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['username'], self.email_config['password'])
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Sent email notification for {event_type} detection on {camera}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False

# Test code
if __name__ == "__main__":
    notifier = EmailNotifier()
    
    # Test notification
    test_event = {
        "camera": "Test Camera",
        "type": "person",
        "timestamp": "2025-04-02 12:34:56",
        "image_path": "events/test_image.jpg",  # Replace with an actual image path
        "objects": [{"class": "person", "confidence": 0.95}]
    }
    
    notifier.send_notification(test_event)
