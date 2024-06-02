from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply

from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

from helper.utils import progress_for_pyrogram, convert, humanbytes
from helper.database import db

from asyncio import sleep
from PIL import Image
import os, time


@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB.")

    try:
        await message.reply_text(
            text=f"**Please enter the new filename.**\n\n**Old filename:** `{filename}`",
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(
            text=f"**Please enter the new filename.**\n\n**Old filename:** `{filename}`",
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply):
        new_name = message.text
        await message.delete()
        msg = await client.get_messages(message.chat.id, reply_message.id)
        file = msg.reply_to_message
        media = getattr(file, file.media.value)

        if "." not in new_name:
            extn = media.file_name.rsplit('.', 1)[-1] if "." in media.file_name else "mkv"
            new_name = f"{new_name}.{extn}"
        
        await reply_message.delete()

        buttons = [[InlineKeyboardButton("📁 Document", callback_data=f"upload_document|{new_name}")]]
        if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
            buttons.append([InlineKeyboardButton("🎥 Video", callback_data=f"upload_video|{new_name}")])
        elif file.media == MessageMediaType.AUDIO:
            buttons.append([InlineKeyboardButton("🎵 Audio", callback_data=f"upload_audio|{new_name}")])
        
        await message.reply(
            text=f"**Select the output file type**\n**• File name:** ```{new_name}```",
            reply_to_message_id=file.id,
            reply_markup=InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):
    callback_data = update.data.split("|")
    upload_type = callback_data[0]
    new_name = callback_data[1]
    file_path = f"downloads/{new_name}"
    file = update.message.reply_to_message

    ms = await update.message.edit("Trying to download...")

    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Download started...", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(str(e))

    duration = 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
    except:
        pass

    ph_path = None
    user_id = int(update.message.chat.id)
    media = getattr(file, file.media.value)
    c_caption = await db.get_caption(user_id)
    c_thumb = await db.get_thumbnail(user_id)

    caption = f"**{new_name}**"
    if c_caption:
        try:
            caption = c_caption.format(filename=new_name, filesize=humanbytes(media.file_size), duration=convert(duration))
        except Exception as e:
            return await ms.edit(text=f"Your caption error: {e}")

    if media.thumbs or c_thumb:
        thumb_id = c_thumb if c_thumb else media.thumbs[0].file_id
        ph_path = await bot.download_media(thumb_id)
        with Image.open(ph_path) as img:
            img.convert("RGB").resize((320, 320)).save(ph_path, "JPEG")

    await ms.edit("Trying to upload...")

    try:
        if upload_type == "upload_document":
            await bot.send_document(
                user_id,
                document=file_path,
                thumb=ph_path,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=("Upload started...", ms, time.time())
            )
        elif upload_type == "upload_video":
            await bot.send_video(
                user_id,
                video=file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("Upload started...", ms, time.time())
            )
        elif upload_type == "upload_audio":
            await bot.send_audio(
                user_id,
                audio=file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("Upload started...", ms, time.time())
            )
    except Exception as e:
        await ms.edit(f"Error: {e}")
    finally:
        os.remove(file_path)
        if ph_path:
            os.remove(ph_path)