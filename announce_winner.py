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

# ──────────────────────────── Настройки ──────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
VERIFY_SSL = False

# ──────────────────────── Объявление победителя ─────────────────

class ОбъявлениеПобедителя:
    def __init__(self):
        self.файл_метаданных = 'last_battle.json'
        
    def загрузить_метаданные(self) -> dict | None:
        """Загружает метаданные последней битвы"""
        if not os.path.exists(self.файл_метаданных):
            logger.error(f"❌ Файл {self.файл_метаданных} не найден!")
            logger.error("Убедитесь, что битва уже была проведена и метаданные сохранены.")
            return None
        
        try:
            with open(self.файл_метаданных, 'r', encoding='utf-8') as f:
                данные = json.load(f)
            logger.info(f"✅ Загружена битва от {данные.get('battle_date', 'неизвестно')}")
            logger.info(f"️ Категория: {данные.get('category_name', 'неизвестно')}")
            logger.info(f"🆚 {данные.get('img1_query', '').title()} vs {данные.get('img2_query', '').title()}")
            return данные
        except Exception as e:
            logger.error(f"❌ Ошибка чтения {self.файл_метаданных}: {e}")
            return None

    def завершить_опрос(self, id_сообщения: int) -> dict | None:
        """Завершает опрос через stopPoll и возвращает финальные результаты"""
        url = f"{TELEGRAM_API}/stopPoll"
        
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'message_id': id_сообщения
        }
        
        try:
            logger.info(f"🛑 Завершаю опрос (id сообщения: {id_сообщения})...")
            response = requests.post(url, json=payload, timeout=30)
            
            if not response.ok:
                данные_ошибки = response.json() if response.text else {}
                описание_ошибки = данные_ошибки.get('description', 'Неизвестная ошибка')
                
                # Если опрос уже закрыт — это не критично, продолжаем
                if 'poll has been closed' in описание_ошибки.lower() or 'already closed' in описание_ошибки.lower():
                    logger.info("ℹ️ Опрос уже был закрыт ранее, продолжаем анализ")
                    return self.получить_результаты(id_сообщения)
                
                logger.error(f"❌ Ошибка Telegram API (stopPoll): {response.status_code} - {response.text}")
                return None
            
            результат = response.json()
            if not результат.get('ok'):
                logger.error(f"❌ Ошибка закрытия опроса: {результат}")
                return None
            
            данные_опроса = результат['result']
            всего_голосов = данные_опроса.get('total_voter_count', 0)
            закрыт = данные_опроса.get('is_closed', False)
            
            logger.info(f"✅ Опрос успешно закрыт!")
            logger.info(f"📊 Статус: {'Закрыт' if закрыт else 'Открыт'} | Всего голосов: {всего_голосов}")
            
            return данные_опроса
            
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия опроса: {e}")
            return None

    def получить_результаты(self, id_сообщения: int) -> dict | None:
        """Получает результаты опроса через getPoll (резервный метод)"""
        url = f"{TELEGRAM_API}/getPoll"
        
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'message_id': id_сообщения
        }
        
        try:
            logger.info(f" Запрашиваю результаты опроса (id сообщения: {id_сообщения})...")
            response = requests.post(url, json=payload, timeout=30)
            
            if not response.ok:
                logger.error(f"❌ Ошибка Telegram API (getPoll): {response.status_code} - {response.text}")
                return None
            
            результат = response.json()
            if not результат.get('ok'):
                logger.error(f"❌ Ошибка получения опроса: {результат}")
                return None
            
            данные_опроса = результат['result']
            всего_голосов = данные_опроса.get('total_voter_count', 0)
            
            logger.info(f"✅ Получены результаты опроса")
            logger.info(f"📊 Всего голосов: {всего_голосов}")
            
            return данные_опроса
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения результатов: {e}")
            return None

    def определить_победителя(self, данные_опроса: dict, запрос1: str, запрос2: str) -> dict:
        """Анализирует результаты и определяет победителя"""
        всего_голосов = данные_опроса.get('total_voter_count', 0)
        варианты = данные_опроса.get('options', [])
        
        if len(варианты) < 3:
            logger.error("❌ Недостаточно вариантов в опросе")
            return None
        
        # Варианты: 0 - Первое, 1 - Второе, 2 - Оба классные
        голоса_первого = варианты[0].get('voter_count', 0)
        голоса_второго = варианты[1].get('voter_count', 0)
        голоса_обоих = варианты[2].get('voter_count', 0)
        
        # Рассчитываем проценты
        if всего_голосов > 0:
            процент_первого = round((голоса_первого / всего_голосов) * 100, 1)
            процент_второго = round((голоса_второго / всего_голосов) * 100, 1)
            процент_обоих = round((голоса_обоих / всего_голосов) * 100, 1)
        else:
            процент_первого = процент_второго = процент_обоих = 0.0
        
        # Определяем победителя
        if голоса_первого > голоса_второго:
            победитель = 'первый'
            победитель_запрос = запрос1
            проигравший_запрос = запрос2
        elif голоса_второго > голоса_первого:
            победитель = 'второй'
            победитель_запрос = запрос2
            проигравший_запрос = запрос1
        else:
            победитель = 'ничья'
            победитель_запрос = None
            проигравший_запрос = None
        
        результат = {
            'победитель': победитель,
            'победитель_запрос': победитель_запрос,
            'процент_победителя': процент_первого if победитель == 'первый' else процент_второго,
            'проигравший_запрос': проигравший_запрос,
            'процент_проигравшего': процент_второго if победитель == 'первый' else процент_первого,
            'всего_голосов': всего_голосов,
            'голоса_первого': голоса_первого,
            'голоса_второго': голоса_второго,
            'голоса_обоих': голоса_обоих,
            'процент_первого': процент_первого,
            'процент_второго': процент_второго,
            'процент_обоих': процент_обоих
        }
        
        logger.info(f" Победитель: {победитель.upper()}")
        logger.info(f"📊 Голоса: {голоса_первого} ({процент_первого}%) vs {голоса_второго} ({процент_второго}%) vs {голоса_обоих} ({процент_обоих}%) оба")
        
        return результат

    def отправить_объявление(self, результат: dict, метаданные: dict) -> bool:
        """Отправляет сообщение с итогами битвы"""
        
        запрос1 = метаданные['img1_query'].title()
        запрос2 = метаданные['img2_query'].title()
        название_категории = метаданные.get('category_name', 'Битва')
        
        # Формируем текст
        if результат['победитель'] == 'ничья':
            текст = (
                f"🏆 **ИТОГИ БИТВЫ** 🏆\n\n"
                f"🤝 **НИЧЬЯ!**\n\n"
                f"Оба изображения набрали одинаковое количество голосов!\n\n"
                f"📊 **Результаты:**\n"
                f" {запрос1}: {результат['процент_первого']}% ({результат['голоса_первого']} голосов)\n"
                f"❤️ {запрос2}: {результат['процент_второго']}% ({результат['голоса_второго']} голосов)\n"
                f"🤝 Оба классные: {результат['процент_обоих']}% ({результат['голоса_обоих']} голосов)\n\n"
                f"👥 Всего проголосовало: **{результат['всего_голосов']}**\n\n"
                f"Спасибо за участие! Ждём вас в следующей битве! 🙏"
            )
        else:
            победитель_запрос = результат['победитель_запрос'].title()
            проигравший_запрос = результат['проигравший_запрос'].title()
            
            текст = (
                f"🏆 **ИТОГИ БИТВЫ** 🏆\n\n"
                f"🎉 **{победитель_запрос}** победил **{проигравший_запрос}**!\n\n"
                f"📊 **Результаты:**\n"
                f" {запрос1}: {результат['процент_первого']}% ({результат['голоса_первого']} голосов)\n"
                f"❤️ {запрос2}: {результат['процент_второго']}% ({результат['голоса_второго']} голосов)\n"
                f"🤝 Оба классные: {результат['процент_обоих']}% ({результат['голоса_обоих']} голосов)\n\n"
                f"👥 Всего проголосовало: **{результат['всего_голосов']}**\n\n"
                f"Спасибо за ваши голоса! Ждём вас в следующей битве! 💪"
            )
        
        # Определяем фото победителя
        if результат['победитель'] == 'первый':
            путь_фото = метаданные['img1_path']
        elif результат['победитель'] == 'второй':
            путь_фото = метаданные['img2_path']
        else:
            # При ничьей отправляем оба фото
            return self.отправить_ничью(текст, метаданные)
        
        # Отправляем фото с результатами
        try:
            url = f"{TELEGRAM_API}/sendPhoto"
            
            if not os.path.exists(путь_фото):
                logger.warning(f"️ Фото победителя {путь_фото} не найдено, отправляем только текст")
                return self.отправить_текст(текст)
            
            with open(путь_фото, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': текст,
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                
                if not response.ok:
                    logger.error(f"❌ Ошибка Telegram API: {response.status_code} - {response.text}")
                    return False
                
                logger.info("✅ Итоги битвы успешно опубликованы!")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

    def отправить_ничью(self, текст: str, метаданные: dict) -> bool:
        """Отправляет сообщение о ничьей с обоими фото"""
        try:
            url = f"{TELEGRAM_API}/sendPhoto"
            
            # Отправляем первое фото
            with open(метаданные['img1_path'], 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"🔥 {метаданные['img1_query'].title()}\n\n{текст}",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
                результат1 = response.json()
            
            # Отправляем второе фото
            with open(метаданные['img2_path'], 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': f"❤️ {метаданные['img2_query'].title()}",
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': результат1['result']['message_id']
                }
                response = requests.post(url, data=data, files=files, timeout=30)
                response.raise_for_status()
            
            logger.info("✅ Итоги ничьей успешно опубликованы!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ничьей: {e}")
            return self.отправить_текст(текст)

    def отправить_текст(self, текст: str) -> bool:
        """Отправляет только текст (резервный метод)"""
        try:
            url = f"{TELEGRAM_API}/sendMessage"
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': текст,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, json=data, timeout=30)
            response.raise_for_status()
            logger.info("✅ Текстовое сообщение отправлено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки текста: {e}")
            return False

    def запустить(self) -> bool:
        """Основной метод"""
        logger.info("🚀 Запуск анализа результатов битвы...")
        
        # 1. Загружаем метаданные
        метаданные = self.загрузить_метаданные()
        if not метаданные:
            return False
        
        # 2. Получаем ID опроса
        id_сообщения = метаданные.get('poll_message_id')
        if not id_сообщения:
            logger.error("❌ poll_message_id не найден в метаданных")
            return False
        
        # 3. 🔥 ЗАКРЫВАЕМ ОПРОС (stopPoll) — это также возвращает финальные результаты
        данные_опроса = self.завершить_опрос(id_сообщения)
        
        # Если stopPoll не сработал, пробуем getPoll как резерв
        if not данные_опроса:
            logger.warning("⚠️ stopPoll не вернул данные, пробуем getPoll...")
            данные_опроса = self.получить_результаты(id_сообщения)
        
        if not данные_опроса:
            logger.error("❌ Не удалось получить результаты опроса")
            return False
        
        # 4. Анализируем результаты
        результат = self.определить_победителя(
            данные_опроса,
            метаданные['img1_query'],
            метаданные['img2_query']
        )
        
        if not результат:
            logger.error(" Не удалось определить победителя")
            return False
        
        # 5. Отправляем объявление
        успех = self.отправить_объявление(результат, метаданные)
        
        return успех

# ──────────────────────────── Главная функция ────────────────────

def main():
    logger.info("🚀 Объявление победителя — %s", datetime.now(timezone.utc).isoformat())
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")
        sys.exit(1)
    
    объявитель = ОбъявлениеПобедителя()
    успех = объявитель.запустить()
    
    if успех:
        logger.info(" Миссия выполнена успешно!")
        sys.exit(0)
    else:
        logger.error(" Завершение работы с ошибкой.")
        sys.exit(1)


if __name__ == "__main__":
    main()
