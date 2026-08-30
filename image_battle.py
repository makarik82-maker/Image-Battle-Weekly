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
from PIL import Image

# Подавляем предупреждения о непроверенных HTTPS-запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ──────────────────────────── Настройки ───────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
GIGACHAT_CREDENTIALS = os.environ.get("GIGACHAT_CREDENTIALS") or os.environ.get("GIGACHAT_API_KEY", "")
NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
VERIFY_SSL = False

# ────────────────────── Токен GigaChat ─────────────────────────

def получить_токен_gigachat() -> str | None:
    """Получает OAuth-токен GigaChat."""
    if not GIGACHAT_CREDENTIALS:
        logger.warning("⚠️ GIGACHAT_CREDENTIALS (или GIGACHAT_API_KEY) не задан. Будет использован резервный текст.")
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
        токен = response.json().get("access_token")
        logger.info("✅ Токен GigaChat успешно получен")
        return токен
    except Exception as e:
        logger.warning(f"⚠️ Ошибка получения токена GigaChat: {e}. Используем резервный текст.")
        return None

# ──────────────────────── Генератор битвы изображений ─────────────

class ГенераторБитвы:
    def __init__(self):
        # Теперь это просто список тематик, а не пары
        self.категории = {
            'space': ['galaxy', 'nebula', 'stars', 'astronomy', 'cosmos'],
            'nature': ['mountain', 'forest', 'ocean', 'waterfall', 'landscape', 'river'],
            'animals': ['tiger', 'lion', 'eagle', 'wolf', 'bear', 'elephant'],
            'city': ['cityscape', 'architecture', 'urban', 'skyline', 'building', 'street'],
            'abstract': ['abstract', 'patterns', 'colors', 'art', 'design', 'geometric']
        }
        
        # Названия тематик для отображения
        self.названия_категорий = {
            'space': '🌌 Космос',
            'nature': '🌿 Природа',
            'animals': '🦁 Животные',
            'city': '️ Город',
            'abstract': '🎨 Абстракция'
        }

    def получить_изображение_unsplash(self, запрос, макс_попыток=3):
        """Получение случайного изображения с Unsplash по конкретному запросу"""
        for попытка in range(макс_попыток):
            try:
                logger.info(f"🔄 Попытка {попытка + 1}/{макс_попыток} для запроса: {запрос}")
                
                url = "https://api.unsplash.com/photos/random"
                params = {
                    'query': запрос,
                    'orientation': 'landscape',
                    'client_id': UNSPLASH_ACCESS_KEY
                }
                
                response = requests.get(url, params=params, timeout=15)
                
                if response.status_code == 429:
                    logger.warning("⚠️ Лимит запросов, ожидание...")
                    import time
                    time.sleep(2)
                    continue
                
                response.raise_for_status()
                данные = response.json()
                
                if not данные or 'urls' not in данные:
                    logger.warning(f"⚠️ Неверные данные ответа для {запрос}")
                    continue
                
                return {
                    'url': данные['urls']['regular'],
                    'download_url': данные['urls']['full'],
                    'author': данные['user']['name'],
                    'description': данные.get('description') or данные.get('alt_description') or запрос,
                    'query': запрос
                }
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠️ Ошибка запроса для {запрос}: {e}")
                if попытка < макс_попыток - 1:
                    import time
                    time.sleep(2)
                    continue
            except Exception as e:
                logger.warning(f"⚠️ Ошибка для {запрос}: {e}")
                continue
        
        logger.error(f"❌ Не удалось получить изображение для запроса: {запрос}")
        return None

    def получить_изображение_nasa(self):
        """Получение изображения от NASA APOD"""
        try:
            url = "https://api.nasa.gov/planetary/apod"
            params = {'api_key': NASA_API_KEY}
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            данные = response.json()
            
            if данные['media_type'] == 'image':
                return {
                    'url': данные['url'],
                    'download_url': данные['url'],
                    'author': 'NASA',
                    'description': данные.get('explanation', 'NASA Астрономическое изображение дня'),
                    'query': 'space'
                }
        except Exception as e:
            logger.warning(f"⚠️ Ошибка NASA API: {e}")
        
        return None

    def получить_резервное_изображение(self, запрос):
        """Резервное изображение через picsum.photos"""
        try:
            ширина, высота = 1080, 720
            сид = f"{запрос}-{random.randint(1, 1000)}"
            url = f"https://picsum.photos/seed/{сид}/{ширина}/{высота}"
            
            return {
                'url': url,
                'download_url': url,
                'author': 'Picsum',
                'description': f'Случайное изображение {запрос}',
                'query': запрос
            }
        except Exception as e:
            logger.warning(f"⚠️ Ошибка резервного метода: {e}")
            return None

    def сгенерировать_текст_сравнения(self, img1, img2, категория, токен_доступа):
        """Генерация сравнительного текста через GigaChat"""
        
        if not токен_доступа:
            logger.warning("⚠️ Нет токена GigaChat, используем резервный текст")
            return self._резервный_текст(img1, img2, категория)
        
        prompt = f"""Создай короткое увлекательное сравнение для двух изображений из одной тематики "{категория}" (максимум 2-3 предложения):

Изображение 1 ({img1['query']}): {img1['description'][:100]}
Изображение 2 ({img2['query']}): {img2['description'][:100]}

Стиль: дружелюбный, вовлекающий, с эмодзи. Заверши призывом к голосованию.
Ответь ТОЛЬКО текстом сравнения без дополнительных пояснений."""

        url = "https://api.giga.chat/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {токен_доступа}",
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
            
            результат = response.json()
            текст_ответа = результат["choices"][0]["message"]["content"].strip()
            
            if текст_ответа.startswith("```"):
                текст_ответа = текст_ответа.strip("`").strip()
            
            logger.info("✅ Текст сгенерирован через GigaChat")
            return текст_ответа
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка GigaChat: {e}, используем резервный текст")
            return self._резервный_текст(img1, img2, категория)

    def _резервный_текст(self, img1, img2, категория):
        """Резервный текст если GigaChat недоступен"""
        return f"🔥 Битва в категории {self.названия_категорий.get(категория, категория)}!\n\n{img1['query'].title()} vs {img2['query'].title()} — что выбираете вы? ✨\n\nГолосуйте! "

    def скачать_изображение(self, url, имя_файла):
        """Скачивание изображения"""
        try:
            logger.info(f"📥 Скачиваю: {имя_файла}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            путь = Path(имя_файла)
            путь.parent.mkdir(parents=True, exist_ok=True)
            
            with open(имя_файла, 'wb') as f:
                f.write(response.content)
            
            if путь.stat().st_size == 0:
                logger.warning(f"️ Скачанный файл пуст: {имя_файла}")
                return None
            
            logger.info(f"✅ Скачано: {имя_файла} ({путь.stat().st_size} байт)")
            return имя_файла
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания {url}: {e}")
            return None

    def оптимизировать_для_telegram(self, путь_к_файлу):
        """Оптимизирует изображение под требования Telegram (макс. 1920px)"""
        try:
            with Image.open(путь_к_файлу) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                макс_размер = 1920
                if img.width > макс_размер or img.height > макс_размер:
                    img.thumbnail((макс_размер, макс_размер), Image.Resampling.LANCZOS)
                
                img.save(путь_к_файлу, format="JPEG", quality=90)
                logger.info(f"✅ Изображение оптимизировано для Telegram: {путь_к_файлу} ({img.width}x{img.height})")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка обработки изображения {путь_к_файлу}: {e}")
            return False

    def сохранить_метаданные(self, id_опроса, категория, запрос1, запрос2, 
                            путь1, путь2, текст_сравнения):
        """Сохраняет информацию о битве для последующего анализа"""
        метаданные = {
            'poll_message_id': id_опроса,
            'chat_id': TELEGRAM_CHAT_ID,
            'category': категория,
            'category_name': self.названия_категорий.get(категория, категория),
            'img1_query': запрос1,
            'img2_query': запрос2,
            'img1_path': путь1,
            'img2_path': путь2,
            'comparison_text': текст_сравнения,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'battle_date': datetime.now(timezone.utc).strftime('%Y-%m-%d')
        }
        
        файл_метаданных = 'last_battle.json'
        with open(файл_метаданных, 'w', encoding='utf-8') as f:
            json.dump(метаданные, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Метаданные битвы сохранены в {файл_метаданных}")

    def создать_опрос(self, текст, путь1, путь2, запрос1, запрос2, категория):
        """Создание опроса в Telegram с сохранением метаданных"""
        
        if not os.path.exists(путь1) or not os.path.exists(путь2):
            logger.error("❌ Файлы изображений не найдены!")
            return False
        
        try:
            # 1. Отправляем первое фото
            url = f"{TELEGRAM_API}/sendPhoto"
            
            with open(путь1, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"🔥 {запрос1.title()}\n\n{текст}\n\n❤️ {запрос2.title()} ниже 👇",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                if not response.ok:
                    logger.error(f"❌ Ошибка Telegram API (sendPhoto 1): {response.status_code} - {response.text}")
                response.raise_for_status()
                результат1 = response.json()
            
            # 2. Отправляем второе фото
            with open(путь2, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"❤️ {запрос2.title()}",
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': результат1['result']['message_id']
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                if not response.ok:
                    logger.error(f"❌ Ошибка Telegram API (sendPhoto 2): {response.status_code} - {response.text}")
                response.raise_for_status()
                результат2 = response.json()
            
            # 3. Создаем опрос с конкретными названиями
            url_опроса = f"{TELEGRAM_API}/sendPoll"
            
            данные_опроса = {
                'chat_id': TELEGRAM_CHAT_ID,
                'question': f'🏆 {запрос1.title()} vs {запрос2.title()} — что круче?',
                'options': [f'🔥 {запрос1.title()}!', f'❤️ {запрос2.title()}!', '🤝 Оба классные!'],
                'is_anonymous': True,
                'allows_multiple_answers': False,
                'reply_to_message_id': результат2['result']['message_id']
            }
            
            response_опроса = requests.post(url_опроса, json=данные_опроса, timeout=10)
            if not response_опроса.ok:
                logger.error(f"❌ Ошибка Telegram API (sendPoll): {response_опроса.status_code} - {response_опроса.text}")
                response_опроса.raise_for_status()
            
            результат_опроса = response_опроса.json()
            id_опроса = результат_опроса['result']['message_id']
            
            logger.info("✅ Пост успешно опубликован!")
            
            # Сохраняем метаданные для будущего анализа
            self.сохранить_метаданные(
                id_опроса=id_опроса,
                category=категория,
                запрос1=запрос1,
                запрос2=запрос2,
                путь1=путь1,
                путь2=путь2,
                текст_сравнения=текст
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации в Telegram: {e}")
            import traceback
            traceback.print_exc()
            return False

    def запустить(self, токен_доступа):
        """Основной метод запуска"""
        logger.info("🎨 Запуск генерации битвы изображений...")
        
        # Выбираем одну категорию
        категория = random.choice(list(self.категории.keys()))
        запросы = self.категории[категория]
        
        # Выбираем два разных запроса из одной категории
        if len(запросы) < 2:
            logger.error(f" Недостаточно запросов в категории {категория}")
            return False
        
        запрос1, запрос2 = random.sample(запросы, 2)
        
        logger.info(f"⚔️ Битва: {self.названия_категорий.get(категория, категория)}")
        logger.info(f"🆚 {запрос1.title()} vs {запрос2.title()}")
        
        # Получаем первое изображение
        logger.info(f"\n📸 Получаю изображение 1 ({запрос1})...")
        img1 = self.получить_изображение_unsplash(запрос1)
        
        if not img1 and категория == 'space':
            logger.info("🔄 Пробую NASA API...")
            img1 = self.получить_изображение_nasa()
        
        if not img1:
            logger.info("🔄 Пробую резервный сервис...")
            img1 = self.получить_резервное_изображение(запрос1)
        
        # Получаем второе изображение
        logger.info(f"\n📸 Получаю изображение 2 ({запрос2})...")
        img2 = self.получить_изображение_unsplash(запрос2)
        
        if not img2 and категория == 'space':
            logger.info("🔄 Пробую NASA API...")
            img2 = self.получить_изображение_nasa()
        
        if not img2:
            logger.info("🔄 Пробую резервный сервис...")
            img2 = self.получить_резервное_изображение(запрос2)
        
        if not img1 or not img2:
            logger.error(f"❌ Не удалось получить изображения. img1: {img1 is not None}, img2: {img2 is not None}")
            return False
        
        logger.info(f"\n✅ Изображения успешно получены!")
        logger.info(f"📸 Изображение 1 ({запрос1}): {img1['description'][:50]}...")
        logger.info(f"📸 Изображение 2 ({запрос2}): {img2['description'][:50]}...")
        
        временная_метка = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        путь1 = f"battle_images/{временная_метка}_1.jpg"
        путь2 = f"battle_images/{временная_метка}_2.jpg"
        
        скачано1 = self.скачать_изображение(img1['download_url'], путь1)
        скачано2 = self.скачать_изображение(img2['download_url'], путь2)
        
        if not скачано1 or not скачано2:
            logger.error("❌ Не удалось скачать изображения")
            return False
        
        # Оптимизация изображений под требования Telegram
        if not self.оптимизировать_для_telegram(путь1) or not self.оптимизировать_для_telegram(путь2):
            logger.error("❌ Не удалось обработать изображения для Telegram")
            return False
        
        logger.info("\n🤖 Генерирую текст сравнения...")
        текст_сравнения = self.сгенерировать_текст_сравнения(img1, img2, категория, токен_доступа)
        logger.info(f" Текст: {текст_сравнения}")
        
        logger.info("\n📤 Публикую в Telegram...")
        успех = self.создать_опрос(текст_сравнения, путь1, путь2, запрос1, запрос2, категория)
        
        return успех

# ──────────────────────────── Главная функция ────────────────────

def main():
    logger.info("🚀 Запуск бота битвы изображений — %s", datetime.now(timezone.utc).isoformat())
    
    токен_доступа = получить_токен_gigachat()
    
    генератор = ГенераторБитвы()
    успех = генератор.запустить(токен_доступа)
    
    if успех:
        logger.info("🎉 Миссия выполнена успешно!")
        sys.exit(0)
    else:
        logger.error("🛑 Завершение работы с ошибкой.")
        sys.exit(1)


if __name__ == "__main__":
    main()
