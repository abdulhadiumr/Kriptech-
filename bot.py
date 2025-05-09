# bot.py
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from utils import init_db, generate_captcha, send_ton_to_faucetpay
from config import TELEGRAM_BOT_TOKEN, REWARD_AMOUNT, MIN_WITHDRAWAL, CHANNELS

# Initialize database
init_db()

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, email, verified) VALUES (?, ?, ?, ?)", 
              (user_id, REWARD_AMOUNT, "", 0))  # Initial bonus
    conn.commit()
    conn.close()

    keyboard = [[InlineKeyboardButton("Join Channels", callback_data="join_channels")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Welcome to Free Ton Bot! You just earned a bonus of {REWARD_AMOUNT} TON for joining.\nYou must join all our channels to continue.", reply_markup=reply_markup)

# Handle button clicks
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "join_channels":
        keyboard = [InlineKeyboardButton(f"{channel['name']}", url=channel['url']) for channel in CHANNELS]
        keyboard.append(InlineKeyboardButton("I Joined All", callback_data="joined_all"))
        reply_markup = InlineKeyboardMarkup([keyboard])
        await query.message.reply_text("Join the following channels:", reply_markup=reply_markup)

    elif query.data == "joined_all":
        captcha_text, image_path = generate_captcha()
        context.user_data["captcha_text"] = captcha_text
        with open(image_path, 'rb') as photo:
            await query.message.reply_photo(photo=photo, caption="Please enter the text from this image for verification.")
        os.remove(image_path)

    elif query.data == "verified":
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text("Verification successful! Please provide your FaucetPay email to claim your TON.")

# Handle CAPTCHA input
async def handle_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "captcha_text" in context.user_data:
        user_input = update.message.text.strip()
        if user_input == context.user_data["captcha_text"]:
            context.user_data.pop("captcha_text")
            await update.message.reply_text("CAPTCHA verified! Click to proceed.", 
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Proceed", callback_data="verified")]]))
        else:
            await update.message.reply_text("Incorrect CAPTCHA. Please try again with the 'Join Channels' button.")

# Handle email input
async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    email = update.message.text.strip()
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET email = ? WHERE user_id = ?", (email, user_id))
    conn.commit()
    conn.close()
    await update.message.reply_text("Email saved! Use /withdraw to claim your TON.")

# Balance command
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    balance = result[0] if result else 0
    await update.message.reply_text(f"Your balance: {balance} TON\nMin. withdrawal is {MIN_WITHDRAWAL} TON")

# Withdraw command
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT balance, email, verified FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()

    if not result or not result[2]:
        await update.message.reply_text("Please verify by joining channels and completing CAPTCHA first!")
        return
    if not result[1]:
        await update.message.reply_text("Please provide your FaucetPay email first!")
        return

    balance, email, _ = result
    if balance < MIN_WITHDRAWAL:
        await update.message.reply_text(f"Insufficient balance. Minimum withdrawal is {MIN_WITHDRAWAL} TON.")
        return

    await update.message.reply_text(f"Let's withdraw! Send the amount of TON you wish to withdraw (max: {balance} TON)\nWithdrawing to: {email}")
    context.user_data["awaiting_withdrawal"] = True

# Handle withdrawal amount
async def handle_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_withdrawal"):
        user_id = update.effective_user.id
        try:
            amount = float(update.message.text.strip())
            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute("SELECT balance, email FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            conn.close()

            if not result or amount > result[0] or amount < MIN_WITHDRAWAL:
                await update.message.reply_text(f"Invalid amount. Max: {result[0]} TON, Min: {MIN_WITHDRAWAL} TON.")
                return

            success, message = send_ton_to_faucetpay(result[1], amount)
            if success:
                c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                conn.commit()
                await update.message.reply_text(f"Withdrawal success!\nAmount: {amount} TON\nHash: {message}\nCheck, confirm and refer more friends.")
            else:
                await update.message.reply_text(f"Withdrawal failed: {message}")
        except ValueError:
            await update.message.reply_text("Please send a valid number.")
        context.user_data.pop("awaiting_withdrawal")

# Placeholder commands
async def ref_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Referral stats coming soon!")

async def earn_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Earn more options coming soon!")

async def bonuses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bonus features coming soon!")

# Main function
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.Text & ~filters.Command, handle_captcha))
    application.add_handler(MessageHandler(filters.Regex(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$') & ~filters.Command, handle_email))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("withdraw", withdraw))
    application.add_handler(MessageHandler(filters.Text & ~filters.Command, handle_withdrawal))
    application.add_handler(CommandHandler("refstats", ref_stats))
    application.add_handler(CommandHandler("earnmore", earn_more))
    application.add_handler(CommandHandler("bonuses", bonuses))
    application.run_polling()

if __name__ == "__main__":
    main()