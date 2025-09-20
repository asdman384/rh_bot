import asyncio
import io
import logging
from typing import Optional

import cv2
import numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.current_image: Optional[np.ndarray] = None
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Команды для будущего расширения
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_message = (
            "Доступные команды:\n"
            "/help - показать справку\n"
            "/screenshot - получить текущий скриншот\n"
            "/status - показать статус бота\n"
            "/window - показать информацию о целевом окне\n"
            "/close - закрыть целевое окно\n"
            "/ping - проверить связь с ботом"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_message = (
            "/start - приветствие и список команд\n"
            "/help - эта справка\n"
            "/screenshot - отправить текущий скриншот\n"
            "/status - показать статус системы\n"
            "/window - показать информацию о целевом окне\n"
            "/close - закрыть целевое окно\n"
            "/ping - проверить отклик бота"
        )
        await update.message.reply_text(help_message)

    async def screenshot_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Обработчик команды /screenshot"""
        try:
            if self.current_image is None:
                await update.message.reply_text("❌ Нет доступного скриншота")
                return

            # Конвертируем np.ndarray в изображение для отправки
            image_bytes = self._convert_np_to_bytes(self.current_image)

            if image_bytes is None:
                await update.message.reply_text("❌ Ошибка при обработке изображения")
                return

            # Отправляем изображение
            await update.message.reply_photo(
                photo=image_bytes, caption="📸 Текущий скриншот"
            )

        except Exception as e:
            logger.error(f"Ошибка при отправке скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        status_message = (
            "📊 Статус бота:\n\n"
            f"✅ Бот активен\n"
            f"📷 Скриншот: {'Доступен' if self.current_image is not None else 'Недоступен'}\n"
            f"🔄 Обновлений: {len(self.application.handlers[0])}"
        )
        await update.message.reply_text(status_message)

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping"""
        await update.message.reply_text("🏓 Pong! Бот работает нормально.")

    def _convert_np_to_bytes(self, image: np.ndarray) -> Optional[io.BytesIO]:
        """Конвертирует np.ndarray в BytesIO для отправки через Telegram"""
        try:
            # Проверяем формат изображения
            if len(image.shape) != 3 or image.shape[2] != 3:
                logger.error(f"Неподдерживаемый формат изображения: {image.shape}")
                return None

            # Кодируем изображение в PNG (cv2.imencode работает с BGR)
            success, encoded_image = cv2.imencode(".png", image)

            if not success:
                logger.error("Не удалось закодировать изображение")
                return None

            # Создаем BytesIO объект
            image_bytes = io.BytesIO(encoded_image.tobytes())
            image_bytes.seek(0)

            return image_bytes

        except Exception as e:
            logger.error(f"Ошибка при конвертации изображения: {e}")
            return None

    def update_image(self, image: np.ndarray):
        """Обновляет текущее изображение"""
        self.current_image = image.copy()
        logger.info("Изображение обновлено")

    def add_command_handler(self, command: str, handler_func):
        """Добавляет новый обработчик команды (для будущего расширения)"""
        self.application.add_handler(CommandHandler(command, handler_func))
        logger.info(f"Добавлен обработчик для команды: /{command}")

    async def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        try:
            # Держим бота запущенным
            await asyncio.Future()  # run forever
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
