# UC Texting App - Personal Health SMS Bot

## Project Overview

UC Texting App is a lightweight Flask web application that enables SMS-based health symptom tracking through a bidirectional messaging system. Users receive daily check-in prompts via SMS, reply with symptoms and an urgency rating (1-10), and the data is automatically logged to a Google Sheets spreadsheet. Users can also query their health log via SMS keywords to retrieve summaries or spreadsheet links.

This project is designed for privacy-conscious individuals who want to track health symptoms without installing mobile apps, utilizing existing SMS infrastructure and cloud spreadsheets for data storage.

## Features

- **Automated Daily Check-ins**: Receive SMS prompts at scheduled times asking about symptom severity
- **SMS-Based Data Entry**: Log symptoms by texting an urgency rating (1-10) and description
- **Automatic Urgency Parsing**: Extracts numerical urgency ratings from message text using regex pattern matching
- **Google Sheets Integration**: All health entries are persisted to a Google Sheet with timestamps
- **Query Commands via SMS**:
  - Text "link" to receive the Google Sheets URL for direct access
  - Text "summary" to receive the last 3 health log entries
- **Cron Job Integration**: Endpoint for external schedulers to trigger daily check-ins
- **Android SMS Forwarding**: Uses Tasker and Join API for SMS sending/receiving on Android devices

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │      External Cron Service          │
                    │  (cron.org, GitHub Actions, etc.)   │
                    └────────────────┬────────────────────┘
                                     │ GET /trigger-daily-checkin
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Flask Application (app.py)                           │
│                                                                               │
│  ┌─────────────────────────┐    ┌─────────────────────────────────────────┐  │
│  │   /trigger-daily-checkin │    │           /android-webhook              │  │
│  │       (GET)              │    │              (POST)                     │  │
│  │                         │    │                                         │  │
│  │  • Verify CRON_SECRET   │    │  Branch A: Data Entry                   │  │
│  │  • Send check-in SMS    │    │  • Parse urgency (1-10)                 │  │
│  └─────────────────────────┘    │  • Log to Google Sheets                 │  │
│                                 │  • Send confirmation SMS                 │  │
│                                 │                                         │  │
│                                 │  Branch B: Retrieval Requests            │  │
│                                 │  • "link" → Return sheet URL             │  │
│                                 │  • "summary" → Return last 3 entries     │  │
│                                 └────────────────┬────────────────────────┘  │
└────────────────────────────────────────────────────┬──────────────────────────┘
                                                     │
                         ┌────────────────────────────┼────────────────────────────┐
                         │                            │                            │
                         ▼                            ▼                            ▼
            ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
            │   Join API (Android)   │   │    Google Sheets API   │   │   Tasker/Join (SMS)    │
            │                        │   │                        │   │                        │
            │  • Send outbound SMS   │   │  • Store health logs   │   │  • Receive incoming    │
            │  • Receive webhook     │   │  • Query last entries  │   │    SMS from phone      │
            │    from Android        │   │  • Generate sheet URL  │   │  • Forward to app.py   │
            └────────────────────────┘   └────────────────────────┘   └────────────────────────┘
```

## Prerequisites

### Required Accounts & Services

1. **Google Cloud Console Account**
   - Create a project and enable the Google Sheets API
   - Create a service account with access to Google Sheets
   - Download the service account JSON credentials

2. **Tasker and Join (Android Apps)**
   - Install [Tasker](https://play.google.com/store/apps/details?id=net.dinglisch.android.taskerm) on Android
   - Install [Join](https://play.google.com/store/apps/details/details?id=com.joaomgcd.join) on Android and connected devices
   - Obtain your Join API URL from Join settings

3. **Cron Scheduling Service** (Optional, for daily check-ins)
   - Options: cron.org, GitHub Actions, EasyCron, or system cron

### Required Python Packages

```
flask>=2.0.0
gspread>=5.0.0
oauth2client>=4.1.3
requests>=2.25.0
gunicorn>=20.0.0
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Setup Instructions

### 1. Clone and Navigate to the Project

```bash
cd <project_directory>
```

### 2. Configure Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Google Sheets Service Account Credentials (JSON string)
# Copy the entire JSON content from your service account key file
GOOGLE_CREDENTIALS='{"type": "service_account", "project_id": "...", ...}'

