Baby Tracker Telegram Bot
A Telegram bot designed to help parents easily log their baby's daily activities (feeding, diaper changes, medication) and view summaries, all integrated with Google Sheets for data storage.

✨ Features
Activity Logging: Quickly log Poop, Pee, Feed, and Medication entries.

Dedicated Vitamin D Tracking: A specific command and button to log "Vitamin D" medication.

Customizable Medication: Log any other medication by name.

Google Sheets Integration: All data is securely stored and accessible in a Google Sheet.

Timezone Aware: Logs timestamps in Indian Standard Time (IST).

Multi-User Support: Designed to work in private chats and group chats (with privacy mode disabled).

Comprehensive Summaries: Get daily, yesterday's, 7-day, 30-day, and 90-day summaries of activities, with special handling for Vitamin D.

Interactive Keyboard: User-friendly reply keyboard for quick actions.

Cold Start Mechanism: A /coldstart command to wake up the bot on free-tier hosting services like Render.com.

🚀 Getting Started
Follow these steps to set up and deploy your Baby Tracker Bot.

Prerequisites
Python 3.9+

Telegram Account: To create a bot via BotFather.

Google Account: To use Google Sheets and Google Cloud Platform.

1. Set up your Telegram Bot (BotFather)
Open Telegram and search for @BotFather.

Send /newbot to BotFather and follow the instructions to create a new bot.

BotFather will give you a Bot Token. Keep this token secure; it's essential for your bot to function.

Disable Privacy Mode (Crucial for Group Chats):

Send /setprivacy to BotFather.

Select your bot.

Choose "Disable". This allows your bot to receive all messages in group chats, not just direct mentions or replies.

2. Set up Google Sheets API
Your bot uses Google Sheets to store all the baby's activity data.

Create a new Google Spreadsheet: Go to Google Sheets and create a new blank spreadsheet. Name it something descriptive, e.g., "Baby Tracker Log".

Note the Spreadsheet ID: The Spreadsheet ID is a long string of characters in the URL of your spreadsheet. For example, in https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit, YOUR_SPREADSHEET_ID is what you need.

Enable Google Sheets API:

Go to the Google Cloud Console.

Create a new project or select an existing one.

Navigate to "APIs & Services" > "Enabled APIs & Services".

Search for "Google Sheets API" and enable it.

Create a Service Account:

In the Google Cloud Console, go to "APIs & Services" > "Credentials".

Click "Create Credentials" > "Service Account".

Give it a name (e.g., baby-tracker-service-account) and a description.

Grant it the role of "Project" > "Editor" (or a more specific role like "Sheets Editor" if available and preferred for security).

Click "Done".

Generate and Download Service Account Key:

After creating the service account, click on its email address in the "Credentials" list.

Go to the "Keys" tab.

Click "Add Key" > "Create new key" > "JSON".

A JSON file will be downloaded to your computer. Rename this file to credentials.json (or any name, but remember it) and keep it secure. This file contains your service account's private key.

Share your Google Sheet with the Service Account:

Open your "Baby Tracker Log" Google Sheet.

Click the "Share" button.

In the "Share with people and groups" dialog, enter the client_email found in your downloaded credentials.json file (it looks like an email address).

Grant it "Editor" access.

Click "Share".

3. Environment Variables
Your bot requires several environment variables to run.

TELEGRAM_TOKEN: Your bot token obtained from BotFather.

SPREADSHEET_ID: The ID of your Google Spreadsheet.

GOOGLE_CREDENTIALS_JSON_BASE64: The content of your credentials.json file, base64 encoded. You can generate this using a tool or a Python script:

import base64
import json

with open('credentials.json', 'r') as f:
    credentials_content = f.read()

encoded_credentials = base64.b64encode(credentials_content.encode('utf-8')).decode('utf-8')
print(encoded_credentials)

Copy the output string and set it as the value for this environment variable.

RENDER_EXTERNAL_URL: (Only for Render.com deployment) This is automatically provided by Render.com. You don't need to set it manually in your render.yaml, but ensure it's available in the Render environment.

⚙️ Local Development (Optional)
If you want to run the bot locally for testing:

Clone the repository:

git clone <your-repo-url>
cd baby-tracker-bot

Create a virtual environment:

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

Create a .env file: In the root directory of your project, create a file named .env and add your environment variables:

TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
SPREADSHEET_ID=YOUR_GOOGLE_SPREADSHEET_ID
GOOGLE_CREDENTIALS_JSON_BASE64=YOUR_BASE64_ENCODED_CREDENTIALS
# RENDER_EXTERNAL_URL is not needed for local testing but keep it if you plan to deploy

