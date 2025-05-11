# bot.py
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from config import TELEGRAM_BOT_TOKEN, LOG_LEVEL
from utils import setup_logging, format_user_message
import uuid
import time
import requests
import portalocker

logger = setup_logging(LOG_LEVEL)

# Social media links
SOCIAL_MEDIA_LINKS = [
    ("WhatsApp", "https://whatsapp.com/channel/0029Vak10xu2ER6Fc7Cth73m"),
    ("YouTube", "https://youtube.com/gnextpip?si=6_zB83LCg4ObGiix"),
    ("Telegram", "https://t.me/kriptectest"),
    ("Twitter", "https://x.com/crypto_bit62141?s=09"),
]

# FaucetPay API configuration
FAUCETPAY_API_KEY = "eb70ce2715bea1e955fb023dda9cf9ac17b1aa759d6c1c86f4dab36495d513d8"
FAUCETPAY_SEND_URL = "https://faucetpay.io/api/v1/send"
FAUCETPAY_BALANCE_URL = "https://faucetpay.io/api/v1/getbalance"

# JSON file path
DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/tmp/data")
DATA_FILE = os.path.join(DATA_DIR, "data.json")

# Ensure the directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

# Initialize or load data.json
def load_data():
    logger.info(f"Loading data from {DATA_FILE}")
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            try:
                data = json.load(f)
                logger.info(f"Loaded data: {data}")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
                data = {}
            portalocker.unlock(f)
            return data
    logger.info("File does not exist, returning empty dict")
    return {}

# Save data to data.json with locking
def save_data(data):
    logger.info(f"Saving data to {DATA_FILE}: {data}")
    with open(DATA_FILE, 'w') as f:
        portalocker.lock(f, portalocker.LOCK_EX)
        json.dump(data, f, indent=4)
        portalocker.unlock(f)
    logger.info("Data saved successfully")

def get_user(user_id):
    data = load_data()
    return data.get(str(user_id), None)

def save_user(user_id, user_data):
    data = load_data()
    data[str(user_id)] = user_data
    save_data(data)

