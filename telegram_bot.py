import io
import json
import os
import logging
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PENDING_FILE = os.path.join(DATA_DIR, "pending_clips.json")
pending_clips = {}
pending_actions = {}


def load_pending():
    global pending_clips
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            pending_clips = json.load(f)
    return pending_clips


def save_pending():
    os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending_clips, f, indent=2, ensure_ascii=False)


async def send_uploaded_message(clip_info, first_gif=None, last_gif=None, original_description=""):
    from telegram import Bot

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    original_title = clip_info.get("original_title", "")
    channel = clip_info.get("channel", "")
    url = clip_info.get("youtube_url", "")
    privacy = clip_info.get("privacy", "private")
    video_id = clip_info.get("youtube_video_id", "")

    desc_trunc = (original_description or "").strip().replace("\n", " ")[:220]

    caption = (
        f"\U0001F4FA YUKLENDI ({privacy})\n"
        f"\U0001F517 {url}\n\n"
        f"\U0001F3AC Başlık: {original_title}\n"
        f"\U0001F4E1 Kanal: {channel}\n"
    )
    if desc_trunc:
        caption += f"\n\U0001F4DD Orijinal Açıklama: {desc_trunc}..."

    keyboard = [[
        InlineKeyboardButton("\u270F\ufe0f Başlığı Değiştir", callback_data=f"rename:{video_id}"),
        InlineKeyboardButton("\U0001F5BC\ufe0f Kapağı Güncelle", callback_data=f"thumb:{video_id}"),
        InlineKeyboardButton("\U0001F680 Yayınla", callback_data=f"publish:{video_id}"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption, reply_markup=reply_markup)

    if first_gif:
        try:
            await bot.send_animation(
                chat_id=TELEGRAM_CHAT_ID,
                animation=io.BytesIO(first_gif),
                caption="\u23F1\ufe0f Ilk 10 saniye",
            )
        except Exception as e:
            logger.error(f"Ilk GIF gonderilemedi: {e}")
    if last_gif:
        try:
            await bot.send_animation(
                chat_id=TELEGRAM_CHAT_ID,
                animation=io.BytesIO(last_gif),
                caption="\u23F1\ufe0f Son 10 saniye",
            )
        except Exception as e:
            logger.error(f"Son GIF gonderilemedi: {e}")

    return True


async def notify_new_video(channel_name, title, url, thumbnail_url=None):
    from telegram import Bot

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    text = (
        f"Yeni Video!\n"
        f"Kanal: {channel_name}\n"
        f"Baslik: {title}\n"
        f"Link: {url}"
    )
    if thumbnail_url:
        try:
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=thumbnail_url, caption=text)
            return
        except Exception:
            pass
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)


def _run_upload_thread(fn, *args):
    def wrapper():
        try:
            fn(*args)
        except Exception as e:
            logger.error(f"Arka plan islemi basarisiz: {e}")
    threading.Thread(target=wrapper, daemon=True).start()


def process_video(url):
    from main import process_video as _pv
    return _pv(url)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if ":" not in data:
        return
    action, video_id = data.split(":", 1)
    chat_id = query.message.chat_id

    if action == "rename":
        pending_actions[chat_id] = {"action": "rename", "video_id": video_id}
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Yeni başlığı yazın (video: {video_id}):\n"
                 f"/iptal ile vazgecebilirsiniz.",
        )

    elif action == "thumb":
        pending_actions[chat_id] = {"action": "thumb", "video_id": video_id}
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Yeni kapak fotografini (resim) gonderin (video: {video_id}):\n"
                 f"/iptal ile vazgecebilirsiniz.",
        )

    elif action == "publish":
        from uploader import publish_video

        await context.bot.send_message(chat_id=chat_id, text="\U0001F680 Video yayinlaniyor...")
        _run_upload_thread(publish_video, video_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"\u2705 Video yayinda: https://www.youtube.com/watch?v={video_id}",
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = pending_actions.get(chat_id)
    if not state:
        return

    video_id = state["video_id"]
    action = state["action"]

    if action == "rename" and update.message.text:
        new_title = update.message.text.strip()
        if not new_title:
            return
        del pending_actions[chat_id]
        from uploader import update_video_title

        ok = update_video_title(video_id, new_title)
        if ok:
            await update.message.reply_text(
                f"\u2705 Başlık güncellendi: {new_title[:80]}"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"\U0001F517 https://www.youtube.com/watch?v={video_id}",
            )
        else:
            await update.message.reply_text("\u26A0\ufe0f Başlık güncellenemedi. Konsola bakın.")

    elif action == "thumb" and update.message.photo:
        del pending_actions[chat_id]
        file_id = update.message.photo[-1].file_id
        try:
            tg_file = await context.bot.get_file(file_id)
            thumb_bytes = await tg_file.download_as_bytearray()
        except Exception as e:
            await update.message.reply_text(f"\u26A0\ufe0f Fotoğraf okunamadi: {e}")
            return

        from uploader import set_thumbnail

        ok = set_thumbnail(video_id, bytes(thumb_bytes))
        if ok:
            await update.message.reply_text(
                f"\u2705 Kapak guncellendi: https://www.youtube.com/watch?v={video_id}"
            )
        else:
            await update.message.reply_text("\u26A0\ufe0f Kapak guncellenemedi. Konsola bakın.")

    elif update.message.text and update.message.text.strip().lower() == "/iptal":
        del pending_actions[chat_id]
        await update.message.reply_text("Vazgecildi.")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pending_actions.pop(chat_id, None)
    await update.message.reply_text("Vazgecildi.")


async def yukle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if str(chat_id) != str(TELEGRAM_CHAT_ID):
        await update.message.reply_text("\u26A0\ufe0f Yetkisiz kullanici.")
        return

    url = None
    if context.args:
        url = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        url = update.message.reply_to_message.text.strip()

    if not url:
        await update.message.reply_text(
            "Kullanim: /yukle <youtube_url>\n"
            "Ornek: /yukle https://www.youtube.com/watch?v=VIDEOID\n"
            "(Bir mesaji yanitlayarak da gonderebilirsiniz)"
        )
        return

    await update.message.reply_text("\U0001F4E4 Video yukleniyor, taslak:\n" + url)
    _run_upload_thread(process_video, url)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "YouTube Automator Bot\n\n"
        "/status - Durum\n"
        "/yukle <URL> - URL ile taslak yukle\n"
        "/iptal - Bekleyen islemi iptal et"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_pending()
    pending = [k for k, v in pending_clips.items() if v.get("status") == "pending"]
    await update.message.reply_text(f"Bekleyen clip: {len(pending)}")


def build_app():
    load_pending()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("yukle", yukle_cmd))
    app.add_handler(CommandHandler("iptal", cancel_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    return app