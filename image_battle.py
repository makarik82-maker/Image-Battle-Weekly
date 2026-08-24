import os
import sys
import json
import uuid
import random
import logging
import urllib3
from datetime import datetime, timezone
from pathlib import Path

import requests

# Подавляем предупреждения о непроверенных HTTPS-запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ──────────────────────────── Настройки ───────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
GIGACHAT_CREDENTIALS = os.environ.get("GIGACHAT_CREDENTIALS", "")
NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
VERIFY_SSL = False

# ─────────────────────── GigaChat Token ──────────────────────────

def get_gigachat_token() -> str | None:
    """Получает OAuth-токен GigaChat."""
    if not GIGACHAT_CREDENTIALS:
        logger.error("❌ GIGACHAT_CREDENTIALS не задан в секретах GitHub!")
        return None
    
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_CREDENTIALS}",
    }
    data = {"scope": "GIGACHAT_API_PERS"}

    try:
        response = requests.post(url, headers=headers, data=data, verify=VERIFY_SSL, timeout=30)
        response.raise_for_status()
        token = response.json().get("access_token")
        logger.info("✅ Токен GigaChat успешно получен")
        return token
    except Exception as e:
        logger.error("❌ Ошибка получения токена GigaChat: %s", e)
        return None

# ──────────────────────── Image Battle Generator ──────────────────

