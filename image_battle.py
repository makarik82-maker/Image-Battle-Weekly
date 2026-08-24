# scripts/image_battle.py
import os
import random
import requests
import json
from datetime import datetime
from pathlib import Path

class ImageBattleGenerator:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.unsplash_key = os.getenv('UNSPLASH_ACCESS_KEY')
        self.gigachat_key = os.getenv('GIGACHAT_API_KEY')
        self.nasa_key = os.getenv('NASA_API_KEY')
        
        self.categories = {
            'space': ['space', 'galaxy', 'stars', 'nebula'],
            'nature': ['mountain', 'forest', 'ocean', 'waterfall'],
            'animals': ['tiger', 'lion', 'eagle', 'wolf'],
            'city': ['cityscape', 'architecture', 'night city', 'skyline'],
            'abstract': ['abstract', 'patterns', 'colors', 'art']
        }
        
        self.battle_pairs = [
            ('space', 'nature'),
            ('animals', 'city'),
            ('nature', 'abstract'),
            ('space', 'animals'),
            ('city', 'nature')
        ]

    def get_unsplash_image(self, category):
        """Получение случайного изображения с Unsplash"""
        query = random.choice(self.categories.get(category, [category]))
        
        url = "https://api.unsplash.com/photos/random"
        params = {
            'query': query,
            'orientation': 'landscape',
            'client_id': self.unsplash_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                'url': data['urls']['regular'],
                'download_url': data['urls']['full'],
                'author': data['user']['name'],
                'description': data.get('description', query),
                'category': category
            }
        except Exception as e:
            print(f"Error fetching from Unsplash: {e}")
            return None

    def get_nasa_image(self):
        """Получение изображения от NASA APOD"""
        url = "https://api.nasa.gov/planetary/apod"
        params = {'api_key': self.nasa_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['media_type'] == 'image':
                return {
                    'url': data['url'],
                    'download_url': data['url'],
                    'author': 'NASA',
                    'description': data.get('explanation', ''),
                    'category': 'space'
                }
        except Exception as e:
            print(f"Error fetching from NASA: {e}")
        
        return None

    def generate_comparison_text(self, img1, img2):
        """Генерация сравнительного текста через GigaChat"""
        
        prompt = f"""
Создай короткое увлекательное сравнение для двух изображений (максимум 3 предложения):

Изображение 1 ({img1['category']}): {img1['description'][:100]}
Изображение 2 ({img2['category']}): {img2['description'][:100]}

Стиль: дружелюбный, вовлекающий, с эмодзи. Заверши вопросом для голосования.
Пример: "Оба явления потрясающи! 🔥 Сияние — это танец солнечных частиц, а Млечный Путь — наш галактический дом. ✨ Что выбираете вы?"
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
            print(f"Error with GigaChat: {e}")
            # Fallback текст
            return f"🔥 Битва категорий: {img1['category'].upper()} vs {img2['category'].upper()}! ✨\n\n{img1['description'][:80]}...\nпротив\n{img2['description'][:80]}...\n\nГолосуйте! 👇"

    def download_image(self, url, filename):
        """Скачивание изображения"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            return filename
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None

    def create_poll(self, text, img1_path, img2_path):
        """Создание опроса в Telegram с фото"""
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMediaGroup"
        
        # Отправляем два фото как альбом
        media = [
            {
                "type": "photo",
                "media": f"attach://{os.path.basename(img1_path)}",
                "caption": "🔥 Вариант 1",
                "parse_mode": "Markdown"
            },
            {
                "type": "photo", 
                "media": f"attach://{os.path.basename(img2_path)}",
                "caption": "❤️ Вариант 2",
                "parse_mode": "Markdown"
            }
        ]
        
        try:
            with open(img1_path, 'rb') as f1, open(img2_path, 'rb') as f2:
                files = {
                    os.path.basename(img1_path): f1,
                    os.path.basename(img2_path): f2
                }
                
                data = {
                    'chat_id': self.chat_id,
                    'media': json.dumps(media)
                }
                
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                
                # Отправляем текст с опросом
                poll_url = f"https://api.telegram.org/bot{self.telegram_token}/sendPoll"
                poll_data = {
                    'chat_id': self.chat_id,
                    'question': '🏆 Какое изображение круче?',
                    'options': json.dumps(['🔥 Первое!', '❤️ Второе!', '🤝 Оба классные!']),
                    'is_anonymous': False,
                    'allows_multiple_answers': False,
                    'reply_to_message_id': result[0]['message_id'] if result else None
                }
                
                # Добавляем описание
                if text:
                    caption_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                    caption_data = {
                        'chat_id': self.chat_id,
                        'text': text,
                        'reply_to_message_id': result[0]['message_id'] if result else None,
                        'parse_mode': 'Markdown'
                    }
                    requests.post(caption_url, json=caption_data, timeout=10)
                
                poll_response = requests.post(poll_url, json=poll_data, timeout=10)
                poll_response.raise_for_status()
                
                print("✅ Post successfully published!")
                return True
                
        except Exception as e:
            print(f"Error posting to Telegram: {e}")
            return False

    def run(self):
        """Основной метод запуска"""
        print("🎨 Starting Image Battle generation...")
        
        # Выбираем случайную пару категорий
        cat1, cat2 = random.choice(self.battle_pairs)
        print(f"⚔️ Battle: {cat1.upper()} vs {cat2.upper()}")
        
        # Получаем изображения
        img1 = self.get_unsplash_image(cat1)
        img2 = self.get_unsplash_image(cat2)
        
        # Если одно не получилось, пробуем NASA для space
        if not img1 and cat1 == 'space':
            img1 = self.get_nasa_image()
        if not img2 and cat2 == 'space':
            img2 = self.get_nasa_image()
        
        if not img1 or not img2:
            print("❌ Failed to fetch images")
            return False
        
        print(f"📸 Image 1: {img1['description'][:50]}...")
        print(f"📸 Image 2: {img2['description'][:50]}...")
        
        # Скачиваем изображения
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        img1_path = f"battle_images/{timestamp}_1.jpg"
        img2_path = f"battle_images/{timestamp}_2.jpg"
        
        self.download_image(img1['download_url'], img1_path)
        self.download_image(img2['download_url'], img2_path)
        
        # Генерируем текст
        print("🤖 Generating comparison text...")
        comparison_text = self.generate_comparison_text(img1, img2)
        print(f"📝 Text: {comparison_text}")
        
        # Публикуем
        print(" Publishing to Telegram...")
        success = self.create_poll(comparison_text, img1_path, img2_path)
        
        return success

if __name__ == "__main__":
    generator = ImageBattleGenerator()
    generator.run()