# Join API endpoint for sending SMS via Android
# Format: https://joinjoaomgcd.appspot.com/_ah/api/messaging/v1/sendPush?text={message}&apikey=YOUR_API_KEY
ANDROID_SEND_URL='https://joinjoaomgcd.appspot.com/_ah/api/messaging/v1/sendPush?text={message}&apikey=YOUR_API_KEY'

# Secret token for cron job authentication
# Generate a secure random string (e.g., openssl rand -hex 32)
CRON_SECRET='your_secure_random_secret_string'
```

#### Obtaining Google Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Google Sheets API: APIs & Services → Library → Search "Google Sheets API" → Enable
4. Create a service account: IAM & Admin → Service Accounts → Create Service Account
5. Grant the service account access to your Google Sheet (share the sheet with the service account email)
6. Create and download key: Service Account → Keys → Add Key → Create new key → JSON
7. Copy the JSON content into the `GOOGLE_CREDENTIALS` environment variable

#### Obtaining Join API URL

1. Install Join on your Android device
2. Open Join → Settings → API
3. Copy the "Push URL" or API endpoint
4. Replace `{message}` placeholder with the actual message parameter name if different

### 3. Configure Google Sheets

1. Create a new Google Spreadsheet named "HealthLog"
2. Add a header row with columns: Date, Time, Body, Urgency
3. Share the spreadsheet with your service account email (from Google Cloud Console)

### 4. Configure Android (Tasker + Join)

#### Tasker Configuration

Create a Tasker profile to forward incoming SMS to your Flask app:

1. **Create Profile**: Event → Phone → Received Text
2. **Task Action**: HTTP Post
   - URL: `https://YOUR_APP_URL/android-webhook`
   - Content-Type: Application/JSON
   - Body: `{"sender": "%SMSRN", "body": "%SMSRB"}`

#### Join Configuration

1. Install Join on your Android device
2. Sign in with the same Google account on all devices
3. Note your Join API key from Settings → API

### 5. Deploy the Application

#### Local Development

```bash
python app.py
```

The application will start on `http://0.0.0.0:5000`

#### Production Deployment (Recommended)

Using Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 app:app --workers 2
```

For persistent background execution, use systemd, supervisor, or a platform like:
- Heroku
- Railway
- Render
- DigitalOcean App Platform

#### Example systemd Service (Linux)

Create `/etc/systemd/system/health-bot.service`:

```ini
[Unit]
Description=Personal Health SMS Bot
After=network.target

[Service]
User=your_username
WorkingDirectory=/path/to/uc-texting-app-kilo
Environment="GOOGLE_CREDENTIALS=..."
Environment="ANDROID_SEND_URL=..."
Environment="CRON_SECRET=..."
ExecStart=/usr/bin/gunicorn --bind 0.0.0.0:5000 app:app --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable health-bot
sudo systemctl start health-bot
```

## Usage Guide

### Sending Health Log Entries

Send an SMS from your phone with the following format:

```
Urgency rating (1-10) and your symptom description
```

**Examples:**
- `5 Mild headache today, feeling better than yesterday`
- `8 Severe back pain, unable to move comfortably`
- `3 Slight congestion, no fever`

The system will:
1. Extract the urgency number (1-10)
2. Log the entry to Google Sheets with timestamp
3. Send a confirmation SMS with checkmark

### Querying Your Health Log

#### Get Spreadsheet Link

Text: `link`

Response: SMS containing the Google Sheets URL for direct access to your HealthLog.

#### Get Recent Summary

Text: `summary`

Response: SMS with the last 3 health log entries in format:
```
Last 3 entries:
1. 2024-01-15 14:30:00 - Urgency: 5
2. 2024-01-14 09:15:00 - Urgency: 3
3. 2024-01-13 18:45:00 - Urgency: 8
```

### Automated Daily Check-ins

Set up a cron job to call the trigger endpoint:

#### Cron.org Example

1. Create account at [cron.org](https://cron.org/)
2. Add new job with URL: `https://YOUR_APP_URL/trigger-daily-checkin?secret=YOUR_CRON_SECRET`
3. Set schedule (e.g., 8:00 PM daily)

#### GitHub Actions Example

Create `.github/workflows/daily-checkin.yml`:

