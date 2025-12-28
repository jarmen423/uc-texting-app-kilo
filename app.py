# Tasker/Join Configuration for Android:
# For incoming SMS forwarding: POST to YOUR_APP_URL/android-webhook
# JSON payload MUST be: {"sender": "+1234567890", "body": "SMS text here"}
# Configure Tasker to send exactly this format.

"""
Personal Health SMS Bot - Main Flask Application Module

This module implements the core logic for a bidirectional SMS health logging bot.

Purpose & Reasoning: Enables users to log daily health symptoms via SMS from their Android phone, automatically parsing urgency ratings and storing in Google Sheets. Created to provide a zero-cost, app-free health tracker using existing phone SMS and cloud sheets, with automated daily prompts and query capabilities.

Dependencies:
- External services: Google Sheets API (gspread client), Tasker/Join Android integration for SMS
- Python packages: Flask (web framework), gspread (Google Sheets API wrapper), oauth2client (Google auth), requests (HTTP client)
- Environment variables: GOOGLE_CREDENTIALS (JSON service account), ANDROID_SEND_URL (Join API endpoint), CRON_SECRET (auth token for scheduled triggers)

Role in Codebase: This is the primary entry point and only application module. The Flask app handles all HTTP webhooks from Android (incoming SMS) and external cron triggers (daily check-ins). It orchestrates SMS sending via Join API and data persistence to Google Sheets.
"""

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
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS')  # <--- REPLACE WITH YOUR ENV VAR FROM .ENV
ANDROID_SEND_URL = os.environ.get('ANDROID_SEND_URL')  # <--- REPLACE WITH YOUR ENV VAR FROM .ENV
CRON_SECRET = os.environ.get('CRON_SECRET')  # <--- REPLACE WITH YOUR ENV VAR FROM .ENV


def send_sms_via_android(message_text):
    """
    Send an SMS message via Android phone using Tasker/Join API.

    This function makes a GET request to the Join API endpoint with the message text
    as a query parameter. The Android device (with Tasker and Join installed) receives
    the request and sends the SMS to the configured recipient. This is the primary
    outbound communication channel for the health bot.

    Args:
        message_text (str): The text content of the SMS message to send.

    Returns:
        bool: True if the SMS was sent successfully, False otherwise.

    Raises:
        Requests exceptions (requests.RequestException): Network or HTTP errors are caught
        and logged, but not raised (returns False instead).

    Key Technologies/APIs:
        - requests.get(): Makes HTTP GET to ANDROID_SEND_URL
        - Join API (Joaoapps.com): Android notification/SMS forwarding service
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
    Authenticate with Google Sheets API using service account credentials.

    This function parses the GOOGLE_CREDENTIALS environment variable (JSON format),
    creates service account credentials, and returns an authorized gspread client.
    The client is used for all subsequent Google Sheets operations (reading, appending).
    Authentication is performed once per request to ensure credentials are fresh.

    Args:
        None

    Returns:
        gspread.client.Client: An authorized gspread client instance if authentication
        succeeds, or None if authentication fails.

    Raises:
        json.JSONDecodeError: Invalid JSON in GOOGLE_CREDENTIALS triggers exception
        gspread.exceptions: Various Google API errors are caught and logged.

    Key Technologies/APIs:
        - gspread: Python library for Google Sheets API access
        - oauth2client.ServiceAccountCredentials: Google service account authentication
        - json.loads(): Parses environment variable JSON string
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
    Append a new row of health log data to the HealthLog Google Sheet.

    This function is the primary data persistence mechanism for the health bot.
    It authenticates with Google Sheets, opens the "HealthLog" spreadsheet's first
    worksheet, and appends the provided data as a new row. The data includes
    timestamp, message body, and parsed urgency rating.

    Args:
        data (list): List of values to append in order [date, time, body, urgency].
            - date (str): ISO format date string (YYYY-MM-DD)
            - time (str): Time string (HH:MM:SS)
            - body (str): Original SMS message body
            - urgency (int): Parsed urgency rating (1-10)

    Returns:
        bool: True if the row was appended successfully, False otherwise.

    Raises:
        gspread.exceptions: Spreadsheet not found, permission errors, or API failures
        are caught and logged, but not raised (returns False instead).

    Key Technologies/APIs:
        - gspread.Client.open(): Opens Google Spreadsheet by name
        - Worksheet.append_row(): Appends row to Google Sheet
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
    Retrieve the most recent N rows from a Google Sheet worksheet.

    This utility function fetches the last N data rows from a worksheet, excluding
    the header row. It is used to generate summaries for user queries. The function
    handles edge cases like empty sheets or sheets with only headers.

    Args:
        sheet (gspread.Worksheet): The worksheet object to query.
        num_rows (int, optional): Number of last rows to retrieve. Defaults to 3.

    Returns:
        list: List of rows (each row is a list of cell values), or empty list if
        the sheet has only header or is empty.

    Raises:
        gspread.exceptions: API errors are caught and logged, returning empty list.

    Key Technologies/APIs:
        - Worksheet.get_all_values(): Retrieves all values from worksheet
        - List slicing: Extracts last N rows from data list
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
    Parse urgency rating (1-10) from SMS message body using regex pattern matching.

    This function extracts the first numeric value between 1 and 10 from the message
    body. Users are instructed to include a number 1-10 indicating symptom urgency.
    This parsed value is used for health tracking and prioritization.

    Args:
        body (str): The SMS message body to parse for urgency rating.

    Returns:
        int: The first number found between 1-10, converted to integer.
        None: If no valid urgency rating (1-10) is found in the message.

    Raises:
        None: All exceptions are handled internally; returns None on pattern match failure.

    Key Technologies/APIs:
        - re.findall(): Regular expression search for numeric patterns
        - Regular expression pattern: \b([1-9]|10)\b matches numbers 1-10 as whole words
    """
    import re
    matches = re.findall(r'\b([1-9]|10)\b', body)
    if matches:
        return int(matches[0])
    return None


