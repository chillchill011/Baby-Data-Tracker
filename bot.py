import os
import logging
import json
import base64
from datetime import datetime, timedelta
import asyncio
import requests
from flask import Flask, request

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

# Import pytz for timezone handling
import pytz

# Import matplotlib for plotting graphs
import matplotlib.pyplot as plt
import io
import pandas as pd # Used for easier data aggregation for plotting

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define Indian Standard Time (IST) timezone
IST = pytz.timezone('Asia/Kolkata')

# --- Flask App for Webhook and Cold Start ---
flask_app = Flask(__name__)

# Global variable to hold the bot instance
telegram_app_instance = None
bot_instance_global = None

# --- Baby Tracker Bot Class ---
class BabyTrackerBot:
    def __init__(self, token: str, spreadsheet_id: str, credentials_json_b64: str):
        self.token = token
        self.spreadsheet_id = spreadsheet_id
        self.credentials_json_b64 = credentials_json_b64
        self.gc = self._authenticate_google_sheets()
        self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
        self.worksheet = self._get_or_create_worksheet("BabyLog")

    def _authenticate_google_sheets(self):
        try:
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
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.info(f"Worksheet '{sheet_name}' found.")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Worksheet '{sheet_name}' not found, creating new one.")
            worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="10")
            headers = ['Timestamp', 'Activity Type', 'Value/Details', 'Telegram User ID']
            worksheet.append_row(headers)
            logger.info(f"Worksheet '{sheet_name}' created with headers.")
        
        if not worksheet.row_values(1):
            headers = ['Timestamp', 'Activity Type', 'Value/Details', 'Telegram User ID']
            worksheet.append_row(headers)
            logger.info(f"Headers added to existing empty worksheet '{sheet_name}'.")
            
        return worksheet

    def _get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("Poop"), KeyboardButton("Pee")],
            [KeyboardButton("Feed"), KeyboardButton("Medication")],
<<<<<<< HEAD
<<<<<<< HEAD
            [KeyboardButton("Vitamin D")],
            [KeyboardButton("Summary (Today)"), KeyboardButton("Summary (7 Days)")],
            [KeyboardButton("Summary (30 Days)"), KeyboardButton("Summary (90 Days)")],
            [KeyboardButton("Cold Start"), KeyboardButton("Help")]
=======
            [KeyboardButton("Vitamin D")], # New button for Vitamin D
            [KeyboardButton("Summary"), KeyboardButton("Cold Start")],
            [KeyboardButton("Help")]
>>>>>>> parent of 3580d1b (Summary expansion)
=======
            [KeyboardButton("Vitamin D")], # New button for Vitamin D
            [KeyboardButton("Summary"), KeyboardButton("Cold Start")],
            [KeyboardButton("Help")]
