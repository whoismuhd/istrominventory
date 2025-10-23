"""
Email Service Module
Handles all email notifications and communications
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# Email Configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': os.getenv('EMAIL_USERNAME', 'muhammadauw04@gmail.com'),
    'password': os.getenv('EMAIL_PASSWORD', 'your-app-password'),
    'from_name': 'Istrom Inventory'
}

def send_email(to_email, subject, body, is_html=False):
    """Send email using Gmail SMTP"""
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{EMAIL_CONFIG['from_name']} <{EMAIL_CONFIG['username']}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Connect to server and send
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
        return False

def send_request_notification_email(requester_name, requester_email, item_name, qty, request_id):
    """Send email notification when a request is made"""
    subject = f"🔔 New Request #{request_id} - {item_name}"
    
    body = f"""
    Hello Admin,
    
    A new request has been submitted:
    
    📋 Request Details:
    • Request ID: #{request_id}
    • Item: {item_name}
    • Quantity: {qty} units
    • Requested by: {requester_name}
    • Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Please log in to the system to review and approve/reject this request.
    
    Best regards,
    Istrom Inventory
    """
    
    return send_email(EMAIL_CONFIG['username'], subject, body)

def send_approval_notification_email(requester_name, requester_email, item_name, qty, request_id, status):
    """Send email notification to admin when request is approved/rejected"""
    status_emoji = "✅" if status == "Approved" else "❌"
    status_text = "APPROVED" if status == "Approved" else "REJECTED"
    
    subject = f"{status_emoji} Request #{request_id} {status_text} - {item_name}"
    
    body = f"""
    Hello Admin,
    
    A request has been {status.lower()}:
    
    📋 Request Details:
    • Request ID: #{request_id}
    • Item: {item_name}
    • Quantity: {qty} units
    • Requested by: {requester_name}
    • Status: {status}
    • Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Best regards,
    Istrom Inventory
    """
    
    return send_email(EMAIL_CONFIG['username'], subject, body)

def send_user_notification_email(requester_name, requester_email, item_name, qty, request_id, status):
    """Send email notification to user when request is approved/rejected"""
    status_emoji = "✅" if status == "Approved" else "❌"
    status_text = "APPROVED" if status == "Approved" else "REJECTED"
    
    subject = f"{status_emoji} Your Request #{request_id} has been {status_text}"
    
    body = f"""
    Hello {requester_name},
    
    Your request has been {status.lower()}:
    
    📋 Request Details:
    • Request ID: #{request_id}
    • Item: {item_name}
    • Quantity: {qty} units
    • Status: {status}
    • Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Thank you for using Istrom Inventory Management System.
    
    Best regards,
    Istrom Inventory Team
    """
    
    return send_email(requester_email, subject, body)

def send_system_notification_email(subject, message, to_email=None):
    """Send system notification email"""
    if to_email is None:
        to_email = EMAIL_CONFIG['username']
    
    body = f"""
    System Notification:
    
    {message}
    
    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Best regards,
    Istrom Inventory System
    """
    
    return send_email(to_email, subject, body)

def send_inventory_alert_email(item_name, current_qty, threshold_qty):
    """Send inventory alert email when quantity is low"""
    subject = f"⚠️ Low Stock Alert - {item_name}"
    
    body = f"""
    Inventory Alert:
    
    📦 Item: {item_name}
    📊 Current Quantity: {current_qty}
    ⚠️ Threshold: {threshold_qty}
    
    Please restock this item as soon as possible.
    
    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Best regards,
    Istrom Inventory System
    """
    
    return send_email(EMAIL_CONFIG['username'], subject, body)
