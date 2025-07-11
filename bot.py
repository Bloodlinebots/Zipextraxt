import os
import zipfile
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatAction
from telegram.error import Forbidden

# ======== CONFIG ========
TOKEN = os.environ["TOKEN"]
EXTRACT_FOLDER = "extracted_files"
user_channel_map = {}  # user_id: channel_id
# ========================

logging.basicConfig(level=logging.INFO)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send /connect <channel_id> to link a channel.\nThen send me a ZIP of images/videos to post to your channel."
    )

# ===== /connect =====
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: /connect <channel_id>")
        return

    channel_id = context.args[0]
    try:
        chat_admins = await context.bot.get_chat_administrators(channel_id)
        bot_id = context.bot.id
        if any(admin.user.id == bot_id for admin in chat_admins):
            user_channel_map[update.effective_user.id] = channel_id
            await update.message.reply_text(f"✅ Connected to {channel_id}")
        else:
            await update.message.reply_text("❌ Bot is not admin in that channel.")
    except Forbidden:
        await update.message.reply_text("❌ Cannot access this channel. Make sure the bot is added and made admin.")
    except Exception as e:
        logging.error(str(e))
        await update.message.reply_text("❌ Failed to connect. Check channel ID or bot permissions.")

# ===== ZIP Handler =====
async def handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    channel_id = user_channel_map.get(user_id)

    if not channel_id:
        await update.message.reply_text("❌ First use /connect <channel_id> to set your channel.")
        return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".zip"):
        await update.message.reply_text("❌ Please send a valid ZIP file.")
        return

    status_msg = await update.message.reply_text("📦 Extracting ZIP...")

    zip_path = os.path.join(EXTRACT_FOLDER, f"{user_id}_media.zip")
    await doc.get_file().download_to_drive(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(EXTRACT_FOLDER)
    except Exception as e:
        logging.error(f"ZIP extraction failed for @{username}: {e}")
        await context.bot.send_message(
            chat_id=channel_id,
            text=f"❌ Error extracting ZIP sent by @{username}"
        )
        await status_msg.edit_text("❌ ZIP extraction failed. No media posted.")
        return

    # Filter media files
    media_files = [
        f for f in os.listdir(EXTRACT_FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".mp4", ".mkv", ".mov"))
    ]
    total = len(media_files)

    if total == 0:
        await status_msg.edit_text("❌ No supported media files found in ZIP.")
        return

    await status_msg.edit_text(f"🧮 Found {total} media files in ZIP.")

    # Post one-by-one
    sent = 0
    for i, file in enumerate(media_files, start=1):
        try:
            await status_msg.edit_text(f"📤 Posting media {i} of {total}...")
            filepath = os.path.join(EXTRACT_FOLDER, file)
            if file.lower().endswith((".jpg", ".jpeg", ".png")):
                await context.bot.send_photo(channel_id, photo=open(filepath, "rb"))
            else:
                await context.bot.send_video(channel_id, video=open(filepath, "rb"))
            sent += 1
        except Exception as e:
            logging.warning(f"Failed to send {file}: {e}")

    await status_msg.edit_text(f"✅ All {sent} media files posted successfully to {channel_id}.")

    # Cleanup
    for f in os.listdir(EXTRACT_FOLDER):
        os.remove(os.path.join(EXTRACT_FOLDER, f))


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(MessageHandler(filters.Document.ZIP, handle_zip))

    print("🤖 Bot is running...")
    app.run_polling()