>>>>>>> parent of 3580d1b (Summary expansion)
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        welcome_message = (
            f"Hi {user.mention_html()}! I'm your Baby Tracker Bot.\n\n"
            "Use the keyboard below to log activities or get summaries.\n"
            "You can also type commands:\n"
            "• `/feed (minutes)`: Log a feeding session (e.g., `/feed 15`)\n" # Fixed formatting here
            "• `/medication [name]`: Log medication (e.g., `/medication Tylenol`)\n"
            "• `/vitamind`: Log Vitamin D medication\n"
<<<<<<< HEAD
<<<<<<< HEAD
            "• `/summary [today|yesterday|7days|1month|3month]`: Get a summary for specific periods (e.g., `/summary 7days` or just `/summary` for all)\n"
=======
            "• `/summary [today|yesterday|7days|1month]`: Get a summary for specific periods (e.g., `/summary 7days` or just `/summary` for all)\n"
>>>>>>> parent of 3580d1b (Summary expansion)
=======
            "• `/summary [today|yesterday|7days|1month]`: Get a summary for specific periods (e.g., `/summary 7days` or just `/summary` for all)\n"
>>>>>>> parent of 3580d1b (Summary expansion)
            "• `/coldstart`: Wake up the bot if it's inactive (for Render.com free tier)\n"
            "• `/help` or `/menu`: Show this message and the keyboard again"
        )
        await update.message.reply_html(welcome_message, reply_markup=self._get_main_keyboard())
        logger.info(f"User {user.id} started the bot.")

    async def _log_activity(self, update: Update, activity_type: str, value: str = "N/A") -> None:
        """Helper function to log activities to Google Sheet."""
        # Get current time and localize to IST
        now_ist = datetime.now(IST)
        timestamp = now_ist.strftime('%Y-%m-%d %H:%M:%S')
        user_id = update.effective_user.username or str(update.effective_user.id)
        row = [timestamp, activity_type, value, user_id]
        
        try:
            self.worksheet.append_row(row)
            logger.info(f"Logged activity: {activity_type}, Value: {value}, User: {user_id}")
            await update.message.reply_text(f"✅ Logged {activity_type} at {now_ist.strftime('%H:%M:%S')} on {now_ist.strftime('%Y-%m-%d')} (IST).")
        except Exception as e:
            logger.error(f"Error logging activity to Google Sheet: {e}")
            await update.message.reply_text("❌ Failed to log activity. Please try again later.")

    async def feed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("❌ Please specify feed duration in minutes. Example: `/feed 15`")
            return
        duration = context.args[0]
        await self._log_activity(update, "Feed", f"{duration} mins")

    async def poop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._log_activity(update, "Poop")

    async def pee(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._log_activity(update, "Pee")

    async def medication(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        med_name = " ".join(context.args) if context.args else "Medication"
        await self._log_activity(update, "Medication", med_name)

    async def vitamind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Logs Vitamin D medication directly."""
        await self._log_activity(update, "Medication", "Vitamin D")

    def _generate_activity_bar_chart(self, records_for_period, period_name):
        """Generates a bar chart of daily activity counts for a given period."""
        if not records_for_period:
            return None

        # Prepare data for plotting
        df = pd.DataFrame(records_for_period)
        
        # Convert Timestamp to datetime objects and localize
        # Handle both '%Y-%m-%d %H:%M:%S' and '%Y-%m-%d %H:%M' formats
        def parse_and_localize_timestamp(ts_str):
            try:
                dt_naive = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt_naive = datetime.strptime(ts_str, '%Y-%m-%d %H:%M')
            return IST.localize(dt_naive).date()

        df['Date'] = df['Timestamp'].apply(parse_and_localize_timestamp)
        
        # Adjust 'Activity Type' for Vitamin D to differentiate
        df['Activity Type Plot'] = df.apply(
            lambda row: 'Vitamin D' if row['Activity Type'] == 'Medication' and row['Value/Details'] == 'Vitamin D'
            else row['Activity Type'], axis=1
        )
        
        # Filter out original 'Medication' if it's Vitamin D for plotting purposes
        # And handle 'Feed' to just count occurrences, not duration for this chart
        activity_counts = df.groupby(['Date', 'Activity Type Plot']).size().unstack(fill_value=0)

        # Ensure all expected columns are present, even if no data for them
        expected_activities = ['Poop', 'Pee', 'Feed', 'Medication', 'Vitamin D']
        for activity in expected_activities:
            if activity not in activity_counts.columns:
                activity_counts[activity] = 0
        
        # Sort by date
        activity_counts = activity_counts.sort_index()

        # Plotting
        fig, ax = plt.subplots(figsize=(10, 6)) # Adjust figure size as needed
        
        # Define colors for consistency
        colors = {
            'Poop': '#8B4513', # SaddleBrown
            'Pee': '#FFD700',  # Gold
            'Feed': '#4682B4', # SteelBlue
            'Medication': '#800080', # Purple
            'Vitamin D': '#228B22' # ForestGreen
        }
        
        # Get the activities that actually have data to plot
        activities_to_plot = [col for col in expected_activities if col in activity_counts.columns and activity_counts[col].sum() > 0]

        # Plot bars for each activity type
        activity_counts[activities_to_plot].plot(kind='bar', ax=ax, color=[colors.get(x, '#CCCCCC') for x in activities_to_plot], width=0.8)

        ax.set_title(f'Daily Activity Counts - {period_name}', fontsize=16)
        ax.set_xlabel('Date (IST)', fontsize=12)
        ax.set_ylabel('Count', fontsize=12)
        ax.tick_params(axis='x', rotation=45)
        ax.legend(title='Activity Type')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()

        # Save plot to a BytesIO object
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig) # Close the plot to free memory
        return buf


    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Provides a summary of activities for various periods."""
        try:
            all_records = self.worksheet.get_all_records()
            
            # Get current date in IST
            now_ist = datetime.now(IST)
            today_ist = now_ist.date()
            yesterday_ist = today_ist - timedelta(days=1)
            
<<<<<<< HEAD
<<<<<<< HEAD
            # Initialize summary dictionaries with new 'vitamin_d' field
            summary_today = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0, 'vitamin_d': 0}
            summary_yesterday = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0, 'vitamin_d': 0}
            summary_last_7_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0, 'vitamin_d': 0}
            summary_last_30_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0, 'vitamin_d': 0}
            summary_last_90_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0, 'vitamin_d': 0}

            # Lists to hold records for plotting
            records_7_days = []
            records_30_days = []
            records_90_days = []

