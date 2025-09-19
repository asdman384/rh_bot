# Telegram Screenshot Bot

Telegram бот для отправки скриншотов с поддержкой различных команд и настроек.

## Возможности

- 📸 Отправка скриншотов по команде
- 🔄 Автоматическое обновление скриншотов в фоне
- ⚙️ Гибкая настройка через конфигурационный файл
- 🔐 Контроль доступа (разрешенные пользователи и администраторы)
- 📝 Детальное логирование
- 🎯 Интеграция с захватом окон Windows

## Установка

1. **Установите зависимости:**
   ```bash
   pip install -r telegram_requirements.txt
   ```

2. **Создайте Telegram бота:**
   - Напишите [@BotFather](https://t.me/botfather) в Telegram
   - Выполните команду `/newbot`
   - Следуйте инструкциям и получите токен бота

3. **Настройте конфигурацию:**
   ```bash
   python bot_config.py
   ```
   Это создаст файл `bot_config.json`. Отредактируйте его:
   ```json
   {
     "telegram": {
       "bot_token": "ВАШ_ТОКЕН_БОТА",
       "allowed_users": [],
       "admin_users": [ВАШ_TELEGRAM_USER_ID]
     }
   }
   ```

## Использование


### Расширенный бот с конфигурацией
```bash
python advanced_telegram_bot.py
```

### Полный сервис с захватом скриншотов
```bash
python screenshot_bot_service.py
```

## Команды бота

### Основные команды:
- `/start` - приветствие и список команд
- `/help` - справка по командам
- `/screenshot` - получить последний скриншот
- `/live` - сделать новый скриншот (только в full service)
- `/ping` - проверить работу бота

### Админские команды:
- `/status` - подробный статус системы
- `/window` - информация о целевом окне
- `/config` - показать конфигурацию

## Структура файлов

```
telegram_bot.py              # Базовый бот
advanced_telegram_bot.py     # Расширенный бот с конфигурацией
screenshot_bot_service.py    # Полный сервис с захватом скриншотов
bot_config.py               # Управление конфигурацией
telegram_requirements.txt   # Зависимости
bot_config.json            # Файл конфигурации (создается автоматически)
```

## Конфигурация

Файл `bot_config.json` содержит все настройки:

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN_HERE",
    "allowed_users": [],     // ID пользователей (пустой = все)
    "admin_users": []        // ID администраторов
  },
  "screenshot": {
    "window_title": "Rogue Hearts",  // Название окна для захвата
    "update_interval": 5.0,          // Интервал обновления (сек)
    "quality": "high",               // "high", "medium", "low"
    "auto_update": true              // Автообновление скриншотов
  },
  "commands": {
    "enabled": [                     // Включенные команды
      "start", "help", "screenshot", "live", 
      "status", "ping", "window"
    ],
    "admin_only": ["window", "status"]  // Только для админов
  },
  "logging": {
    "level": "INFO",                 // Уровень логирования
    "file": "bot.log"               // Файл логов
  }
}
```

## Интеграция с существующим кодом

Для интеграции с вашим кодом захвата скриншотов:

```python
from devices.wincap import screenshot_window_np
from advanced_telegram_bot import AdvancedTelegramBot
from bot_config import BotConfig

# Создаем бота
config = BotConfig()
bot = AdvancedTelegramBot(config)

# Получаем скриншот и отправляем в бота
frame = screenshot_window_np(hwnd, client_only=True)
bot.update_image(frame)
```

## Получение User ID

Для настройки доступа нужно знать Telegram User ID:

1. Напишите боту [@userinfobot](https://t.me/userinfobot)
2. Скопируйте ваш ID из ответа
3. Добавьте ID в конфигурацию

## Безопасность

- Никогда не публикуйте токен бота в открытом виде
- Используйте `allowed_users` для ограничения доступа
- Админские команды доступны только пользователям из `admin_users`
- Токен храните в переменных окружения или конфигурационном файле

## Расширение функциональности

Для добавления новых команд:

```python
async def my_custom_command(self, update, context):
    await update.message.reply_text("Моя новая команда!")

# Добавляем обработчик
bot.add_command_handler("custom", my_custom_command, admin_only=False)
```

## Устранение неполадок

1. **Бот не отвечает:**
   - Проверьте правильность токена
   - Убедитесь, что бот запущен
   - Проверьте интернет-соединение

2. **Скриншоты не отправляются:**
   - Проверьте, что окно найдено
   - Убедитесь, что изображение обновляется
   - Проверьте логи в `bot.log`

3. **Доступ запрещен:**
   - Проверьте настройки `allowed_users`
   - Убедитесь, что используете правильный User ID

## Логи

Все события записываются в файл `bot.log`. Для изменения уровня логирования отредактируйте `logging.level` в конфигурации.

## Поддержка

При возникновении проблем проверьте:
1. Логи в файле `bot.log`
2. Правильность конфигурации
3. Наличие всех зависимостей