```yaml
name: Daily Health Check-in

on:
  schedule:
    - cron: '0 20 * * *'  # 8:00 PM daily
  workflow_dispatch:

jobs:
  trigger-checkin:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger health check-in
        run: |
          curl "https://YOUR_APP_URL/trigger-daily-checkin?secret=${{ secrets.CRON_SECRET }}"
```

#### System Cron Example

Add to crontab (`crontab -e`):

```bash
# Daily at 8:00 PM
0 20 * * * curl "https://YOUR_APP_URL/trigger-daily-checkin?secret=YOUR_CRON_SECRET"
```

## API Reference

### Endpoints

#### GET /

Health check endpoint.

**Response (200 OK):**
```json
{
  "status": "ok",
  "message": "Personal Health SMS Bot is running"
}
```

#### GET /trigger-daily-checkin

Trigger a daily check-in SMS. Requires `secret` query parameter.

**Parameters:**
- `secret` (required): CRON_SECRET environment variable value

**Response:**
- 200: "Triggered" (SMS sent successfully)
- 401: `{"error": "Unauthorized"}` (invalid secret)
- 500: `{"error": "Failed to send SMS"}` (SMS sending failed)

**Example:**
```bash
curl "https://YOUR_APP_URL/trigger-daily-checkin?secret=YOUR_CRON_SECRET"
```

#### POST /android-webhook

Receive incoming SMS from Android via Tasker/Join.

**Headers:**
- Content-Type: application/json

**Request Body:**
```json
{
  "sender": "+1234567890",
  "body": "8 Severe headache today"
}
```

**Response:**
- 200: Operation-specific status
  - `{"status": "logged", "urgency": 8}` - Entry logged successfully
  - `{"status": "link sent"}` - Sheet link sent
  - `{"status": "summary sent"}` - Summary sent
  - `{"status": "no urgency found"}` - No urgency rating in message
- 400: `{"error": "Invalid payload"}` - Missing required fields
- 500: `{"error": "Failed to log entry"}` or `{"error": "Internal server error"}`

### SMS Commands

| Command | Description | Example Response |
|---------|-------------|------------------|
| (number 1-10) + text | Log health entry | "Logged for +1234567890. ✅" |
| link | Get Google Sheets URL | "Health Log Link: https://docs.google.com/..." |
| summary | Get last 3 entries | "Last 3 entries:\n1. 2024-01-15 - Urgency: 5\n..." |

## Troubleshooting

### Common Issues

#### SMS Not Being Sent
1. Verify ANDROID_SEND_URL is correct and includes your Join API key
2. Check that Join is running on your Android device
3. Review application logs for error messages

#### Google Sheets Authentication Failed
1. Ensure GOOGLE_CREDENTIALS contains valid JSON (no line breaks in .env)
2. Verify the service account has access to the HealthLog spreadsheet
3. Check that Google Sheets API is enabled in Google Cloud Console

#### Incoming SMS Not Reaching the App
1. Verify Tasker HTTP Post configuration (correct URL, JSON format)
2. Check that your Flask app is accessible from the internet (not localhost)
3. Ensure firewall allows incoming connections to port 5000

#### Cron Job Not Working
1. Verify CRON_SECRET matches exactly in both cron URL and .env
2. Ensure the cron service can reach your deployed application URL
3. Check cron service logs for connection errors

### Logging

The application logs to stdout with INFO level. Configure logging in production:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('health-bot.log'),
        logging.StreamHandler()
    ]
)
```

## Security Considerations

1. **Environment Variables**: Never commit `.env` files or credentials to version control
2. **CRON_SECRET**: Use a strong, random secret (32+ characters)
3. **HTTPS**: Deploy with HTTPS in production (use a reverse proxy like nginx with SSL)
4. **Input Validation**: The app validates all incoming JSON payloads
5. **Rate Limiting**: Consider implementing rate limiting for webhook endpoints

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/improvement-name`
3. Commit changes: `git commit -m 'Add descriptive commit message'`
4. Push to branch: `git push origin feature/improvement-name`
5. Submit a Pull Request

## License

This project is provided as-is for personal health tracking purposes.

## Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Lightweight web framework
- [gspread](https://gspread.readthedocs.io/) - Google Sheets API Python client
- [Tasker](https://tasker.joaoapps.com/) - Android automation
- [Join](https://joaoapps.com/join/) - Cross-device notifications and SMS