@app.route('/trigger-daily-checkin', methods=['GET'])
def trigger_daily_checkin():
    """
    Flask route handler for initiating daily health check-in SMS.

    This endpoint is called by external cron jobs (e.g., cron.org, GitHub Actions)
    to trigger automated daily check-in messages. It is protected by CRON_SECRET
    authentication to prevent unauthorized triggering. Upon successful authentication,
    it sends a prompt asking the user to rate their symptoms and describe them.

    Args:
        None (uses request.args for authentication token)

    Returns:
        str: "Triggered" if SMS was sent successfully (HTTP 200)
        Response: JSON error response with HTTP 401 (unauthorized) or 500 (failure)

    Raises:
        None: All exceptions are caught and handled, returning JSON error responses.

    Key Technologies/APIs:
        - Flask @app.route(): HTTP endpoint decoration
        - Flask request.args: Query parameter extraction
        - CRON_SECRET: Environment variable for endpoint authentication
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
    Flask route handler for receiving incoming SMS from Android via Tasker/Join.

    This is the primary webhook endpoint that receives JSON payloads from the
    Android device when SMS messages are received. It implements a bidirectional
    communication system with two main branches:

    Branch A (Data Entry): Logs health symptoms to Google Sheets when the user
    sends a message containing an urgency rating (1-10). Extracts the rating,
    timestamps the entry, and stores in HealthLog spreadsheet.

    Branch B (Retrieval Requests): Responds to special keywords:
    - "link": Returns a shareable Google Sheets URL
    - "summary": Returns the last 3 health log entries

    Args:
        None (expects JSON body with 'sender' and 'body' fields)

    Returns:
        Response: JSON response with status field indicating result
        - {'status': 'logged', 'urgency': N} on successful data entry (HTTP 200)
        - {'status': 'link sent'} or {'status': 'summary sent'} on retrieval (HTTP 200)
        - {'error': 'Invalid payload'} for malformed requests (HTTP 400)
        - {'error': 'Unauthorized'} for auth failures (HTTP 401 - not currently used)
        - {'error': 'Failed to log entry'} or {'error': 'Internal server error'} (HTTP 500)

    Raises:
        None: All exceptions are caught and handled with appropriate error responses.

    Key Technologies/APIs:
        - Flask request.json: Parses incoming JSON payload
        - gspread operations: Spreadsheet access and row appending
        - send_sms_via_android(): Outbound SMS for confirmations and query responses
        - parse_urgency_from_body(): Regex-based urgency extraction
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
    """
    Flask route handler for application health check endpoint.

    This simple endpoint confirms the application is running and accessible.
    It returns a JSON status message indicating the service is operational.

    Args:
        None

    Returns:
        Response: JSON response with status 'ok' and service message (HTTP 200)

    Raises:
        None: This function has no failure conditions.

    Key Technologies/APIs:
        - Flask @app.route(): Root endpoint decoration
        - Flask jsonify(): Creates JSON response object
    """
    return jsonify({'status': 'ok', 'message': 'Personal Health SMS Bot is running'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