class ImageBattleGenerator:
    def __init__(self):
        self.categories = {
            'space': ['space', 'galaxy', 'stars', 'nebula', 'astronomy'],
            'nature': ['mountain', 'forest', 'ocean', 'waterfall', 'landscape'],
            'animals': ['tiger', 'lion', 'eagle', 'wolf', 'wildlife'],
            'city': ['cityscape', 'architecture', 'urban', 'skyline', 'building'],
            'abstract': ['abstract', 'patterns', 'colors', 'art', 'design']
        }
        
        self.battle_pairs = [
            ('space', 'nature'),
            ('animals', 'city'),
            ('nature', 'abstract'),
            ('space', 'animals'),
            ('city', 'nature')
        ]

    def get_unsplash_image(self, category, max_retries=3):
        """Получение случайного изображения с Unsplash с повторными попытками"""
        queries = self.categories.get(category, [category])
        
        for attempt in range(max_retries):
            for query in queries:
                try:
                    logger.info(f"🔄 Attempt {attempt + 1}/{max_retries} for {category}: {query}")
                    
                    url = "https://api.unsplash.com/photos/random"
                    params = {
                        'query': query,
                        'orientation': 'landscape',
                        'client_id': UNSPLASH_ACCESS_KEY
                    }
                    
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 429:
                        logger.warning("⚠️ Rate limit, waiting...")
                        import time
                        time.sleep(2)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data or 'urls' not in data:
                        logger.warning(f"⚠️ Invalid response data for {query}")
                        continue
                    
                    return {
                        'url': data['urls']['regular'],
                        'download_url': data['urls']['full'],
                        'author': data['user']['name'],
                        'description': data.get('description') or data.get('alt_description') or query,
                        'category': category
                    }
                    
                except requests.exceptions.RequestException as e:
                    logger.warning(f"️ Request error for {query}: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2)
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ Error for {query}: {e}")
                    continue
        
        logger.error(f"❌ Failed to get image for category: {category}")
        return None

    def get_nasa_image(self):
        """Получение изображения от NASA APOD"""
        try:
            url = "https://api.nasa.gov/planetary/apod"
            params = {'api_key': NASA_API_KEY}
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data['media_type'] == 'image':
                return {
                    'url': data['url'],
                    'download_url': data['url'],
                    'author': 'NASA',
                    'description': data.get('explanation', 'NASA Astronomy Picture of the Day'),
                    'category': 'space'
                }
        except Exception as e:
            logger.warning(f"⚠️ NASA API error: {e}")
        
        return None

    def get_fallback_image(self, category):
        """Fallback изображения через picsum.photos"""
        try:
            width, height = 1080, 720
            seed = f"{category}-{random.randint(1, 1000)}"
            url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
            
            return {
                'url': url,
                'download_url': url,
                'author': 'Picsum',
                'description': f'Random {category} image',
                'category': category
            }
        except Exception as e:
            logger.warning(f"️ Fallback error: {e}")
            return None

    def generate_comparison_text(self, img1, img2, access_token):
        """Генерация сравнительного текста через GigaChat"""
        
        if not access_token:
            logger.warning("⚠️ Нет токена GigaChat, используем fallback текст")
            return self._fallback_text(img1, img2)
        
        prompt = f"""Создай короткое увлекательное сравнение для двух изображений (максимум 2-3 предложения):

Изображение 1 ({img1['category']}): {img1['description'][:100]}
Изображение 2 ({img2['category']}): {img2['description'][:100]}

Стиль: дружелюбный, вовлекающий, с эмодзи. Заверши призывом к голосованию.
Ответь ТОЛЬКО текстом сравнения без дополнительных пояснений."""

        url = "https://api.giga.chat/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        
        payload = {
            "model": "GigaChat-2",
            "messages": [
                {"role": "system", "content": "Ты создаешь короткие увлекательные тексты для соцсетей."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            answer_text = result["choices"][0]["message"]["content"].strip()
            
            # Очищаем ответ от markdown-оберток
            if answer_text.startswith("```"):
                answer_text = answer_text.strip("`").strip()
            
            logger.info("✅ Текст сгенерирован через GigaChat")
            return answer_text
            
        except Exception as e:
            logger.warning(f"⚠️ GigaChat error: {e}, используем fallback")
            return self._fallback_text(img1, img2)

    def _fallback_text(self, img1, img2):
        """Fallback текст если GigaChat недоступен"""
        return f"🔥 Битва: {img1['category'].upper()} vs {img2['category'].upper()}! ✨\n\nГолосуйте за лучшее изображение! 👇"

    def download_image(self, url, filename):
        """Скачивание изображения"""
        try:
            logger.info(f"📥 Downloading: {filename}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            if path.stat().st_size == 0:
                logger.warning(f"⚠️ Downloaded file is empty: {filename}")
                return None
            
            logger.info(f"✅ Downloaded: {filename} ({path.stat().st_size} bytes)")
            return filename
        except Exception as e:
            logger.error(f" Error downloading {url}: {e}")
            return None

    def create_poll(self, text, img1_path, img2_path):
        """Создание опроса в Telegram"""
        
        if not os.path.exists(img1_path) or not os.path.exists(img2_path):
            logger.error("❌ Image files not found!")
            return False
        
        try:
            # 1. Отправляем первое фото
            url = f"{TELEGRAM_API}/sendPhoto"
            
            with open(img1_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"🔥 ВАРИАНТ 1\n\n{text}\n\n❤️ ВАРИАНТ 2 ниже 👇",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                result1 = response.json()
            
            # 2. Отправляем второе фото
            with open(img2_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': '❤️ ВАРИАНТ 2',
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': result1['result']['message_id']
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                result2 = response.json()
            
            # 3. Создаем опрос
            poll_url = f"{TELEGRAM_API}/sendPoll"
            
            # ВАЖНО: options передаем как список Python, json= сам сериализует
            poll_data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'question': '🏆 Какое изображение круче?',
                'options': ['🔥 Первое!', '❤️ Второе!', '🤝 Оба классные!'],
                'is_anonymous': False,
                'allows_multiple_answers': False,
                'reply_to_message_id': result2['result']['message_id']
            }
            
            poll_response = requests.post(poll_url, json=poll_data, timeout=10)
            
            if not poll_response.ok:
                logger.error(f"❌ Telegram API Error: {poll_response.status_code} - {poll_response.text}")
                poll_response.raise_for_status()
            
            logger.info("✅ Post successfully published!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error posting to Telegram: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self, access_token):
        """Основной метод запуска"""
        logger.info("🎨 Starting Image Battle generation...")
        
        # Выбираем случайную пару категорий
        cat1, cat2 = random.choice(self.battle_pairs)
        logger.info(f"️ Battle: {cat1.upper()} vs {cat2.upper()}")
        
        # Получаем изображения с повторными попытками
        logger.info(f"\n📸 Fetching image 1 ({cat1})...")
        img1 = self.get_unsplash_image(cat1)
        
        if not img1 and cat1 == 'space':
            logger.info("🔄 Trying NASA API...")
            img1 = self.get_nasa_image()
        
        if not img1:
            logger.info("🔄 Trying fallback service...")
            img1 = self.get_fallback_image(cat1)
        
        logger.info(f"\n📸 Fetching image 2 ({cat2})...")
        img2 = self.get_unsplash_image(cat2)
        
        if not img2 and cat2 == 'space':
            logger.info(" Trying NASA API...")
            img2 = self.get_nasa_image()
        
        if not img2:
            logger.info("🔄 Trying fallback service...")
            img2 = self.get_fallback_image(cat2)
        
        if not img1 or not img2:
            logger.error(f" Failed to fetch images. img1: {img1 is not None}, img2: {img2 is not None}")
            return False
        
        logger.info(f"\n✅ Images fetched successfully!")
        logger.info(f"📸 Image 1: {img1['description'][:50]}...")
        logger.info(f"📸 Image 2: {img2['description'][:50]}...")
        
        # Скачиваем изображения
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        img1_path = f"battle_images/{timestamp}_1.jpg"
        img2_path = f"battle_images/{timestamp}_2.jpg"
        
        downloaded1 = self.download_image(img1['download_url'], img1_path)
        downloaded2 = self.download_image(img2['download_url'], img2_path)
        
        if not downloaded1 or not downloaded2:
            logger.error("❌ Failed to download images")
            return False
        
        # Генерируем текст
        logger.info("\n🤖 Generating comparison text...")
        comparison_text = self.generate_comparison_text(img1, img2, access_token)
        logger.info(f"📝 Text: {comparison_text}")
        
        # Публикуем
        logger.info("\n📤 Publishing to Telegram...")
        success = self.create_poll(comparison_text, img1_path, img2_path)
        
        return success

# ──────────────────────────── Main ─────────────────────────────────

def main():
    logger.info("🚀 Запуск Image Battle Bot — %s", datetime.now(timezone.utc).isoformat())
    
    # 1. Получаем токен GigaChat
    access_token = get_gigachat_token()
    if not access_token:
        logger.warning("⚠️ Продолжаем работу без токена GigaChat (будет использован fallback текст)")
    
    # 2. Создаем генератор и запускаем
    generator = ImageBattleGenerator()
    success = generator.run(access_token)
    
    if success:
        logger.info("🎉 Миссия выполнена успешно!")
        sys.exit(0)
    else:
        logger.error("🛑 Завершение работы с ошибкой.")
        sys.exit(1)


if __name__ == "__main__":
    main()
