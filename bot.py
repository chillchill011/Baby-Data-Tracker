import os
import logging
import json
import base64
from datetime import datetime, timedelta
import asyncio
import requests # For the coldstart ping
from flask import Flask, request # For webhook and coldstart endpoint

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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

# Import WsgiToAsgi from asgiref for Flask-Uvicorn compatibility
from asgiref.wsgi import WsgiToAsgi


# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App for Webhook and Cold Start ---
# Initialize the Flask app FIRST with a distinct name
flask_app = Flask(__name__)

# Global variable to hold the bot instance
telegram_app_instance = None
bot_instance_global = None # Also make bot_instance global for access in setup

# --- Ping Service for Cold Start ---
class PingService:
    def __init__(self, url):
        self.url = url
        self.is_active = False
        self.last_ping = None

    async def activate(self): # Made activate async
        """Activate the service with a single ping."""
        try:
            # Use asyncio.to_thread to run the synchronous requests.get in a separate thread
            response = await asyncio.to_thread(requests.get, self.url)
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
        self.ping_service = PingService("") # Placeholder, will be updated in setup_bot_application

    def _authenticate_google_sheets(self):
        """Authenticates with Google Sheets using service account credentials."""
        try:
            # Decode base64 credentials and load as JSON
            decoded_string = base64.b64decode(self.credentials_json_b64).decode('utf-8')
            credentials_info = json.loads(decoded_string)
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            creds = Credentials.from_service_account_info(credentials_info, scopes=scope)
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

    # --- Keyboard Definition ---
    def _get_main_keyboard(self):
        """Returns the main ReplyKeyboardMarkup for bot actions."""
        keyboard = [
            [KeyboardButton("Poop"), KeyboardButton("Pee")],
            [KeyboardButton("Feed"), KeyboardButton("Medication")],
            [KeyboardButton("Summary"), KeyboardButton("Cold Start")],
            [KeyboardButton("Help")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends a welcome message and lists commands."""
        user = update.effective_user
        welcome_message = (
            f"Hi {user.mention_html()}! I'm your Baby Tracker Bot.\n\n"
            "Use the keyboard below to log activities or get summaries.\n"
            "You can also type commands:\n"
            "• `/feed &lt;minutes&gt;`: Log a feeding session (e.g., `/feed 15`)\n"
            "• `/medication [name]`: Log medication (e.g., `/medication Tylenol`)\n"
            "• `/summary [today|yesterday|7days|1month]`: Get a summary for specific periods (e.g., `/summary 7days` or just `/summary` for all)\n"
            "• `/coldstart`: Wake up the bot if it's inactive (for Render.com free tier)\n"
            "• `/help` or `/menu`: Show this message and the keyboard again"
        )
        await update.message.reply_html(welcome_message, reply_markup=self._get_main_keyboard())
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
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends the main menu keyboard."""
        await update.message.reply_text("Here's the main menu:", reply_markup=self._get_main_keyboard())


    async def coldstart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /coldstart command to activate the bot."""
        logger.info("coldstart command received.") # New log
        if not self.ping_service.is_active:
            logger.info("Ping service is not active, attempting to activate.") # New log
            if await self.ping_service.activate(): # Added await here
                logger.info("Ping service activated successfully, sending success message.") # New log
                await update.message.reply_text(
                    "🟢 Bot Successfully Activated!\n\n"
                    "I'm awake and ready to help you track baby activities.\n\n"
                    "You can:\n"
                    "• Log activities like /feed, /poop, /pee, /medication\n"
                    "• Get summaries with /summary\n"
                    "• View all commands with /start"
                )
            else:
                logger.error("Ping service activation failed, sending error message.") # New log
                await update.message.reply_text("❌ Failed to activate bot. Please try again.")
        else:
            logger.info("Ping service is already active, sending info message.") # New log
            await update.message.reply_text(
                "ℹ️ I'm already active and ready!\n\n"
                "You can start logging activities."
            )
    
    async def handle_keyboard_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles text messages that correspond to keyboard buttons."""
        text = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Handling keyboard input: {text} from user {user_id}") # New log

        if text == "Poop":
            await self.poop(update, context)
        elif text == "Pee":
            await self.pee(update, context)
        elif text == "Feed":
            context.user_data[user_id] = {'awaiting_input_for': 'feed'}
            await update.message.reply_text("Please type the feed duration in minutes (e.g., `15`).")
        elif text == "Medication":
            context.user_data[user_id] = {'awaiting_input_for': 'medication'}
            await update.message.reply_text("Please type the medication name (e.g., `Tylenol`).")
        elif text == "Summary":
            await update.message.reply_text("Please type `/summary` followed by `today`, `yesterday`, `7days`, or `1month` (e.g., `/summary 7days`). Or just `/summary` for all.")
        elif text == "Cold Start":
            await self.coldstart(update, context)
        elif text == "Help":
            await self.help_command(update, context)
        else:
            # This handler should ideally only catch button presses.
            # Free text input will be handled by handle_free_text_input.
            pass

    async def handle_free_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles free text input, especially after a button press for Feed/Medication."""
        text = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Handling free text input: {text} from user {user_id}") # New log
        
        # Check if the user is awaiting specific input
        if user_id in context.user_data and 'awaiting_input_for' in context.user_data[user_id]:
            awaiting_for = context.user_data[user_id]['awaiting_input_for']
            logger.info(f"User {user_id} is awaiting input for: {awaiting_for}") # New log

            if awaiting_for == 'feed':
                if text.isdigit():
                    context.args = [text] # Temporarily set context.args for the feed handler
                    await self._log_activity(update, "Feed", f"{text} mins")
                    del context.user_data[user_id]['awaiting_input_for'] # Clear state
                else:
                    await update.message.reply_text("❌ Invalid input. Please enter a number for feed duration (e.g., `15`).")
                    del context.user_data[user_id]['awaiting_input_for'] # Clear state
            elif awaiting_for == 'medication':
                if text: # Any non-empty text is considered the medication name
                    context.args = [text] # Temporarily set context.args for the medication handler
                    await self._log_activity(update, "Medication", text)
                    del context.user_data[user_id]['awaiting_input_for'] # Clear state
                else:
                    await update.message.reply_text("❌ Invalid input. Please enter a name for medication.")
                    del context.user_data[user_id]['awaiting_input_for'] # Clear state
            else:
                # Fallback if awaiting_input_for is set but doesn't match expected values
                await update.message.reply_text("I'm not sure what to do with that. Please use the menu or type a command.", reply_markup=self._get_main_keyboard())
                if user_id in context.user_data: # Ensure it's cleared
                    del context.user_data[user_id]['awaiting_input_for']
        else:
            # If no specific input is awaited, it's an unrecognized message
            await update.message.reply_text("I'm not sure what that means. Please use the menu or type a command.", reply_markup=self._get_main_keyboard())


# --- Main function to set up and run the bot (for Render deployment) ---
async def setup_bot_application():
    """Initializes and sets up the PTB Application for webhooks."""
    global telegram_app_instance
    global bot_instance_global # Access the global bot instance

    # Load environment variables (from Render's env vars)
    bot_token = os.getenv("BOT_TOKEN") # Changed from TELEGRAM_TOKEN
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID") # Changed from SPREADSHEET_ID
    google_credentials_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")
    render_external_url = os.getenv("RENDER_EXTERNAL_URL")

    # --- DEBUGGING ENVIRONMENT VARIABLES ---
    logger.info(f"DEBUG ENV: TELEGRAM_TOKEN length: {len(bot_token) if bot_token else 'None'}")
    logger.info(f"DEBUG ENV: SPREADSHEET_ID: {spreadsheet_id}")
    logger.info(f"DEBUG ENV: GOOGLE_CREDENTIALS_JSON_BASE64 length: {len(google_credentials_json_b64) if google_credentials_json_b64 else 'None'}")
    logger.info(f"DEBUG ENV: RENDER_EXTERNAL_URL: {render_external_url}")
    # --- END DEBUGGING ---

    # Explicitly check if RENDER_EXTERNAL_URL is None or empty string
    if not render_external_url:
        logger.error("RENDER_EXTERNAL_URL environment variable is missing or empty. Please set it in Render's dashboard.")
        # We can't proceed without this. Exit the application.
        exit(1)

    if not all([bot_token, spreadsheet_id, google_credentials_json_b64]):
        logger.error("Missing one or more required environment variables (BOT_TOKEN, GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON_BASE64).")
        exit(1)

    # Initialize the bot instance
    bot_instance_global = BabyTrackerBot(bot_token, spreadsheet_id, google_credentials_json_b64)
    
    # Set the PingService URL
    coldstart_url = f"{render_external_url}/coldstart"
    bot_instance_global.ping_service.url = coldstart_url
    logger.info(f"PingService URL set to: {coldstart_url}")

    # Create the Application and pass your bot's token.
    telegram_app_instance = Application.builder().token(bot_token).build()

    # Register command handlers
    telegram_app_instance.add_handler(CommandHandler("start", bot_instance_global.start))
    telegram_app_instance.add_handler(CommandHandler("feed", bot_instance_global.feed))
    telegram_app_instance.add_handler(CommandHandler("poop", bot_instance_global.poop))
    telegram_app_instance.add_handler(CommandHandler("pee", bot_instance_global.pee))
    telegram_app_instance.add_handler(CommandHandler("medication", bot_instance_global.medication))
    telegram_app_instance.add_handler(CommandHandler("summary", bot_instance_global.summary))
    telegram_app_instance.add_handler(CommandHandler("help", bot_instance_global.help_command))
    telegram_app_instance.add_handler(CommandHandler("menu", bot_instance_global.menu_command))
    telegram_app_instance.add_handler(CommandHandler("coldstart", bot_instance_global.coldstart))

    # IMPORTANT: Order of MessageHandlers matters!
    telegram_app_instance.add_handler(MessageHandler(filters.TEXT & filters.Regex("^(Poop|Pee|Feed|Medication|Summary|Cold Start|Help)$"), bot_instance_global.handle_keyboard_input))
    telegram_app_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance_global.handle_free_text_input))

    # Set up webhook
    webhook_path = "/webhook"
    logger.info(f"Setting webhook to {render_external_url}{webhook_path}")
    await telegram_app_instance.bot.set_webhook(url=f"{render_external_url}{webhook_path}")

    logger.info("Telegram bot application prepared for webhook.")
    # Initialize the Application
    await telegram_app_instance.initialize()
    logger.info("Telegram Application initialized.")


# --- Flask Endpoints ---
# These routes are for when the bot is deployed on Render using webhooks.
# Uvicorn will import this module and run the 'app' Flask instance.
@flask_app.route("/webhook", methods=["POST"]) # Use flask_app.route
async def webhook_handler():
    """Handle incoming Telegram updates."""
    logger.info("Webhook handler received a request.") # New log
    try:
        # Read the raw request body
        request_body = request.get_data() # REMOVED await here
        update_json_str = request_body.decode('utf-8')
        
        logger.info(f"Received raw update body: {update_json_str}") # New log

        update_json = json.loads(update_json_str)
        logger.info(f"Parsed update JSON: {update_json}") # New log

        global telegram_app_instance
        if telegram_app_instance is None:
            logger.error("Telegram application instance not initialized in webhook handler.")
            return "Bot not ready", 500

        update = Update.de_json(update_json, telegram_app_instance.bot)
        logger.info(f"Processing update: {update}") # New log
        
        await telegram_app_instance.process_update(update)
        logger.info("Update processed successfully.") # New log
        return "ok"
    except Exception as e:
        logger.error(f"Error in webhook_handler: {e}", exc_info=True)
        return "Error", 500

@flask_app.route("/coldstart", methods=["GET"]) # Use flask_app.route
def coldstart_endpoint():
    """Simple endpoint to keep Render service awake."""
    logger.info("Coldstart endpoint hit.")
    return "Bot is awake!", 200

# This __main__ block is only for direct execution (e.g., local testing of this deploy file)
# It will NOT be executed by Uvicorn on Render.
if __name__ == "__main__":
    # Run the bot setup asynchronously
    asyncio.run(setup_bot_application())
    
    # Run the Flask app
    port = int(os.environ.get("PORT", 8000))
    # Use app.run() for local development. For Render, Gunicorn/Werkzeug will serve.
    # For Render, the 'startCommand' in render.yaml will typically be `gunicorn bot:app`
    # where 'bot' is the module name and 'app' is the Flask instance.
    # For simplicity here, we'll just run Flask directly, but be aware of production setups.
    logger.info(f"Starting Flask app locally on port {port} for webhook testing.")
    flask_app.run(host="0.0.0.0", port=port) # Run flask_app here

# Global initialization for Uvicorn
# Uvicorn directly imports the 'app' object.
# We need to ensure setup_bot_application runs once when the module is loaded.
# This will happen when Uvicorn imports 'bot.py'.
try:
    # Attempt to run the async setup when the module is loaded.
    # This might run in a different event loop context than Uvicorn's main loop,
    # but it ensures initialization happens.
    # We use asyncio.get_event_loop() and check if it's running to avoid RuntimeError.
    loop = asyncio.get_event_loop()
    if loop.is_running():
        logger.warning("Event loop already running, scheduling PTB setup as a task.")
        loop.create_task(setup_bot_application())
    else:
        asyncio.run(setup_bot_application())
except RuntimeError as e:
    # This specific RuntimeError happens if asyncio.run() is called when a loop is already running.
    # For web servers like Uvicorn, they manage their own loop.
    # We log a warning and assume Uvicorn's loop will handle subsequent async calls.
    if "cannot run an event loop while another loop is running" in str(e):
        logger.warning("Event loop already running during global setup. This is expected with Uvicorn.")
    else:
        logger.error(f"Failed to run global app init: {e}")
        raise # Re-raise other unexpected RuntimeErrors
except Exception as e:
    logger.error(f"Error during global app init: {e}")
    raise

# Wrap the Flask app with WsgiToAsgi for Uvicorn compatibility AFTER routes are defined
# This makes the WSGI Flask app behave like an ASGI app for Uvicorn
app = WsgiToAsgi(flask_app) # Wrap flask_app and assign to 'app'
