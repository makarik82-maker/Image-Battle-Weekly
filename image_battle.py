# scripts/image_battle.py
import os
import random
import requests
import json
from datetime import datetime
from pathlib import Path
import time

class ImageBattleGenerator:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.unsplash_key = os.getenv('UNSPLASH_ACCESS_KEY')
        self.gigachat_key = os.getenv('GIGACHAT_API_KEY')
        self.nasa_key = os.getenv('NASA_API_KEY')
        
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
                    print(f" Attempt {attempt + 1}/{max_retries} for {category}: {query}")
                    
                    url = "https://api.unsplash.com/photos/random"
                    params = {
                        'query': query,
                        'orientation': 'landscape',
                        'client_id': self.unsplash_key
                    }
                    
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 429:
                        print(f"⚠️ Rate limit, waiting...")
                        time.sleep(2)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Проверяем, что данные корректны
                    if not data or 'urls' not in data:
                        print(f"⚠️ Invalid response data for {query}")
                        continue
                    
                    return {
                        'url': data['urls']['regular'],
                        'download_url': data['urls']['full'],
                        'author': data['user']['name'],
                        'description': data.get('description') or data.get('alt_description') or query,
                        'category': category
                    }
                    
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ Request error for {query}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                except Exception as e:
                    print(f"⚠️ Error for {query}: {e}")
                    continue
        
        print(f"❌ Failed to get image for category: {category}")
        return None

    def get_nasa_image(self):
        """Получение изображения от NASA APOD"""
        try:
            url = "https://api.nasa.gov/planetary/apod"
            params = {'api_key': self.nasa_key}
            
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
            print(f"⚠️ NASA API error: {e}")
        
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
            print(f"⚠️ Fallback error: {e}")
            return None

    def generate_comparison_text(self, img1, img2):
        """Генерация сравнительного текста через GigaChat"""
        
        prompt = f"""
Создай короткое увлекательное сравнение для двух изображений (максимум 3 предложения):

Изображение 1 ({img1['category']}): {img1['description'][:100]}
Изображение 2 ({img2['category']}): {img2['description'][:100]}

Стиль: дружелюбный, вовлекающий, с эмодзи. Заверши вопросом для голосования.
"""
        
        try:
            headers = {
                'Authorization': f'Bearer {self.gigachat_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                "model": "GigaChat",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200
            }
            
            response = requests.post(
                "https://gigachat.ru/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=15
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            print(f"⚠️ GigaChat error: {e}")
            # Fallback текст
            return f"🔥 Битва: {img1['category'].upper()} vs {img2['category'].upper()}! ✨\n\nГолосуйте за лучшее изображение! 👇"

    def download_image(self, url, filename):
        """Скачивание изображения"""
        try:
            print(f"️ Downloading: {filename}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            # Проверяем, что файл не пустой
            if path.stat().st_size == 0:
                print(f"⚠️ Downloaded file is empty: {filename}")
                return None
            
            print(f"✅ Downloaded: {filename} ({path.stat().st_size} bytes)")
            return filename
        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
            return None

    def create_poll(self, text, img1_path, img2_path):
        """Создание опроса в Telegram"""
        
        if not os.path.exists(img1_path) or not os.path.exists(img2_path):
            print("❌ Image files not found!")
            return False
        
        try:
            # Отправляем первое фото
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
            
            with open(img1_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': self.chat_id,
                    'caption': f"🔥 ВАРИАНТ 1\n\n{text}\n\n❤️ ВАРИАНТ 2 ниже 👇",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                result1 = response.json()
            
            # Отправляем второе фото
            with open(img2_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': self.chat_id,
                    'caption': '❤️ ВАРИАНТ 2',
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': result1['result']['message_id']
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                result2 = response.json()
            
            # Создаем опрос
            poll_url = f"https://api.telegram.org/bot{self.telegram_token}/sendPoll"
            poll_data = {
                'chat_id': self.chat_id,
                'question': '🏆 Какое изображение круче?',
                'options': json.dumps(['🔥 Первое!', '❤️ Второе!', '🤝 Оба классные!']),
                'is_anonymous': False,
                'allows_multiple_answers': False,
                'reply_to_message_id': result2['result']['message_id']
            }
            
            poll_response = requests.post(poll_url, json=poll_data, timeout=10)
            poll_response.raise_for_status()
            
            print("✅ Post successfully published!")
            return True
            
        except Exception as e:
            print(f"❌ Error posting to Telegram: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self):
        """Основной метод запуска"""
        print(" Starting Image Battle generation...")
        
        # Выбираем случайную пару категорий
        cat1, cat2 = random.choice(self.battle_pairs)
        print(f"⚔️ Battle: {cat1.upper()} vs {cat2.upper()}")
        
        # Получаем изображения с повторными попытками
        print(f"\n📸 Fetching image 1 ({cat1})...")
        img1 = self.get_unsplash_image(cat1)
        
        # Если не получилось, пробуем NASA для space
        if not img1 and cat1 == 'space':
            print("🔄 Trying NASA API...")
            img1 = self.get_nasa_image()
        
        # Fallback на picsum
        if not img1:
            print("🔄 Trying fallback service...")
            img1 = self.get_fallback_image(cat1)
        
        print(f"\n📸 Fetching image 2 ({cat2})...")
        img2 = self.get_unsplash_image(cat2)
        
        if not img2 and cat2 == 'space':
            print("🔄 Trying NASA API...")
            img2 = self.get_nasa_image()
        
        if not img2:
            print("🔄 Trying fallback service...")
            img2 = self.get_fallback_image(cat2)
        
        # Проверяем, что изображения получены
        if not img1 or not img2:
            print(f"❌ Failed to fetch images. img1: {img1 is not None}, img2: {img2 is not None}")
            return False
        
        print(f"\n✅ Images fetched successfully!")
        print(f"📸 Image 1: {img1['description'][:50]}...")
        print(f"📸 Image 2: {img2['description'][:50]}...")
        
        # Скачиваем изображения
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        img1_path = f"battle_images/{timestamp}_1.jpg"
        img2_path = f"battle_images/{timestamp}_2.jpg"
        
        downloaded1 = self.download_image(img1['download_url'], img1_path)
        downloaded2 = self.download_image(img2['download_url'], img2_path)
        
        if not downloaded1 or not downloaded2:
            print(" Failed to download images")
            return False
        
        # Генерируем текст
        print("\n Generating comparison text...")
        comparison_text = self.generate_comparison_text(img1, img2)
        print(f"📝 Text: {comparison_text}")
        
        # Публикуем
        print("\n📤 Publishing to Telegram...")
        success = self.create_poll(comparison_text, img1_path, img2_path)
        
        return success

if __name__ == "__main__":
    generator = ImageBattleGenerator()
    success = generator.run()
    exit(0 if success else 1)