=======
=======
>>>>>>> parent of 3580d1b (Summary expansion)
            summary_today = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_yesterday = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_last_7_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
            summary_last_30_days = {'pee': 0, 'poop': 0, 'feed_count': 0, 'feed_total_mins': 0, 'medications': 0}
<<<<<<< HEAD
>>>>>>> parent of 3580d1b (Summary expansion)
=======
>>>>>>> parent of 3580d1b (Summary expansion)

            for record in all_records:
                try:
                    record_timestamp_str = record['Timestamp']
                    
                    # Parse timestamp as naive, then localize to IST
                    try:
                        # Try parsing with seconds first
                        record_dt_naive = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Fallback to parsing without seconds if needed
                        record_dt_naive = datetime.strptime(record_timestamp_str, '%Y-%m-%d %H:%M')
                    
                    record_dt_ist = IST.localize(record_dt_naive) # Localize to IST
                    record_date_ist = record_dt_ist.date()

                    activity_type = record['Activity Type']
                    value_details = record['Value/Details']
                    
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

                    if record_date_ist == today_ist:
                        update_summary_dict(summary_today, activity_type, value_details)
                    
                    if record_date_ist == yesterday_ist:
                        update_summary_dict(summary_yesterday, activity_type, value_details)

                    if today_ist - record_date_ist < timedelta(days=7):
                        update_summary_dict(summary_last_7_days, activity_type, value_details)
                        records_7_days.append(record)

                    if today_ist - record_date_ist < timedelta(days=30):
                        update_summary_dict(summary_last_30_days, activity_type, value_details)
<<<<<<< HEAD
<<<<<<< HEAD
                        records_30_days.append(record)
                    
                    if today_ist - record_date_ist < timedelta(days=90):
                        update_summary_dict(summary_last_90_days, activity_type, value_details)
                        records_90_days.append(record)
=======
>>>>>>> parent of 3580d1b (Summary expansion)
=======
>>>>>>> parent of 3580d1b (Summary expansion)

                except Exception as e:
                    logger.warning(f"Skipping malformed record: {record} - Error: {e}")
                    continue

            response_message = "--- Baby Activity Summary (IST) ---\n\n" # Updated title
            
            def format_summary(title, data, date_info=""):
                return (
                    f"**{title}** {date_info}:\n"
                    f"  Pee: {data['pee']}\n"
                    f"  Poop: {data['poop']}\n"
                    f"  Feeds: {data['feed_count']} (Total {data['feed_total_mins']} mins)\n"
                    f"  Medications: {data['medications']}\n\n"
                )
