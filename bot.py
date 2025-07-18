import os
import logging
import json
import base64
from datetime import datetime, timedelta
import asyncio
import requests # For the coldstart ping
from flask import Flask, request # For webhook and coldstart endpoint (only active on Render)

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

# --- Flask App for Webhook and Cold Start (Only active when served by Gunicorn/Werkzeug on Render) ---
# This 'app' instance is intended for Render's webhook setup.
# For local polling, it won't be explicitly run.
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
            # THIS LINE MUST COME FIRST TO DEFINE decoded_string
            decoded_string = base64.b64decode(self.credentials_json_b64).decode('utf-8')
            
            # Debug prints (now correctly placed after decoded_string is defined)
            print(f"--- DEBUG: Decoded string length: {len(decoded_string)}")
            print(f"--- DEBUG: Decoded string (first 200 chars): {decoded_string[:200]}")
            # print("--- DEBUG: Full Decoded String (for inspection):") # Uncomment if you need to see the whole thing
            # print(decoded_string) # Uncomment if you need to see the whole thing

            credentials_info = json.loads(decoded_string) # This line uses decoded_string
            
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
            "• `/feed &lt;minutes&gt;`: Log a feeding session (e.g., `/feed 15`)\n"
            "• `/poop`: Log a pooping event\n"
            "• `/pee`: Log a peeing event\n"
            "• `/medication [name]`: Log medication (e.g., `/medication Tylenol`)\n"
            "• `/summary [today|yesterday|7days|1month]`: Get a summary for specific periods (e.g., `/summary 7days` or just `/summary` for all)\n"
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
        """Provides a summary of activities for various periods."""
        try:
            all_records = self.worksheet.get_all_records()
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            # Initialize summary data structures
            summary_today = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_yesterday = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_last_7_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_last_30_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}

            for record in all_records:
                try:
                    record_timestamp_str = record['Timestamp']
                    try:
                        record_dt = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        record_dt = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M')
                    record_date = record_dt.date()

                    activity_type = record['Activity Type']
                    value_details = record['Value/Details']
                    
                    # Helper to update a summary dictionary
                    def update_summary_dict(summary_dict, activity, value):
                        if activity == 'Pee':
                            summary_dict['pee'] += 1
                        elif activity == 'Poop':
                            summary_dict['poop'] += 1
                        elif activity == 'Feed':
                            summary_dict['feed_count'] += 1
                            if 'mins' in value:
                                try:
                                    duration = int(value.split(' ')[0])
                                    summary_dict['feed_total_mins'] += duration
                                except ValueError:
                                    pass
                        elif activity == 'Medication':
                            summary_dict['medications'] += 1

                    # Categorize records into respective summaries
                    if record_date == today:
                        update_summary_dict(summary_today, activity_type, value_details)
                    
                    if record_date == yesterday:
                        update_summary_dict(summary_yesterday, activity_type, value_details)

                    if today - record_date < timedelta(days=7): # Last 7 days including today
                        update_summary_dict(summary_last_7_days, activity_type, value_details)

                    if today - record_date < timedelta(days=30): # Last 30 days including today
                        update_summary_dict(summary_last_30_days, activity_type, value_details)

                except Exception as e:
                    logger.warning(f"Skipping malformed record: {record} - Error: {e}")
                    continue

            response_message = "--- Baby Activity Summary ---\n\n"
            
            # Helper to format summary output
            def format_summary(title, data, date_info=""):
                return (
                    f"**{title}** {date_info}:\n"
                    f"  Pee: {data['pee']}\n"
                    f"  Poop: {data['poop']}\n"
                    f"  Feeds: {data['feed_count']} (Total {data['feed_total_mins']} mins)\n"
                    f"  Medications: {data['medications']}\n\n"
                )

            # Determine which summaries to show
            arg = context.args[0].lower() if context.args else None

            if arg == 'today':
                response_message += format_summary("Current Day", summary_today, f"({today.strftime('%Y-%m-%d')})")
            elif arg == 'yesterday':
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday.strftime('%Y-%m-%d')})")
            elif arg == '7days':
                response_message += format_summary("Last 7 Days", summary_last_7_days)
            elif arg == '1month':
                response_message += format_summary("Last 1 Month", summary_last_30_days)
            else: # Default to all summaries if no specific argument or invalid argument
                response_message += format_summary("Current Day", summary_today, f"({today.strftime('%Y-%m-%d')})")
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday.strftime('%Y-%m-%d')})")
                response_message += format_summary("Last 7 Days", summary_last_7_days)
                response_message += format_summary("Last 1 Month", summary_last_30_days)

            await update.message.reply_html(response_message)

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

# --- Flask Endpoints (Only active when served by Gunicorn/Werkzeug on Render) ---
# These routes are for when the bot is deployed on Render using webhooks.
# They are part of the 'app' Flask instance, which is not directly run
# when the bot is in local polling mode.
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
    # This endpoint doesn't need to interact with the bot_instance's ping_service
    # directly for its primary purpose (keeping Render awake).
    # The bot's /coldstart command handles the internal status.
    return "Bot is awake!", 200

# --- Entry point for Local Polling ---
if __name__ == "__main__":
    # For local testing, we run in polling mode.
    # For Render deployment, the 'startCommand' in render.yaml will run 'gunicorn bot:app'
    # which will activate the Flask 'app' and its webhook/coldstart endpoints.
    
    # Ensure environment variables are loaded if using .env file
    from dotenv import load_dotenv
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    google_credentials_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")
    render_external_url = os.getenv("RENDER_EXTERNAL_URL") # Still needed for PingService URL

    if not all([bot_token, spreadsheet_id, google_credentials_json_b64]):
        logger.error("Missing one or more required environment variables for local polling. Please check BOT_TOKEN, GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON_BASE64.")
        exit(1)

    # Initialize the bot instance
    bot_instance = BabyTrackerBot(bot_token, spreadsheet_id, google_credentials_json_b64)
    
    # Set the PingService URL (even if dummy for local)
    coldstart_url = f"{render_external_url}/coldstart" # Will be http://localhost:8000/coldstart
    bot_instance.ping_service.url = coldstart_url
    logger.info(f"PingService URL set to: {coldstart_url}")

    # Create the Application and pass your bot's token.
    # This is the PTB application instance
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

    logger.info("Starting bot in polling mode...")
    # Run the bot in polling mode. This is a blocking call.
    telegram_app_instance.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot has stopped.")

