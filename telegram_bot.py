import io
import os
import json
import threading
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PENDING_FILE = os.path.join(DATA_DIR, "pending_clips.json")
pending_clips = {}


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


async def notify_new_video(channel_name, title, url, thumbnail_url=None):
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    text = (
        f"Yeni Video!\n"
        f"Kanal: {channel_name}\n"
        f"Baslik: {title}\n"
        f"Link: {url}"
    )

    keyboard = [[
        InlineKeyboardButton("Isle", callback_data=f"process:{url}"),
        InlineKeyboardButton("Atla", callback_data=f"skip:{url}"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if thumbnail_url:
        try:
            await bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=thumbnail_url,
                caption=text,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        reply_markup=reply_markup,
    )


async def send_preview(clip_id, video_bytes, clip_info):
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    title = clip_info.get("title", "Video")
    channel = clip_info.get("channel", "")
    intro_end = clip_info.get("intro_end", 0)
    original_url = clip_info.get("original_url", "")

    caption = (
        f"ONAY BEKLIYOR\n\n"
        f"Baslik: {title}\n"
        f"Kanal: {channel}\n"
        f"Intro kesildi: {intro_end:.0f}s\n"
        f"Orijinal: {original_url}"
    )

    keyboard = [[
        InlineKeyboardButton("Onayla - Taslak Yukle", callback_data=f"approve:{clip_id}"),
        InlineKeyboardButton("Reddet - Sil", callback_data=f"reject:{clip_id}"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        size_mb = len(video_bytes) / (1024 * 1024)
        if size_mb > 50:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"{caption}\n\nDosya boyutu: {size_mb:.1f} MB (50MB limiti astigindan video gonderilemedi)",
                reply_markup=reply_markup,
            )
            return

        video_file = InputFile(io.BytesIO(video_bytes), filename="preview.mp4")
        await bot.send_video(
            chat_id=TELEGRAM_CHAT_ID,
            video=video_file,
            caption=caption,
            reply_markup=reply_markup,
            supports_streaming=True,
        )
    except Exception as e:
        logger.error(f"Preview gonderilemedi: {e}")
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{caption}\n\nPreview gonderilemedi: {e}",
            reply_markup=reply_markup,
        )


async def send_uploaded_message(clip_info):
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    title = clip_info.get("title", "")
    channel = clip_info.get("channel", "")
    url = clip_info.get("youtube_url", "")
    privacy = clip_info.get("privacy", "taslak/private")

    text = (
        f"TASLAK OLARAK YUKLENDI\n\n"
        f"Baslik: {title}\n"
        f"Kanal: {channel}\n"
        f"Gizlilik: {privacy}\n"
        f"Link: {url}\n\n"
        f"Yayinlamak icin YouTube Studio'yu kontrol et."
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)


def handle_approve_sync(clip_id):
    if clip_id in pending_clips:
        pending_clips[clip_id]["status"] = "approved"
        save_pending()
        return pending_clips[clip_id]
    return None


def handle_reject_sync(clip_id):
    if clip_id in pending_clips:
        pending_clips[clip_id]["status"] = "rejected"
        save_pending()
        clip_path = pending_clips[clip_id].get("video_path")
        if clip_path and os.path.exists(clip_path):
            os.remove(clip_path)
        return pending_clips[clip_id]
    return None


def _upload_approved(clip_id):
    from uploader import upload_clip
    from telegram import Bot

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    clip = pending_clips.get(clip_id)
    if not clip:
        _send_result(bot, clip_id, None, "Clip bulunamadi")
        return

    video_path = clip.get("video_path")
    if not video_path or not os.path.exists(video_path):
        _send_result(bot, clip_id, None, "Video dosyasi bulunamadi")
        return

    with open(video_path, "rb") as f:
        mp4_bytes = f.read()

    thumbnail_path = clip.get("thumbnail_path")
    thumbnail_bytes = None
    if thumbnail_path and os.path.exists(thumbnail_path):
        with open(thumbnail_path, "rb") as t:
            thumbnail_bytes = t.read()

    video_id, url = upload_clip(
        mp4_bytes=mp4_bytes,
        info=clip,
        thumbnail_bytes=thumbnail_bytes,
    )

    if video_id:
        clip["status"] = "uploaded"
        clip["youtube_url"] = url
        save_pending()
        result_msg = f"TASLAK YUKLENDI\n{url}"
    else:
        result_msg = "Yukleme basarisiz. Konsol ciktisini kontrol edin."
    _send_result(bot, clip_id, video_id, result_msg)


def _send_result(bot, clip_id, video_id, message):
    try:
        import asyncio
        asyncio.run(bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"Clip: {clip_id}\n{message}",
        ))
    except Exception as e:
        logger.error(f"Yukleme sonucu gonderilemedi: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(":", 1)
    if len(parts) != 2:
        return

    action, clip_id = parts

    if action == "approve":
        result = handle_approve_sync(clip_id)
        if result:
            await query.edit_message_caption(
                caption=f"ONAYLANDI\n\n{query.message.caption or ''}",
            )
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Video onaylandi! YouTube'a taslak olarak yukleniyor...",
            )
            threading.Thread(
                target=_upload_approved,
                args=(clip_id,),
                daemon=True,
            ).start()
        else:
            await query.edit_message_caption(
                caption=f"Bulunamadi\n\n{query.message.caption or ''}",
            )

    elif action == "reject":
        handle_reject_sync(clip_id)
        await query.edit_message_caption(
            caption=f"REDDEDILDI\n\n{query.message.caption or ''}",
        )
        await query.edit_message_reply_markup(reply_markup=None)

    elif action == "process":
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Video isleniyor (monitor modunda otomatik).",
        )

    elif action == "skip":
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Atlandi.",
        )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "YouTube Automator Bot\n\n"
        "/status - Bekleyen klipleri listele\n"
        "/check - Yeni videolari kontrol et"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_pending()
    pending = [k for k, v in pending_clips.items() if v.get("status") == "pending"]
    approved = [k for k, v in pending_clips.items() if v.get("status") == "approved"]
    await update.message.reply_text(
        f"Bekleyen: {len(pending)}\nOnaylanan: {len(approved)}"
    )


def build_app():
    load_pending()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app