<<<<<<< HEAD
<<<<<<< HEAD
                
                if period_days is None: # For Today/Yesterday
                    formatted_str += f"  Vitamin D: {data['vitamin_d']} ✅\n"
                    formatted_str += f"  Medications: {data['medications']}\n\n"
                else: # For 7/30/90 days
                    formatted_str += f"  Vitamin D: {data['vitamin_d']} [Given] / {period_days} Days\n"
                    formatted_str += f"  Medications: {data['medications']}\n\n"
                return formatted_str
=======
>>>>>>> parent of 3580d1b (Summary expansion)
=======
>>>>>>> parent of 3580d1b (Summary expansion)

            arg = context.args[0].lower() if context.args else None
            
            graph_data = None
            graph_period_name = ""

            if arg == 'today':
                response_message += format_summary("Current Day", summary_today, f"({today_ist.strftime('%Y-%m-%d')})")
            elif arg == 'yesterday':
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday_ist.strftime('%Y-%m-%d')})")
            elif arg == '7days':
<<<<<<< HEAD
<<<<<<< HEAD
                response_message += format_summary("Last 7 Days", summary_last_7_days, period_days=7)
                graph_data = records_7_days
                graph_period_name = "Last 7 Days"
            elif arg == '1month':
                response_message += format_summary("Last 1 Month", summary_last_30_days, period_days=30)
                graph_data = records_30_days
                graph_period_name = "Last 30 Days"
            elif arg == '3month':
                response_message += format_summary("Last 3 Months", summary_last_90_days, period_days=90)
                graph_data = records_90_days
                graph_period_name = "Last 90 Days"
            else: # Default to showing all summaries and no graph
                response_message += format_summary("Current Day", summary_today, f"({today_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Last 7 Days", summary_last_7_days, period_days=7)
                response_message += format_summary("Last 1 Month", summary_last_30_days, period_days=30)
                response_message += format_summary("Last 3 Months", summary_last_90_days, period_days=90)
=======
                response_message += format_summary("Last 7 Days", summary_last_7_days)
            elif arg == '1month':
                response_message += format_summary("Last 1 Month", summary_last_30_days)
            else:
                response_message += format_summary("Current Day", summary_today, f"({today_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Last 7 Days", summary_last_7_days)
                response_message += format_summary("Last 1 Month", summary_last_30_days)
>>>>>>> parent of 3580d1b (Summary expansion)
=======
                response_message += format_summary("Last 7 Days", summary_last_7_days)
            elif arg == '1month':
                response_message += format_summary("Last 1 Month", summary_last_30_days)
            else:
                response_message += format_summary("Current Day", summary_today, f"({today_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Previous Day", summary_yesterday, f"({yesterday_ist.strftime('%Y-%m-%d')})")
                response_message += format_summary("Last 7 Days", summary_last_7_days)
                response_message += format_summary("Last 1 Month", summary_last_30_days)
>>>>>>> parent of 3580d1b (Summary expansion)

            await update.message.reply_html(response_message)

            # Send graph if applicable
            if graph_data:
                graph_buffer = self._generate_activity_bar_chart(graph_data, graph_period_name)
                if graph_buffer:
                    await update.message.reply_photo(photo=graph_buffer, caption=f"Activity trends for {graph_period_name}")

        except Exception as e:
            logger.error(f"Error generating summary: {e}", exc_info=True)
            await update.message.reply_text("❌ Error generating summary. Please try again.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.start(update, context)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Here's the main menu:", reply_markup=self._get_main_keyboard())


    async def coldstart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info("coldstart command received.")
        await update.message.reply_text(
            "🟢 Bot is awake and ready!\n\n"
            "You can:\n"
            "• Log activities like /feed, /poop, /pee, /medication\n"
            "• Get summaries with /summary\n"
            "• View all commands with /start"
        )
        logger.info("Coldstart response sent (simplified).")
    
    async def handle_keyboard_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Handling keyboard input: {text} from user {user_id}")

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
        elif text == "Vitamin D": # New handler for Vitamin D button
            await self.vitamind(update, context)
