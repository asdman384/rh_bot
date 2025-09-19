import asyncio
import io
import logging
from functools import wraps
from typing import Optional, List

import cv2
import numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from tg.bot_config import BotConfig

class AdvancedTelegramBot:
    """Расширенный Telegram бот с конфигурацией и контролем доступа"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.token = config.get('telegram.bot_token')
        self.application = Application.builder().token(self.token).build()
        self.current_image: Optional[np.ndarray] = None
        
        # Настройка логирования
        self._setup_logging()
        
        # Настройка обработчиков команд
        self._setup_handlers()
    
    def _setup_logging(self):
        """Настройка логирования"""
        log_level = getattr(logging, self.config.get('logging.level', 'INFO'))
        log_file = self.config.get('logging.file', 'bot.log')
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def require_access(self, admin_only: bool = False):
        """Декоратор для проверки прав доступа к команде"""
        def decorator(func):
            @wraps(func)
            async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
                user_id = update.effective_user.id
                
                # Проверяем общий доступ
                if not self.config.is_user_allowed(user_id):
                    await update.message.reply_text("❌ У вас нет доступа к этому боту")
                    return
                
                # Проверяем админские права если нужно
                if admin_only and not self.config.is_admin(user_id):
                    await update.message.reply_text("❌ Эта команда доступна только администраторам")
                    return
                
                return await func(self, update, context)
            return wrapper
        return decorator
    
    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        enabled_commands = self.config.get('commands.enabled', [])
        admin_commands = self.config.get('commands.admin_only', [])
        
        # Словарь команд с их обработчиками
        commands = {
            'start': (self.start_command, False),
            'help': (self.help_command, False),
            'screenshot': (self.screenshot_command, False),
            'live': (self.live_command, False),
            'status': (self.status_command, True),
            'ping': (self.ping_command, False),
            'window': (self.window_command, True),
            'config': (self.config_command, True)
        }
        
        # Добавляем только включенные команды
        for cmd_name, (handler, default_admin) in commands.items():
            if cmd_name in enabled_commands:
                admin_only = cmd_name in admin_commands or default_admin
                decorated_handler = self.require_access(admin_only)(handler)
                self.application.add_handler(CommandHandler(cmd_name, decorated_handler))
    
    @require_access()
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_name = update.effective_user.first_name or "Пользователь"
        welcome_message = (
            f"🤖 Привет, {user_name}! Добро пожаловать в бота для скриншотов!\n\n"
            "📋 Доступные команды:\n"
            "/help - показать справку\n"
            "/screenshot - получить последний скриншот\n"
            "/live - сделать новый скриншот\n"
            "/ping - проверить связь с ботом\n"
        )
        
        # Добавляем админские команды если пользователь админ
        if self.config.is_admin(update.effective_user.id):
            welcome_message += (
                "\n🔧 Админские команды:\n"
                "/status - показать статус бота\n"
                "/window - информация об окне\n"
                "/config - показать конфигурацию"
            )
        
        await update.message.reply_text(welcome_message)
    
    @require_access()
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_message = (
            "📋 Справка по командам:\n\n"
            "🖼️ **Команды для работы с изображениями:**\n"
            "/screenshot - отправить последний сохраненный скриншот\n"
            "/live - сделать новый скриншот и отправить\n\n"
            "ℹ️ **Общие команды:**\n"
            "/start - приветствие и список команд\n"
            "/help - эта справка\n"
            "/ping - проверить отклик бота\n\n"
        )
        
        if self.config.is_admin(update.effective_user.id):
            help_message += (
                "🔧 **Админские команды:**\n"
                "/status - показать подробный статус системы\n"
                "/window - информация о целевом окне\n"
                "/config - показать текущую конфигурацию\n\n"
            )
        
        help_message += "💡 Больше функций будет добавлено в будущем!"
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    @require_access()
    async def screenshot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /screenshot"""
        try:
            if self.current_image is None:
                await update.message.reply_text("❌ Нет доступного скриншота")
                return
            
            # Отправляем сообщение о начале обработки
            processing_msg = await update.message.reply_text("🔄 Подготавливаю изображение...")
            
            # Конвертируем np.ndarray в изображение для отправки
            image_bytes = self._convert_np_to_bytes(self.current_image)
            
            if image_bytes is None:
                await processing_msg.edit_text("❌ Ошибка при обработке изображения")
                return
            
            # Удаляем сообщение о обработке и отправляем изображение
            await processing_msg.delete()
            await update.message.reply_photo(
                photo=image_bytes,
                caption="📸 Последний скриншот"
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при отправке скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    @require_access()
    async def live_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для получения живого скриншота (переопределяется в наследнике)"""
        await update.message.reply_text(
            "❌ Функция живого скриншота не реализована в базовом боте.\n"
            "Используйте ScreenshotBotService для полной функциональности."
        )
    
    @require_access(admin_only=True)
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        status_message = (
            "📊 **Статус бота:**\n\n"
            f"✅ Бот активен\n"
            f"📷 Скриншот: {'Доступен' if self.current_image is not None else 'Недоступен'}\n"
            f"👥 Всего пользователей в сессии: {len(self.application.bot_data)}\n"
            f"🔧 Обработчиков команд: {len(self.application.handlers[0])}\n"
            f"⚙️ Автообновление: {'Включено' if self.config.get('screenshot.auto_update') else 'Выключено'}\n"
        )
        
        if self.current_image is not None:
            h, w = self.current_image.shape[:2]
            status_message += f"🖼️ Размер изображения: {w}x{h}\n"
        
        await update.message.reply_text(status_message, parse_mode='Markdown')
    
    @require_access()
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping"""
        await update.message.reply_text("🏓 Pong! Бот работает нормально.")
    
    @require_access(admin_only=True)
    async def window_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о целевом окне (переопределяется в наследнике)"""
        window_title = self.config.get('screenshot.window_title', 'Не задано')
        message = f"🪟 Целевое окно: {window_title}\n❓ Подробная информация недоступна в базовом боте"
        await update.message.reply_text(message)
    
    @require_access(admin_only=True)
    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущую конфигурацию"""
        config_info = (
            "⚙️ **Текущая конфигурация:**\n\n"
            f"🎯 Целевое окно: `{self.config.get('screenshot.window_title')}`\n"
            f"🔄 Интервал обновления: {self.config.get('screenshot.update_interval')}с\n"
            f"📊 Качество: {self.config.get('screenshot.quality')}\n"
            f"🤖 Автообновление: {'Вкл' if self.config.get('screenshot.auto_update') else 'Выкл'}\n"
            f"📝 Уровень логов: {self.config.get('logging.level')}\n"
        )
        
        allowed_users = self.config.get('telegram.allowed_users', [])
        if allowed_users:
            config_info += f"👥 Разрешенные пользователи: {len(allowed_users)}\n"
        else:
            config_info += "👥 Доступ: открытый\n"
        
        await update.message.reply_text(config_info, parse_mode='Markdown')
    
    def _convert_np_to_bytes(self, image: np.ndarray) -> Optional[io.BytesIO]:
        """Конвертирует np.ndarray в BytesIO для отправки через Telegram"""
        try:
            # Если изображение в формате BGR (OpenCV), конвертируем в RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            # Определяем качество сжатия из конфигурации
            quality_settings = {
                'low': [cv2.IMWRITE_JPEG_QUALITY, 60],
                'medium': [cv2.IMWRITE_JPEG_QUALITY, 80],
                'high': [cv2.IMWRITE_PNG_COMPRESSION, 3]
            }
            
            quality = self.config.get('screenshot.quality', 'high')
            
            if quality == 'high':
                # PNG для высокого качества
                success, encoded_image = cv2.imencode('.png', image_rgb, quality_settings['high'])
            else:
                # JPEG для сжатия
                success, encoded_image = cv2.imencode('.jpg', image_rgb, quality_settings.get(quality, quality_settings['medium']))
            
            if not success:
                self.logger.error("Не удалось закодировать изображение")
                return None
            
            # Создаем BytesIO объект
            image_bytes = io.BytesIO(encoded_image.tobytes())
            image_bytes.seek(0)
            
            return image_bytes
            
        except Exception as e:
            self.logger.error(f"Ошибка при конвертации изображения: {e}")
            return None
    
    def update_image(self, image: np.ndarray):
        """Обновляет текущее изображение"""
        self.current_image = image.copy()
        self.logger.info("Изображение обновлено")
    
    def add_command_handler(self, command: str, handler_func, admin_only: bool = False):
        """Добавляет новый обработчик команды"""
        decorated_handler = self.require_access(admin_only)(handler_func)
        self.application.add_handler(CommandHandler(command, decorated_handler))
        self.logger.info(f"Добавлен обработчик для команды: /{command}")
    
    async def run(self):
        """Запуск бота"""
        self.logger.info("Запуск Advanced Telegram бота...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        try:
            # Держим бота запущенным
            await asyncio.Future()  # run forever
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал остановки")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

# Пример использования
async def main():
    """Основная функция для запуска бота"""
    config = BotConfig()
    
    if config.get('telegram.bot_token') == "YOUR_BOT_TOKEN_HERE":
        print("❌ Пожалуйста, отредактируйте bot_config.json и укажите ваш BOT_TOKEN")
        return
    
    bot = AdvancedTelegramBot(config)
    
    # Пример обновления изображения
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(test_image, "Advanced Bot Test", (50, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    bot.update_image(test_image)
    
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())