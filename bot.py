import os
import logging
import json
import base64
from datetime import datetime, timedelta
import asyncio
import requests # For the coldstart ping
from flask import Flask, request # For webhook and coldstart endpoint
from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Google Sheets imports
import gspread
from google.oauth2.service_account import Credentials

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App for Webhook and Cold Start ---
app = Flask(__name__)

# Global variable to hold the bot instance
# This is a common pattern when integrating PTB with Flask
telegram_app_instance = None

# --- Ping Service for Cold Start ---
class PingService:
    def __init__(self, url):
        self.url = url
        self.is_active = False
        self.last_ping = None

    def activate(self):
        """Activate the service with a single ping."""
        try:
            response = requests.get(self.url)
            self.last_ping = datetime.now()
            self.is_active = True
            logger.info(f"Ping successful: {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    def get_status(self):
        """Get current status of the service."""
        return {
            'active': self.is_active,
            'last_ping': self.last_ping.strftime('%Y-%m-%d %H:%M:%S') if self.last_ping else None
        }

# --- Baby Tracker Bot Class ---
class BabyTrackerBot:
    def __init__(self, token: str, spreadsheet_id: str, credentials_json_b64: str):
        """
        Initializes the bot with Telegram token, Google Sheet ID,
        and base64 encoded Google Service Account credentials.
        """
        self.token = token
        self.spreadsheet_id = spreadsheet_id
        self.credentials_json_b64 = credentials_json_b64
        self.gc = self._authenticate_google_sheets()
        self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
        self.worksheet = self._get_or_create_worksheet("BabyLog") # Default sheet for logging

        # Initialize ping service for cold start
        # The URL will be set dynamically or via an env var in main()
        self.ping_service = PingService("") # Placeholder, will be updated in main

    def _authenticate_google_sheets(self):
        """Authenticates with Google Sheets using service account credentials."""
        try:
            # Decode base64 credentials and load as JSON
            credentials_info = json.loads(base64.b64decode(self.credentials_json_b64).decode('utf-8'))
            
            # Define the scope for Google Sheets API
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            
            # Create credentials object
            creds = Credentials.from_service_account_info(credentials_info, scopes=scope)
            
            # Authorize gspread client
            gc = gspread.authorize(creds)
            logger.info("Google Sheets authentication successful.")
            return gc
        except Exception as e:
            logger.error(f"Error authenticating with Google Sheets: {e}")
            raise

    def _get_or_create_worksheet(self, sheet_name: str):
        """
        Gets an existing worksheet or creates a new one if it doesn't exist.
        Adds headers if the sheet is newly created or empty.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.info(f"Worksheet '{sheet_name}' found.")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Worksheet '{sheet_name}' not found, creating new one.")
            worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="10")
            # Add headers
            headers = ['Timestamp', 'Activity Type', 'Value/Details', 'Telegram User ID']
            worksheet.append_row(headers)
            logger.info(f"Worksheet '{sheet_name}' created with headers.")
        
        # Ensure headers are present if sheet was empty
        if not worksheet.row_values(1):
            headers = ['Timestamp', 'Activity Type', 'Value/Details', 'Telegram User ID']
            worksheet.append_row(headers)
            logger.info(f"Headers added to existing empty worksheet '{sheet_name}'.")
            
        return worksheet

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends a welcome message and lists commands."""
        user = update.effective_user
        welcome_message = (
            f"Hi {user.mention_html()}! I'm your Baby Tracker Bot.\n\n"
            "Here's what I can do:\n"
            "• `/feed <minutes>`: Log a feeding session (e.g., `/feed 15`)\n"
            "• `/poop`: Log a pooping event\n"
            "• `/pee`: Log a peeing event\n"
            "• `/medication [name]`: Log medication (e.g., `/medication Tylenol`)\n"
            "• `/summary [days]`: Get a summary for the last N days (e.g., `/summary 7`)\n"
            "• `/coldstart`: Wake up the bot if it's inactive (for Render.com free tier)\n"
            "• `/help`: Show this message again"
        )
        await update.message.reply_html(welcome_message)
        logger.info(f"User {user.id} started the bot.")

    async def _log_activity(self, update: Update, activity_type: str, value: str = "N/A") -> None:
        """Helper function to log activities to Google Sheet."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_id = update.effective_user.username or str(update.effective_user.id)
        row = [timestamp, activity_type, value, user_id]
        
        try:
            self.worksheet.append_row(row)
            logger.info(f"Logged activity: {activity_type}, Value: {value}, User: {user_id}")
            await update.message.reply_text(f"✅ Logged {activity_type} at {timestamp.split(' ')[1]} on {timestamp.split(' ')[0]}.")
        except Exception as e:
            logger.error(f"Error logging activity to Google Sheet: {e}")
            await update.message.reply_text("❌ Failed to log activity. Please try again later.")

    async def feed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Logs a feeding session with duration."""
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("❌ Please specify feed duration in minutes. Example: `/feed 15`")
            return
        
        duration = context.args[0]
        await self._log_activity(update, "Feed", f"{duration} mins")

    async def poop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Logs a pooping event."""
        await self._log_activity(update, "Poop")

    async def pee(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Logs a peeing event."""
        await self._log_activity(update, "Pee")

    async def medication(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Logs medication administration."""
        med_name = " ".join(context.args) if context.args else "Medication"
        await self._log_activity(update, "Medication", med_name)

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Provides a summary of activities for the last N days."""
        try:
            days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
            
            # Fetch all data from the sheet
            all_records = self.worksheet.get_all_records()
            
            summary_data = {}
            today = datetime.now().date()

            for record in all_records:
                try:
                    record_timestamp_str = record['Timestamp']
                    # Handle potential missing seconds or different formats
                    try:
                        record_dt = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        record_dt = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M')

                    record_date = record_dt.date()

                    if today - record_date < timedelta(days=days):
                        date_key = record_date.strftime('%Y-%m-%d')
                        if date_key not in summary_data:
                            summary_data[date_key] = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}

                        activity_type = record['Activity Type']
                        value_details = record['Value/Details']

                        if activity_type == 'Pee':
                            summary_data[date_key]['pee'] += 1
                        elif activity_type == 'Poop':
                            summary_data[date_key]['poop'] += 1
                        elif activity_type == 'Feed':
                            summary_data[date_key]['feed_count'] += 1
                            if 'mins' in value_details:
                                try:
                                    duration = int(value_details.split(' ')[0])
                                    summary_data[date_key]['feed_total_mins'] += duration
                                except ValueError:
                                    pass # Ignore if duration is not a valid number
                        elif activity_type == 'Medication':
                            summary_data[date_key]['medications'] += 1
                except Exception as e:
                    logger.warning(f"Skipping malformed record: {record} - Error: {e}")
                    continue # Skip to the next record if parsing fails

            response_message = f"--- Last {days} Days Summary ---\n\n"
            # Sort by date, newest first
            sorted_dates = sorted(summary_data.keys(), reverse=True)

            if not sorted_dates:
                response_message += "No activities found for the selected period."
            else:
                for date_key in sorted_dates:
                    data = summary_data[date_key]
                    response_message += (
                        f"Day ({date_key}): {data['pee']} pee, {data['poop']} poop, "
                        f"{data['feed_count']} feeds (Total {data['feed_total_mins']} mins), "
                        f"{data['medications']} medications\n"
                    )
            
            await update.message.reply_text(response_message)

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            await update.message.reply_text("❌ Error generating summary. Please try again.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends the help message."""
        await self.start(update, context) # Re-use start command's message

    async def coldstart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /coldstart command to activate the bot."""
        # The PingService URL needs to be set up in the main function with the actual Render URL
        if not self.ping_service.is_active:
            if self.ping_service.activate():
                await update.message.reply_text(
                    "🟢 Bot Successfully Activated!\n\n"
                    "I'm awake and ready to help you track baby activities.\n\n"
                    "You can:\n"
                    "• Log activities like /feed, /poop, /pee, /medication\n"
                    "• Get summaries with /summary\n"
                    "• View all commands with /start"
                )
            else:
                await update.message.reply_text("❌ Failed to activate bot. Please try again.")
        else:
            await update.message.reply_text(
                "ℹ️ I'm already active and ready!\n\n"
                "You can start logging activities."
            )

# --- Main function to set up and run the bot ---
async def run_bot():
    """Sets up the Telegram bot and Flask app for webhooks."""
    global telegram_app_instance # Use the global instance

    bot_token = os.getenv("BOT_TOKEN")
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    google_credentials_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")
    render_external_url = os.getenv("RENDER_EXTERNAL_URL") # Provided by Render

    if not all([bot_token, spreadsheet_id, google_credentials_json_b64, render_external_url]):
        logger.error("Missing one or more required environment variables. Please check BOT_TOKEN, GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON_BASE64, and RENDER_EXTERNAL_URL.")
        exit(1)

    # Initialize the bot
    bot_instance = BabyTrackerBot(bot_token, spreadsheet_id, google_credentials_json_b64)
    
    # Set the PingService URL
    coldstart_url = f"{render_external_url}/coldstart"
    bot_instance.ping_service.url = coldstart_url
    logger.info(f"PingService URL set to: {coldstart_url}")

    # Create the Application and pass your bot's token.
    telegram_app_instance = Application.builder().token(bot_token).build()

    # Register command handlers
    telegram_app_instance.add_handler(CommandHandler("start", bot_instance.start))
    telegram_app_instance.add_handler(CommandHandler("feed", bot_instance.feed))
    telegram_app_instance.add_handler(CommandHandler("poop", bot_instance.poop))
    telegram_app_instance.add_handler(CommandHandler("pee", bot_instance.pee))
    telegram_app_instance.add_handler(CommandHandler("medication", bot_instance.medication))
    telegram_app_instance.add_handler(CommandHandler("summary", bot_instance.summary))
    telegram_app_instance.add_handler(CommandHandler("help", bot_instance.help_command))
    telegram_app_instance.add_handler(CommandHandler("coldstart", bot_instance.coldstart))

    # Set up webhook
    webhook_path = "/webhook"
    listen_address = "0.0.0.0"
    port = int(os.environ.get("PORT", 8000)) # Render provides the PORT env var

    logger.info(f"Setting webhook to {render_external_url}{webhook_path}")
    await telegram_app_instance.bot.set_webhook(url=f"{render_external_url}{webhook_path}")

    # Start the PTB application in webhook mode
    # This will be handled by the Flask app's /webhook endpoint
    # We don't call run_webhook directly here, as Flask will handle the HTTP server.
    logger.info("Telegram bot application prepared for webhook.")


# --- Flask Endpoints ---
@app.route("/webhook", methods=["POST"])
async def webhook_handler():
    """Handle incoming Telegram updates."""
    if telegram_app_instance is None:
        logger.error("Telegram application instance not initialized.")
        return "Bot not ready", 500

    update_json = request.get_json(force=True)
    update = Update.de_json(update_json, telegram_app_instance.bot)
    
    # Process the update asynchronously
    await telegram_app_instance.process_update(update)
    return "ok"

@app.route("/coldstart", methods=["GET"])
def coldstart_endpoint():
    """Simple endpoint to keep Render service awake."""
    logger.info("Coldstart endpoint hit.")
    return "Bot is awake!", 200

# --- Entry point for Render ---
if __name__ == "__main__":
    # Run the bot setup asynchronously
    asyncio.run(run_bot())
    
    # Run the Flask app
    port = int(os.environ.get("PORT", 8000))
    # Use app.run() for local development. For Render, Gunicorn/Werkzeug will serve.
    # For Render, the 'startCommand' in render.yaml will typically be `gunicorn bot:app`
    # where 'bot' is the module name and 'app' is the Flask instance.
    # For simplicity here, we'll just run Flask directly, but be aware of production setups.
    logger.info(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port)