<<<<<<< HEAD
<<<<<<< HEAD
        elif text == "Summary (Today)":
            context.args = ['today']
            await self.summary(update, context)
        elif text == "Summary (7 Days)":
            context.args = ['7days']
            await self.summary(update, context)
        elif text == "Summary (30 Days)":
            context.args = ['1month']
            await self.summary(update, context)
        elif text == "Summary (90 Days)":
            context.args = ['3month']
            await self.summary(update, context)
=======
        elif text == "Summary":
            await update.message.reply_text("Please type `/summary` followed by `today`, `yesterday`, `7days`, or `1month` (e.g., `/summary 7days`). Or just `/summary` for all.")
>>>>>>> parent of 3580d1b (Summary expansion)
=======
        elif text == "Summary":
            await update.message.reply_text("Please type `/summary` followed by `today`, `yesterday`, `7days`, or `1month` (e.g., `/summary 7days`). Or just `/summary` for all.")
>>>>>>> parent of 3580d1b (Summary expansion)
        elif text == "Cold Start":
            await self.coldstart(update, context)
        elif text == "Help":
            await self.help_command(update, context)
        else:
            pass

    async def handle_free_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text
        user_id = update.effective_user.id
        logger.info(f"Handling free text input: {text} from user {user_id}")
        
        if user_id in context.user_data and 'awaiting_input_for' in context.user_data[user_id]:
            awaiting_for = context.user_data[user_id]['awaiting_input_for']
            logger.info(f"User {user_id} is awaiting input for: {awaiting_for}")

            if awaiting_for == 'feed':
                if text.isdigit():
                    context.args = [text]
                    await self._log_activity(update, "Feed", f"{text} mins")
                    del context.user_data[user_id]['awaiting_input_for']
                else:
                    await update.message.reply_text("❌ Invalid input. Please enter a number for feed duration (e.g., `15`).")
                    del context.user_data[user_id]['awaiting_input_for']
            elif awaiting_for == 'medication':
                if text:
                    context.args = [text]
                    await self._log_activity(update, "Medication", text)
                    del context.user_data[user_id]['awaiting_input_for']
                else:
                    await update.message.reply_text("❌ Invalid input. Please enter a name for medication.")
                    del context.user_data[user_id]['awaiting_input_for']
            else:
                await update.message.reply_text("I'm not sure what to do with that. Please use the menu or type a command.", reply_markup=self._get_main_keyboard())
                if user_id in context.user_data:
                    del context.user_data[user_id]['awaiting_input_for']
        else:
            await update.message.reply_text("I'm not sure what that means. Please use the menu or type a command.", reply_markup=self._get_main_keyboard())


