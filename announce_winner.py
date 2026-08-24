import os
import sys
import json
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

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
VERIFY_SSL = False

# ──────────────────────── Winner Announcer ───────────────────────

class WinnerAnnouncer:
    def __init__(self):
        self.metadata_file = 'last_battle.json'
        
    def load_battle_metadata(self) -> dict | None:
        """Загружает metadata последней битвы"""
        if not os.path.exists(self.metadata_file):
            logger.error(f"❌ Файл {self.metadata_file} не найден!")
            logger.error("Убедитесь, что битва уже была проведена и metadata сохранена.")
            return None
        
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"✅ Загружена битва от {data.get('battle_date', 'неизвестно')}")
            logger.info(f"⚔️ Категории: {data.get('img1_category', '').upper()} vs {data.get('img2_category', '').upper()}")
            return data
        except Exception as e:
            logger.error(f"❌ Ошибка чтения {self.metadata_file}: {e}")
            return None

    def get_poll_results(self, poll_message_id: int) -> dict | None:
        """Получает результаты опроса через getPoll"""
        url = f"{TELEGRAM_API}/getPoll"
        
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'message_id': poll_message_id
        }
        
        try:
            logger.info(f"📊 Запрашиваю результаты опроса (message_id: {poll_message_id})...")
            response = requests.post(url, json=payload, timeout=30)
            
            if not response.ok:
                logger.error(f"❌ Telegram API Error: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            if not result.get('ok'):
                logger.error(f"❌ Ошибка получения опроса: {result}")
                return None
            
            poll_data = result['result']
            total_votes = poll_data.get('total_voter_count', 0)
            
            logger.info(f"✅ Получены результаты опроса")
            logger.info(f"📊 Всего голосов: {total_votes}")
            
            return poll_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения результатов: {e}")
            return None

    def calculate_winner(self, poll_data: dict, img1_category: str, img2_category: str) -> dict:
        """Анализирует результаты и определяет победителя"""
        total_votes = poll_data.get('total_voter_count', 0)
        options = poll_data.get('options', [])
        
        if len(options) < 3:
            logger.error("❌ Недостаточно вариантов в опросе")
            return None
        
        # Варианты: 0 - Первое, 1 - Второе, 2 - Оба классные
        first_votes = options[0].get('voter_count', 0)
        second_votes = options[1].get('voter_count', 0)
        both_votes = options[2].get('voter_count', 0)
        
        # Рассчитываем проценты
        if total_votes > 0:
            first_percent = round((first_votes / total_votes) * 100, 1)
            second_percent = round((second_votes / total_votes) * 100, 1)
            both_percent = round((both_votes / total_votes) * 100, 1)
        else:
            first_percent = second_percent = both_percent = 0.0
        
        # Определяем победителя
        if first_votes > second_votes:
            winner = 'first'
            winner_category = img1_category
            loser_category = img2_category
        elif second_votes > first_votes:
            winner = 'second'
            winner_category = img2_category
            loser_category = img1_category
        else:
            winner = 'tie'
            winner_category = None
            loser_category = None
        
        result = {
            'winner': winner,
            'winner_category': winner_category,
            'winner_percent': first_percent if winner == 'first' else second_percent,
            'loser_category': loser_category,
            'loser_percent': second_percent if winner == 'first' else first_percent,
            'total_votes': total_votes,
            'first_votes': first_votes,
            'second_votes': second_votes,
            'both_votes': both_votes,
            'first_percent': first_percent,
            'second_percent': second_percent,
            'both_percent': both_percent
        }
        
        logger.info(f"🏆 Победитель: {winner.upper()}")
        logger.info(f"📊 Голоса: {first_votes} ({first_percent}%) vs {second_votes} ({second_percent}%) vs {both_votes} ({both_percent}%) оба")
        
        return result

    def send_winner_announcement(self, result: dict, metadata: dict) -> bool:
        """Отправляет сообщение с итогами битвы"""
        
        img1_cat = metadata['img1_category'].upper()
        img2_cat = metadata['img2_category'].upper()
        
        # Формируем текст
        if result['winner'] == 'tie':
            text = (
                f"🏆 **ИТОГИ БИТВЫ** 🏆\n\n"
                f"🤝 **НИЧЬЯ!**\n\n"
                f"Оба изображения набрали одинаковое количество голосов!\n\n"
                f"📊 **Результаты:**\n"
                f"🔥 {img1_cat}: {result['first_percent']}% ({result['first_votes']} голосов)\n"
                f"❤️ {img2_cat}: {result['second_percent']}% ({result['second_votes']} голосов)\n"
                f"🤝 Оба классные: {result['both_percent']}% ({result['both_votes']} голосов)\n\n"
                f"👥 Всего проголосовало: **{result['total_votes']}**\n\n"
                f"Спасибо за участие! Ждём вас в следующей битве! 🙏"
            )
        else:
            winner_cat = result['winner_category'].upper()
            loser_cat = result['loser_category'].upper()
            winner_pct = result['winner_percent']
            loser_pct = result['loser_percent']
            
            text = (
                f" **ИТОГИ БИТВЫ** \n\n"
                f"🎉 **{winner_cat}** победил **{loser_cat}**!\n\n"
                f"📊 **Результаты:**\n"
                f"🔥 {img1_cat}: {result['first_percent']}% ({result['first_votes']} голосов)\n"
                f"❤️ {img2_cat}: {result['second_percent']}% ({result['second_votes']} голосов)\n"
                f"🤝 Оба классные: {result['both_percent']}% ({result['both_votes']} голосов)\n\n"
                f"👥 Всего проголосовало: **{result['total_votes']}**\n\n"
                f"Спасибо за ваши голоса! Ждём вас в следующей битве! 💪"
            )
        
        # Определяем фото победителя
        if result['winner'] == 'first':
            winner_photo_path = metadata['img1_path']
        elif result['winner'] == 'second':
            winner_photo_path = metadata['img2_path']
        else:
            # При ничьей отправляем оба фото
            return self.send_tie_announcement(text, metadata)
        
        # Отправляем фото с результатами
        try:
            url = f"{TELEGRAM_API}/sendPhoto"
            
            if not os.path.exists(winner_photo_path):
                logger.warning(f"️ Фото победителя {winner_photo_path} не найдено, отправляем только текст")
                return self.send_text_only(text)
            
            with open(winner_photo_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': text,
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                
                if not response.ok:
                    logger.error(f"❌ Telegram API Error: {response.status_code} - {response.text}")
                    return False
                
                logger.info("✅ Итоги битвы успешно опубликованы!")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

    def send_tie_announcement(self, text: str, metadata: dict) -> bool:
        """Отправляет сообщение о ничьей с обоими фото"""
        try:
            url = f"{TELEGRAM_API}/sendPhoto"
            
            # Отправляем первое фото
            with open(metadata['img1_path'], 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"🔥 {metadata['img1_category'].upper()}\n\n{text}",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                result1 = response.json()
            
            # Отправляем второе фото
            with open(metadata['img2_path'], 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"❤️ {metadata['img2_category'].upper()}",
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': result1['result']['message_id']
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
            
            logger.info("✅ Итоги ничьей успешно опубликованы!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ничьей: {e}")
            return self.send_text_only(text)

    def send_text_only(self, text: str) -> bool:
        """Отправляет только текст (fallback)"""
        try:
            url = f"{TELEGRAM_API}/sendMessage"
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, json=data, timeout=30)
            response.raise_for_status()
            logger.info("✅ Текстовое сообщение отправлено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки текста: {e}")
            return False

    def run(self) -> bool:
        """Основной метод"""
        logger.info(" Запуск анализа результатов битвы...")
        
        # 1. Загружаем metadata
        metadata = self.load_battle_metadata()
        if not metadata:
            return False
        
        # 2. Получаем результаты опроса
        poll_message_id = metadata.get('poll_message_id')
        if not poll_message_id:
            logger.error("❌ poll_message_id не найден в metadata")
            return False
        
        poll_data = self.get_poll_results(poll_message_id)
        if not poll_data:
            logger.error(" Не удалось получить результаты опроса")
            return False
        
        # 3. Анализируем результаты
        result = self.calculate_winner(
            poll_data,
            metadata['img1_category'],
            metadata['img2_category']
        )
        
        if not result:
            logger.error("❌ Не удалось определить победителя")
            return False
        
        # 4. Отправляем объявление
        success = self.send_winner_announcement(result, metadata)
        
        return success

# ──────────────────────────── Main ─────────────────────────────────

def main():
    logger.info("🚀 Winner Announcer — %s", datetime.now(timezone.utc).isoformat())
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")
        sys.exit(1)
    
    announcer = WinnerAnnouncer()
    success = announcer.run()
    
    if success:
        logger.info("🎉 Миссия выполнена успешно!")
        sys.exit(0)
    else:
        logger.error("🛑 Завершение работы с ошибкой.")
        sys.exit(1)


if __name__ == "__main__":
    main()