# Helper function to send group links
async def send_group_links(user_id, user_first_name, context):
    keyboard = [
        [InlineKeyboardButton(name, url=link)] for name, link in SOCIAL_MEDIA_LINKS
    ]
    keyboard.append([InlineKeyboardButton("Joined All Groups", callback_data=f"joined_groups_{user_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Welcome, {user_first_name}! Please join our social media groups:\n\n"
                 "After joining, click 'Joined All Groups' to proceed.",
            reply_markup=reply_markup
        )
        logger.info(f"Sent group links to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send group links to user {user_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = str(user.id)
    user_data = get_user(user_id)
    
    if not user_data:
        # First time user: Initialize with 0.0001 TRX reward for starting
        referral_code = str(uuid.uuid4())[:8]
        user_data = {
            "user_id": user_id,
            "balance": 0.0001,
            "joined_groups": False,
            "referral_code": referral_code,
            "referrals": 0,
            "last_bonus": 0.0,
            "faucetpay_email": None
        }
        save_user(user_id, user_data)
        logger.info(f"New user {user_id} joined. Initial balance: 0.0001 TRX, Referral code: {referral_code}")
    else:
        # Debug: Force a save to ensure data.json is written
        logger.info(f"User {user_id} already exists, forcing save: {user_data}")
        save_user(user_id, user_data)
    
    # Handle referrals
    if context.args and len(context.args) == 1:
        referrer_id = None
        data = load_data()
        for uid, udata in data.items():
            if udata.get("referral_code") == context.args[0] and uid != user_id:
                referrer_id = uid
                break
        if referrer_id:
            referrer_data = get_user(referrer_id)
            referrer_data["referrals"] += 1
            referrer_data["balance"] += 0.0001
            save_user(referrer_id, referrer_data)
            logger.info(f"User {referrer_id} got a referral from {user_id}. New referrals: {referrer_data['referrals']}, Balance: {referrer_data['balance']}")

    # If user hasn't joined groups, send group links
    if not user_data["joined_groups"]:
        await send_group_links(user_id, user.first_name, context)
        return

    # If user has joined groups, send the welcome message with referral link
    referral_code = user_data["referral_code"]
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your bot. Use /balance to check your balance.\n"
        f"Your referral link: https://t.me/nextpip_bot?start={referral_code}"
    )
    logger.info(f"User {user_id} started the bot with referral code: {referral_code}")

# Helper function to check if user has joined groups
async def check_joined_groups(user_id, user_data, update):
    if not user_data["joined_groups"]:
        await update.message.reply_text(
            "Please join the required groups first. Use /start to get the group links."
        )
        return False
    return True

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("Please start the bot with /start first.")
        return

    if not await check_joined_groups(user_id, user_data, update):
        return

    balance = user_data["balance"]
    await update.message.reply_text(f"Your balance: {balance} TRX")
    logger.info(f"User {user_id} checked balance: {balance}")

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("Please start the bot with /start first.")
        return

    if not await check_joined_groups(user_id, user_data, update):
        return

    current_time = time.time()
    last_bonus = user_data["last_bonus"]
    cooldown = 24 * 60 * 60

    if current_time - last_bonus < cooldown:
        remaining_time = int(cooldown - (current_time - last_bonus))
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        await update.message.reply_text(
            f"You can claim your next bonus in {hours} hours and {minutes} minutes."
        )
        return

    user_data["last_bonus"] = current_time
    user_data["balance"] += 0.0001
    save_user(user_id, user_data)
    await update.message.reply_text(
        "You’ve claimed your daily bonus of 0.0001 TRX! Use /balance to check your balance."
    )
    logger.info(f"User {user_id} claimed daily bonus. New balance: {user_data['balance']}")

async def refstats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("Please start the bot with /start first.")
        return

    if not await check_joined_groups(user_id, user_data, update):
        return

    referrals = user_data["referrals"]
    referral_bonus = referrals * 0.0001
    await update.message.reply_text(
        f"Referral Stats:\n"
        f"Total Referrals: {referrals}\n"
        f"Referral Bonus Earned: {referral_bonus:.4f} TRX"
    )
    logger.info(f"User {user_id} checked referral stats: {referrals} referrals")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("Please start the bot with /start first.")
        return

    if not await check_joined_groups(user_id, user_data, update):
        return

    balance = user_data["balance"]
    if balance < 0.001:
        await update.message.reply_text("Minimum withdrawal is 0.001 TRX. Your balance is too low.")
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Please provide your FaucetPay email, e.g., /withdraw your.email@example.com")
        return

    faucetpay_email = context.args[0]
    user_data["faucetpay_email"] = faucetpay_email

    # Check faucet balance before withdrawal
    try:
        balance_payload = {
            "api_key": FAUCETPAY_API_KEY,
            "currency": "TRX"
        }
        balance_response = requests.post(FAUCETPAY_BALANCE_URL, data=balance_payload)
        balance_data = balance_response.json()
        if balance_response.status_code != 200 or balance_data.get("status") != 200:
            await update.message.reply_text("Error checking faucet balance. Please try again later.")
            logger.error(f"Failed to check faucet balance: {balance_data.get('message', 'Unknown error')}")
            return

        faucet_balance_sun = int(balance_data.get("balance", 0))
        faucet_balance_trx = faucet_balance_sun / 1000000
        if faucet_balance_trx < balance:
            await update.message.reply_text("Insufficient funds in the faucet to process your withdrawal.")
            logger.error(f"Insufficient faucet balance: {faucet_balance_trx} TRX, needed: {balance} TRX")
            return

    except Exception as e:
        await update.message.reply_text("Error checking faucet balance. Please try again.")
        logger.error(f"Error checking faucet balance for user {user_id}: {e}")
        return

    # Convert balance to sun
    amount_in_sun = int(balance * 1000000)
    payload = {
        "api_key": FAUCETPAY_API_KEY,
        "to": faucetpay_email,
        "amount": amount_in_sun,
        "currency": "TRX",
        "ip_address": "0.0.0.0"
    }
    try:
        response = requests.post(FAUCETPAY_SEND_URL, data=payload)
        response_data = response.json()
        if response.status_code == 200 and response_data.get("status") == 200:
            user_data["balance"] = 0.0
            save_user(user_id, user_data)
            payout_id = response_data.get("payout_id")
            await update.message.reply_text(
                f"Withdrawal of {balance} TRX to {faucetpay_email} successful! Payout ID: {payout_id}\n"
                f"Your balance is now 0.0 TRX."
            )
            logger.info(f"User {user_id} withdrew {balance} TRX to {faucetpay_email}. Payout ID: {payout_id}")
        else:
            error_message = response_data.get("message", "Unknown error")
            await update.message.reply_text(f"Withdrawal failed: {error_message}. Please try again or check your email.")
            logger.error(f"Withdrawal failed for user {user_id}: {response.text}")
    except Exception as e:
        await update.message.reply_text("Error processing withdrawal. Please try again.")
        logger.error(f"Error in withdrawal for user {user_id}: {e}")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        user_id = str(member.id)
        user_data = get_user(user_id)
        if not user_data:
            referral_code = str(uuid.uuid4())[:8]
            user_data = {
                "user_id": user_id,
                "balance": 0.0,
                "joined_groups": False,
                "referral_code": referral_code,
                "referrals": 0,
                "last_bonus": 0.0,
                "faucetpay_email": None
            }
            save_user(user_id, user_data)
            logger.info(f"New user {user_id} joined group. Referral code: {referral_code}")

        # Send group links to new member
        await send_group_links(user_id, member.first_name, context)

async def handle_joined_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = str(query.data.split("_")[-1])
    user = query.from_user

    user_data = get_user(user_id)
    if not user_data["joined_groups"]:
        user_data["joined_groups"] = True
        save_user(user_id, user_data)
        await query.message.reply_text(
            "Thank you for joining the groups! Use /balance to check your balance."
        )
        logger.info(f"User {user_id} marked as joined groups.")
    else:
        await query.message.reply_text("You’ve already verified your group membership.")

async def debug_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    await update.message.reply_text(f"Current data: {data}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error: {context.error}")

def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("bonus", bonus))
    application.add_handler(CommandHandler("refstats", refstats))
    application.add_handler(CommandHandler("withdraw", withdraw))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(CallbackQueryHandler(handle_joined_groups, pattern="joined_groups_.*"))
    application.add_handler(CommandHandler("debugdata", debug_data))
    application.add_error_handler(error_handler)

    logger.info(f"Starting bot with polling...")
    application.run_polling()

if __name__ == "__main__":
    main()