# --- Main function to set up and run the bot (for Render deployment) ---
async def setup_bot_application():
    global telegram_app_instance
    global bot_instance_global

    bot_token = os.getenv("BOT_TOKEN")
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    google_credentials_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")
    render_external_url = os.getenv("RENDER_EXTERNAL_URL")

    logger.info(f"DEBUG ENV: BOT_TOKEN length: {len(bot_token) if bot_token else 'None'}")
    logger.info(f"DEBUG ENV: GOOGLE_SHEET_ID: {spreadsheet_id}")
    logger.info(f"DEBUG ENV: GOOGLE_CREDENTIALS_JSON_BASE64 length: {len(google_credentials_json_b64) if google_credentials_json_b64 else 'None'}")
    logger.info(f"DEBUG ENV: RENDER_EXTERNAL_URL: {render_external_url}")

    if not render_external_url:
        logger.error("RENDER_EXTERNAL_URL environment variable is missing or empty. Please set it in Render's dashboard.")
        exit(1)

    if not all([bot_token, spreadsheet_id, google_credentials_json_b64]):
        logger.error("Missing one or more required environment variables (BOT_TOKEN, GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON_BASE64).")
        exit(1)

    bot_instance_global = BabyTrackerBot(bot_token, spreadsheet_id, google_credentials_json_b64)
    
    # PingService URL setup is no longer needed here as it's not used for internal pinging.

    telegram_app_instance = Application.builder().token(bot_token).build()

    telegram_app_instance.add_handler(CommandHandler("start", bot_instance_global.start))
    telegram_app_instance.add_handler(CommandHandler("feed", bot_instance_global.feed))
    telegram_app_instance.add_handler(CommandHandler("poop", bot_instance_global.poop))
    telegram_app_instance.add_handler(CommandHandler("pee", bot_instance_global.pee))
    telegram_app_instance.add_handler(CommandHandler("medication", bot_instance_global.medication))
    telegram_app_instance.add_handler(CommandHandler("vitamind", bot_instance_global.vitamind)) # Added new CommandHandler for vitamind
    telegram_app_instance.add_handler(CommandHandler("summary", bot_instance_global.summary))
    telegram_app_instance.add_handler(CommandHandler("help", bot_instance_global.help_command))
    telegram_app_instance.add_handler(CommandHandler("menu", bot_instance_global.menu_command))
    telegram_app_instance.add_handler(CommandHandler("coldstart", bot_instance_global.coldstart))

    telegram_app_instance.add_handler(MessageHandler(filters.TEXT & filters.Regex("^(Poop|Pee|Feed|Medication|Summary|Cold Start|Help|Vitamin D)$"), bot_instance_global.handle_keyboard_input)) # Updated Regex
    telegram_app_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance_global.handle_free_text_input))

    webhook_path = "/webhook"
    logger.info(f"Setting webhook to {render_external_url}{webhook_path}")
    await telegram_app_instance.bot.set_webhook(url=f"{render_external_url}{webhook_path}")

    logger.info("Telegram bot application prepared for webhook.")
    await telegram_app_instance.initialize()
    logger.info("Telegram Application initialized.")


# --- Flask Endpoints ---
@flask_app.route("/webhook", methods=["POST"])
async def webhook_handler():
    logger.info("Webhook handler received a request.")
    try:
        request_body = request.get_data()
        update_json_str = request_body.decode('utf-8')
        
        logger.info(f"Received raw update body: {update_json_str}")

        update_json = json.loads(update_json_str)
        logger.info(f"Parsed update JSON: {update_json}")

        global telegram_app_instance
        if telegram_app_instance is None:
            logger.error("Telegram application instance not initialized in webhook handler.")
            return "Bot not ready", 500

        update = Update.de_json(update_json, telegram_app_instance.bot)
        logger.info(f"Processing update: {update}")
        
        await telegram_app_instance.process_update(update)
        logger.info("Update processed successfully.")
        return "ok"
    except Exception as e:
        logger.error(f"Error in webhook_handler: {e}", exc_info=True)
        return "Error", 500
    finally:
        logger.info("Webhook handler finished.")
        return "ok"


@flask_app.route("/coldstart", methods=["GET"])
def coldstart_endpoint():
    logger.info("Coldstart endpoint hit.")
    return "Bot is awake!", 200

# Wrap the Flask app with WsgiToAsgi for Uvicorn compatibility AFTER routes are defined
app = WsgiToAsgi(flask_app)


# This __main__ block is only for direct execution (e.g., local testing of this deploy file)
# It will NOT be executed by Uvicorn on Render.
if __name__ == "__main__":
    asyncio.run(setup_bot_application())
    
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Flask app locally on port {port} for webhook testing.")
    flask_app.run(host="0.0.0.0", port=port)

# Global initialization for Uvicorn
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        logger.warning("Event loop already running, scheduling PTB setup as a task.")
        loop.create_task(setup_bot_application())
    else:
        asyncio.run(setup_bot_application())
except RuntimeError as e:
    if "cannot run an event loop while another loop is running" in str(e):
        logger.warning("Event loop already running during global setup. This is expected with Uvicorn.")
    else:
        logger.error(f"Failed to run global app init: {e}")
        raise
except Exception as e:
    logger.error(f"Error during global app init: {e}")
    raise
