"""
Скрипт для быстрой настройки Telegram бота
"""

import json
import os
import sys

def setup_bot():
    """Интерактивная настройка бота"""
    print("🤖 Добро пожаловать в мастер настройки Telegram Screenshot Bot!")
    print("=" * 60)
    
    # Проверяем наличие зависимостей
    try:
        import telegram
        print("✅ Библиотека python-telegram-bot установлена")
    except ImportError:
        print("❌ Библиотека python-telegram-bot не найдена")
        print("Установите зависимости: pip install -r telegram_requirements.txt")
        return False
    
    # Проверяем наличие OpenCV
    try:
        import cv2
        print("✅ OpenCV установлен")
    except ImportError:
        print("❌ OpenCV не найден")
        print("Установите зависимости: pip install -r telegram_requirements.txt")
        return False
    
    print("\n📝 Настройка конфигурации:")
    
    # Получаем токен бота
    bot_token = input("\n🔑 Введите токен вашего Telegram бота: ").strip()
    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        print("❌ Необходимо указать действительный токен бота")
        print("Создайте бота через @BotFather в Telegram")
        return False
    
    # Получаем ID администратора
    print("\n👤 Для получения вашего Telegram User ID:")
    print("   1. Напишите боту @userinfobot")
    print("   2. Скопируйте ваш ID из ответа")
    
    admin_id = input("\n🔧 Введите ваш Telegram User ID (администратор): ").strip()
    try:
        admin_id = int(admin_id)
    except ValueError:
        print("❌ ID должен быть числом")
        return False
    
    # Настройки окна
    window_title = input("\n🪟 Введите название окна для захвата (по умолчанию 'Rogue Hearts'): ").strip()
    if not window_title:
        window_title = "Rogue Hearts"
    
    # Создаем конфигурацию
    config = {
        "telegram": {
            "bot_token": bot_token,
            "allowed_users": [],  # Пустой список = доступ всем
            "admin_users": [admin_id]
        },
        "screenshot": {
            "window_title": window_title,
            "update_interval": 5.0,
            "quality": "high",
            "auto_update": True
        },
        "commands": {
            "enabled": [
                "start", "help", "screenshot", "live", 
                "status", "ping", "window", "config"
            ],
            "admin_only": ["window", "status", "config"]
        },
        "logging": {
            "level": "INFO",
            "file": "bot.log"
        }
    }
    
    # Сохраняем конфигурацию
    try:
        with open("bot_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Конфигурация сохранена в bot_config.json")
    except Exception as e:
        print(f"\n❌ Ошибка сохранения конфигурации: {e}")
        return False
    
    # Создаем батник для запуска (Windows)
    if os.name == 'nt':
        try:
            with open("run_bot.bat", "w", encoding="utf-8") as f:
                f.write("@echo off\n")
                f.write("echo Запуск Telegram Screenshot Bot...\n")
                f.write("python screenshot_bot_service.py\n")
                f.write("pause\n")
            print("✅ Создан файл run_bot.bat для быстрого запуска")
        except Exception as e:
            print(f"⚠️ Не удалось создать bat файл: {e}")
    
    print("\n🎉 Настройка завершена!")
    print("\n📋 Следующие шаги:")
    print("1. Убедитесь, что окно с названием '" + window_title + "' открыто")
    print("2. Запустите бота одним из способов:")
    print("   - python screenshot_bot_service.py")
    print("   - run_bot.bat (если создан)")
    print("3. Напишите боту в Telegram команду /start")
    
    print("\n🔧 Полезные команды бота:")
    print("   /screenshot - получить скриншот")
    print("   /live - сделать новый скриншот")
    print("   /status - статус системы (админ)")
    print("   /help - справка")
    
    return True

def check_requirements():
    """Проверка требований к системе"""
    print("🔍 Проверка требований к системе...")
    
    # Проверяем Python версию
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        return False
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Проверяем файлы
    required_files = [
        "telegram_bot.py",
        "advanced_telegram_bot.py", 
        "screenshot_bot_service.py",
        "bot_config.py",
        "requirements.txt"
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file}")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    return True

def main():
    """Главная функция"""
    print("🔧 Мастер настройки Telegram Screenshot Bot")
    print("=" * 50)
    
    # Проверяем требования
    if not check_requirements():
        print("\n❌ Проверка требований не пройдена")
        input("\nНажмите Enter для выхода...")
        return
    
    print("\n" + "=" * 50)
    
    # Запускаем настройку
    if setup_bot():
        print("\n🚀 Готово к запуску!")
    else:
        print("\n❌ Настройка не завершена")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()