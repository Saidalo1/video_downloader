import os
import json
import time
import requests
from urllib.parse import urlparse, parse_qs
from tqdm import tqdm
from bs4 import BeautifulSoup
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_chrome_driver():
    """Инициализация Chrome драйвера"""
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = uc.Chrome(options=options)
    return driver

def download_allstar_video(url, output_dir="downloads"):
    """
    Скачивает видео с allstar.gg используя Selenium
    
    Args:
        url (str): URL видео с allstar.gg
        output_dir (str): Директория для сохранения видео
    """
    driver = None
    try:
        # Создаём директорию для сохранения, если её нет
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Получаем ID клипа из URL
        parsed_url = urlparse(url)
        clip_id = parse_qs(parsed_url.query)['clip'][0]
        
        print(f"Загрузка страницы клипа: {url}")
        driver = get_chrome_driver()
        driver.get(url)
        
        # Ждем загрузки видео (максимум 20 секунд)
        wait = WebDriverWait(driver, 20)
        video_element = wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )
        
        # Получаем URL видео
        video_url = video_element.get_attribute('src')
        
        if not video_url:
            # Если src нет напрямую у video, ищем в source
            source_elements = video_element.find_elements(By.TAG_NAME, "source")
            if source_elements:
                video_url = source_elements[0].get_attribute('src')
            
        if not video_url:
            # Пробуем найти URL в JavaScript
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')
            for script in soup.find_all('script'):
                if script.string and 'videoUrl' in script.string:
                    matches = re.search(r'videoUrl["\']?\s*:\s*["\']([^"\']+)["\']', script.string)
                    if matches:
                        video_url = matches.group(1)
                        break
        
        if not video_url:
            # Выводим содержимое страницы для отладки
            print("HTML страницы:")
            print(driver.page_source[:1000])  # Первые 1000 символов
            raise Exception("Не удалось найти URL видео на странице")
            
        print(f"Найден URL видео: {video_url}")
        
        # Скачиваем видео
        print(f"Начинаем скачивание видео...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': url
        }
        
        video_response = requests.get(video_url, headers=headers, stream=True)
        video_response.raise_for_status()
        
        # Получаем размер файла
        total_size = int(video_response.headers.get('content-length', 0))
        
        # Формируем имя файла
        output_file = os.path.join(output_dir, f"{clip_id}.mp4")
        
        # Скачиваем файл с прогресс-баром
        with open(output_file, 'wb') as f, tqdm(
            desc=f"Скачивание {clip_id}",
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as pbar:
            for data in video_response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)
                
        print(f"Видео успешно скачано: {output_file}")
        return True
        
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        return False
    
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    # Пример использования
    urls = [
        "https://allstar.gg/clip?clip=677a96f90d620690778ecc42",
        "https://allstar.gg/clip?clip=675f6ef2a665300c7d190ad4"
    ]
    
    for url in urls:
        print(f"\nОбработка URL: {url}")
        download_allstar_video(url)
