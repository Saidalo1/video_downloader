import os
import re
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import aiohttp
import aiofiles

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
TOKEN = "6031079365:AAGhNXxFXoKGdBo6ufvhzvJiCPEjLk0Twk0"

# Настройка путей
CACHE_DIR = "/app/cache"

# Создаем директорию для кэша если её нет
os.makedirs(CACHE_DIR, exist_ok=True)

# Кэш для хранения информации о скачанных видео
# Структура: {clip_id: (file_path, timestamp)}
video_cache: Dict[str, Tuple[str, datetime]] = {}

# Время жизни кэша (в часах)
CACHE_LIFETIME = 24

async def is_allstar_url(url: str) -> Optional[str]:
    """Проверяет, является ли URL ссылкой на allstar.gg клип"""
    try:
        parsed_url = urlparse(url)
        if 'allstar.gg' in parsed_url.netloc and 'clip' in parsed_url.path:
            clip_id = parse_qs(parsed_url.query).get('clip', [None])[0]
            return clip_id
    except Exception:
        pass
    return None

async def get_video_url(url: str) -> str:
    """Получает URL видео с помощью Selenium"""
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = None
    try:
        driver = uc.Chrome(options=options)
        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        video_element = wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )
        
        video_url = video_element.get_attribute('src')
        if not video_url:
            source_elements = video_element.find_elements(By.TAG_NAME, "source")
            if source_elements:
                video_url = source_elements[0].get_attribute('src')
        
        if not video_url:
            raise Exception("Не удалось найти URL видео")
            
        return video_url
    
    finally:
        if driver:
            driver.quit()

async def download_video(video_url: str, output_path: str):
    """Скачивает видео по URL"""
    async with aiohttp.ClientSession() as session:
        async with session.get(video_url) as response:
            if response.status == 200:
                async with aiofiles.open(output_path, mode='wb') as f:
                    await f.write(await response.read())
            else:
                raise Exception(f"Ошибка при скачивании: {response.status}")

async def clean_old_cache():
    """Очищает устаревшие файлы из кэша"""
    current_time = datetime.now()
    expired_clips = []
    
    for clip_id, (file_path, timestamp) in video_cache.items():
        if current_time - timestamp > timedelta(hours=CACHE_LIFETIME):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                expired_clips.append(clip_id)
            except Exception as e:
                logger.error(f"Ошибка при удалении файла {file_path}: {e}")
    
    for clip_id in expired_clips:
        del video_cache[clip_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Отправь мне ссылку на клип с allstar.gg, и я скачаю его для тебя."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Просто отправь мне ссылку на клип с allstar.gg в формате:\n"
        "https://allstar.gg/clip?clip=ID_КЛИПА\n"
        "И я скачаю его для тебя!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений"""
    message = update.message
    
    # Проверяем, есть ли в сообщении ссылка на allstar.gg
    clip_id = await is_allstar_url(message.text)
    if not clip_id:
        return
    
    try:
        # Отправляем начальное сообщение
        status_message = await message.reply_text(
            "🎮 Получена ссылка на клип!\n"
            "⏳ Начинаю обработку..."
        )
        
        # Проверяем кэш
        if clip_id in video_cache:
            file_path, _ = video_cache[clip_id]
            if os.path.exists(file_path):
                await status_message.edit_text("⚡️ Клип найден в кэше, отправляю...")
                await message.reply_video(
                    video=open(file_path, 'rb'),
                    caption="Видео из кэша ⚡️"
                )
                await status_message.delete()
                return
        
        # Создаем временный файл для сохранения видео
        cache_file = os.path.join(CACHE_DIR, f"{clip_id}.mp4")
        
        # Получаем URL видео
        await status_message.edit_text(
            "🔍 Получаю информацию о видео...\n"
            "🕒 Это может занять несколько секунд"
        )
        video_url = await get_video_url(message.text)
        
        # Скачиваем видео
        await status_message.edit_text(
            "📥 Скачиваю видео...\n"
            "⏳ Пожалуйста, подождите"
        )
        await message.chat.send_action(ChatAction.UPLOAD_VIDEO)
        await download_video(video_url, cache_file)
        
        # Отправляем видео
        await status_message.edit_text("📤 Отправляю видео...")
        await message.reply_video(
            video=open(cache_file, 'rb'),
            caption="Вот ваше видео! 🎮"
        )
        
        # Удаляем статусное сообщение
        await status_message.delete()
        
        # Сохраняем в кэш
        video_cache[clip_id] = (cache_file, datetime.now())
        
        # Очищаем старый кэш
        await clean_old_cache()
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        error_text = (
            "❌ Извините, произошла ошибка при скачивании видео.\n"
            "🔄 Пожалуйста, попробуйте позже или проверьте правильность ссылки."
        )
        if 'status_message' in locals():
            await status_message.edit_text(error_text)
        else:
            await message.reply_text(error_text)

def main():
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