Run the bot:

python bot.py

Note: For local development, you might need to use a tunneling service (like ngrok) to expose your local server to the internet if you want to test webhooks. For simple command testing, running bot.py directly will use long polling.

🚀 Deployment (Render.com)
This bot is configured for deployment on Render.com.

Fork/Clone this repository: Push your code to your GitHub repository.

Create a new Web Service on Render:

Go to your Render Dashboard.

Click "New" > "Web Service".

Connect your GitHub repository.

Select the branch you want to deploy (e.g., main).

Configure the Web Service:

Name: baby-tracker-bot (or your preferred name)

Root Directory: / (if your bot.py and render.yaml are in the root)

Runtime: Python 3

Build Command: pip install -r requirements.txt

Start Command: gunicorn bot:app (This uses Gunicorn to run the Flask app wrapped by WsgiToAsgi)

Health Check Path: /webhook

Environment Variables: Add the TELEGRAM_TOKEN, SPREADSHEET_ID, and GOOGLE_CREDENTIALS_JSON_BASE64 as secret environment variables. Render automatically provides RENDER_EXTERNAL_URL.

Plan: Choose a suitable plan (e.g., Free plan for testing).

Deploy: Click "Create Web Service". Render will automatically build and deploy your bot.

Set Webhook URL: Once your service is deployed and running, Render will provide you with an "External URL" (e.g., https://your-service-name.onrender.com). You need to set your Telegram bot's webhook to this URL.

The bot automatically attempts to set the webhook during setup_bot_application. Ensure RENDER_EXTERNAL_URL is correctly set in Render's environment variables.

If the webhook isn't set, you can manually set it via a browser: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-service-name.onrender.com/webhook

🤖 Bot Usage
Interact with the bot using commands or the provided keyboard.

Commands
/start: Displays the welcome message and the main keyboard.

/feed (minutes): Logs a feeding session. Example: /feed 15

/poop: Logs a poop activity.

/pee: Logs a pee activity.

/medication [name]: Logs a medication. Example: /medication Tylenol. If no name is provided, it logs "Medication".

/vitamind: Logs a "Vitamin D" medication entry directly.

/summary [today|yesterday|7days|1month|3month]: Provides a summary of activities for the specified period.

/summary today: Summary for the current day.

/summary yesterday: Summary for the previous day.

/summary 7days: Summary for the last 7 days.

/summary 1month: Summary for the last 30 days.

/summary 3month: Summary for the last 90 days.

/summary (without arguments): Shows all summary periods.

/coldstart: Sends a message to wake up the bot if it has been idle (useful for free-tier hosting).

/help or /menu: Displays the welcome message and the main keyboard again.

Keyboard Buttons
The bot provides a persistent reply keyboard for quick access to common actions:

Poop

Pee

Feed (prompts for duration)

Medication (prompts for medication name)

Vitamin D (logs Vitamin D directly)

Summary (Today)

Summary (7 Days)

Summary (30 Days)

Summary (90 Days)

Cold Start

Help

Summary Details
The /summary command provides a breakdown of activities.

Daily/Yesterday Summaries:

Pee: Count

Poop: Count

Feeds: Count (Total minutes)

Vitamin D: Count with a ✅ emoji

Medications: Count (for non-Vitamin D medications)

7-Day/30-Day/90-Day Summaries:

Pee: Count

Poop: Count

Feeds: Count (Total minutes)

Vitamin D: Count [Given] / X Days (where X is the period duration)

Medications: Count (for non-Vitamin D medications)

⚠️ Troubleshooting
Keyboard not appearing: Try sending /start or /menu to the bot. If it still doesn't appear, try clearing the cache of your Telegram app or restarting it.

Bot not responding in groups: Ensure you have disabled privacy mode for your bot via BotFather (/setprivacy -> select your bot -> Disable).

BadRequest: Can't parse entities error: This usually means there's an issue with HTML formatting in the bot's messages. Ensure all special characters are properly escaped or use plain text where HTML is not strictly necessary. The current version of bot.py should have this fixed.

Bot is slow or unresponsive: On free hosting tiers, bots might go to sleep after a period of inactivity. Use the /coldstart command to wake it up.

🤝 Contributing
Feel free to fork this repository, open issues, and submit pull requests if you have suggestions or improvements!

📄 License
This project is open-source and available under the MIT License.
