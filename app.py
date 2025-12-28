# Tasker/Join Configuration for Android:
# For incoming SMS forwarding: POST to YOUR_APP_URL/android-webhook
# JSON payload MUST be: {"sender": "+1234567890", "body": "SMS text here"}
# Configure Tasker to send exactly this format.

import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load environment variables
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS')
ANDROID_SEND_URL = os.environ.get('ANDROID_SEND_URL')
CRON_SECRET = os.environ.get('CRON_SECRET')


def send_sms_via_android(message_text):
    """
    Send SMS via Android phone using Tasker/Join.
    Makes a GET request to ANDROID_SEND_URL with message_text as query param.
    """
    try:
        params = {'message': message_text}
        response = requests.get(ANDROID_SEND_URL, params=params)
        response.raise_for_status()
        logger.info(f"SMS sent successfully: {message_text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS: {str(e)}")
        return False


def get_google_sheets_client():
    """
    Authenticate with Google Sheets using service account credentials.
    Returns gspread client.
    """
    try:
        credentials_dict = json.loads(GOOGLE_CREDENTIALS)
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            credentials_dict,
            ['https://spreadsheets.google.com/feeds']
        )
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Sheets: {str(e)}")
        return None


def append_to_google_sheets(data):
    """
    Append a row to the HealthLog Google Sheet.
    data: list of values to append [date, time, body, urgency]
    """
    try:
        client = get_google_sheets_client()
        if not client:
            return False
        
        sheet = client.open("HealthLog").sheet1
        sheet.append_row(data)
        logger.info(f"Appended to Google Sheets: {data}")
        return True
    except Exception as e:
        logger.error(f"Failed to append to Google Sheets: {str(e)}")
        return False


def get_last_rows(sheet, num_rows=3):
    """
    Get the last N rows from the sheet (excluding header).
    Returns list of rows.
    """
    try:
        all_values = sheet.get_all_values()
        if len(all_values) <= 1:  # Only header or empty
            return []
        return all_values[-num_rows:] if len(all_values) > 1 else []
    except Exception as e:
        logger.error(f"Failed to get last rows: {str(e)}")
        return []


def parse_urgency_from_body(body):
    """
    Parse urgency rating (1-10) from message body.
    Returns the first number found between 1-10, or None if not found.
    """
    import re
    matches = re.findall(r'\b([1-9]|10)\b', body)
    if matches:
        return int(matches[0])
    return None


@app.route('/trigger-daily-checkin', methods=['GET'])
def trigger_daily_checkin():
    """
    Trigger route for daily check-in SMS.
    Protected by CRON_SECRET.
    """
    try:
        # Verify secret
        provided_secret = request.args.get('secret')
        if provided_secret != CRON_SECRET:
            logger.warning("Unauthorized trigger attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Send check-in SMS
        message = "How were your symptoms today? Rate urgency (1-10) and describe."
        success = send_sms_via_android(message)
        
        if success:
            return "Triggered"
        else:
            return jsonify({'error': 'Failed to send SMS'}), 500
            
    except Exception as e:
        logger.error(f"Error in trigger_daily_checkin: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/android-webhook', methods=['POST'])
def android_webhook():
    """
    Webhook to receive incoming SMS from Android.
    Handles data entry and retrieval requests.
    """
    try:
        # Parse JSON payload
        data = request.json
        if not data or 'sender' not in data or 'body' not in data:
            logger.error("Invalid payload received")
            return jsonify({'error': 'Invalid payload'}), 400
        
        sender = data['sender']
        body = data['body'].strip()
        body_lower = body.lower()
        
        logger.info(f"Received SMS from {sender}: {body}")
        
        # Branch B: Retrieval requests
        if 'link' in body_lower:
            try:
                client = get_google_sheets_client()
                if client:
                    sheet = client.open("HealthLog").sheet1
                    sheet_url = sheet.spreadsheet.url
                    send_sms_via_android(f"Health Log Link: {sheet_url}")
                else:
                    send_sms_via_android("Failed to retrieve sheet link.")
            except Exception as e:
                logger.error(f"Error getting sheet link: {str(e)}")
                send_sms_via_android("Failed to retrieve sheet link.")
            return jsonify({'status': 'link sent'})
        
        elif 'summary' in body_lower:
            try:
                client = get_google_sheets_client()
                if client:
                    sheet = client.open("HealthLog").sheet1
                    last_rows = get_last_rows(sheet, 3)
                    if last_rows:
                        summary_lines = []
                        for i, row in enumerate(last_rows, 1):
                            if len(row) >= 4:
                                summary_lines.append(f"{i}. {row[0]} {row[1]} - Urgency: {row[3]}")
                            else:
                                summary_lines.append(f"{i}. {row}")
                        summary = "\n".join(summary_lines)
                        send_sms_via_android(f"Last 3 entries:\n{summary}")
                    else:
                        send_sms_via_android("No entries found in Health Log.")
                else:
                    send_sms_via_android("Failed to retrieve summary.")
            except Exception as e:
                logger.error(f"Error getting summary: {str(e)}")
                send_sms_via_android("Failed to retrieve summary.")
            return jsonify({'status': 'summary sent'})
        
        # Branch A: Data Entry
        else:
            urgency = parse_urgency_from_body(body)
            if urgency is not None:
                # Log entry to Google Sheets
                now = datetime.now()
                row_data = [
                    now.date().isoformat(),
                    now.time().strftime('%H:%M:%S'),
                    body,
                    urgency
                ]
                success = append_to_google_sheets(row_data)
                
                if success:
                    send_sms_via_android(f"Logged for {sender}. ✅")
                    return jsonify({'status': 'logged', 'urgency': urgency})
                else:
                    send_sms_via_android(f"Failed to log entry for {sender}. ❌")
                    return jsonify({'error': 'Failed to log entry'}), 500
            else:
                send_sms_via_android("Please include a urgency rating (1-10) in your message.")
                return jsonify({'status': 'no urgency found'})
                
    except Exception as e:
        logger.error(f"Error in android_webhook: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/', methods=['GET'])
def index():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Personal Health SMS Bot is running'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
