import asyncio
import io
import logging
from typing import Optional, List

import cv2
import numpy as np
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Suppress noisy INFO logs from telegram and httpx libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
logging.getLogger("apscheduler.jobstores.default").setLevel(logging.WARNING)
logging.getLogger("apscheduler.job").setLevel(logging.WARNING)
logging.getLogger("_client").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class TelegramBot:
    welcome_message = [
        "Доступные команды:\n",
        "/start - приветствие и список команд\n",
        "/ping - проверить связь с ботом\n",
        "/help - показать справку\n\n",
    ]

    def __init__(self, token: str, admin_users: List[int] = None):
        self.token = token
        self.admin_users = admin_users or []
        self.application = Application.builder().token(token).build()
        # Optional: list of BotCommand to expose in Telegram's input menu
        self._commands: List[BotCommand] | None = None
        # Pre-computed filter for admin users (if any provided)
        self._admin_filter = (
            filters.User(self.admin_users) if self.admin_users else None
        )
        # Event loop reference (set on run). Needed for cross-thread notifications.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._setup_handlers()

    def _setup_handlers(self):
        self.add_command_handler("start", self.start_command)
        self.add_command_handler("help", self.start_command)
        self.add_command_handler("ping", self.ping_command)
        # Text message handler (echo) only for admins if admin list provided
        if self._admin_filter:
            self.application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & self._admin_filter,
                    self.echo_handler,
                )
            )
        else:
            # No admin list configured -> allow everyone
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo_handler)
            )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("".join(self.welcome_message))

    async def echo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (эхо)"""
        user_text = update.message.text
        await update.message.reply_text(f"🔊 Эхо: {user_text}")

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

    def add_command_handler(self, command: str, handler_func):
        # Apply admin filter if configured
        if self._admin_filter:
            self.application.add_handler(
                CommandHandler(command, handler_func, filters=self._admin_filter)
            )
        else:
            self.application.add_handler(CommandHandler(command, handler_func))
        logger.warning(f"Добавлен обработчик для команды: /{command}")

    def set_command_list(self, commands: List[tuple[str, str]]):
        self._commands = [BotCommand(cmd, desc) for cmd, desc in commands]

    async def notify_admins(self, message: str):
        """Отправляет сообщение всем администраторам из конфига"""
        if not self.admin_users:
            logger.warning("Список администраторов пуст")
            return

        for admin_id in self.admin_users:
            try:
                await self.application.bot.send_message(
                    chat_id=admin_id, text=f"🔔 Уведомление администратору:\n{message}"
                )
                logger.info(f"Сообщение отправлено администратору {admin_id}")
            except Exception as e:
                logger.error(
                    f"Ошибка отправки сообщения администратору {admin_id}: {e}"
                )

    def notify_admins_threadsafe(self, message: str):
        """Thread-safe wrapper to call notify_admins from non-async threads.

        If the bot has already started (loop stored) we schedule the coroutine
        with run_coroutine_threadsafe. If not yet started we fall back to
        creating a temporary event loop to send messages synchronously (best-effort).
        """

        async def _coro():
            await self.notify_admins(message)

        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(_coro(), self._loop)
            except Exception as e:
                logger.error(f"notify_admins_threadsafe scheduling failed: {e}")
        else:
            # Fallback (should rarely happen): run in a new loop (blocks caller)
            try:
                asyncio.run(_coro())
            except RuntimeError:
                # If already in an event loop (unlikely in thread) create new loop
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_coro())
                finally:
                    loop.close()

    async def run(self):
        """Запуск бота"""
        logger.warning("Запуск Telegram бота...")
        # Store loop for cross-thread callbacks
        self._loop = asyncio.get_running_loop()
        await self.application.initialize()
        # Apply bot commands so Telegram shows menu button with pop-up suggestions
        if self._commands:
            await self.application.bot.set_my_commands(self._commands)
        await self.application.start()
        await self.application.updater.start_polling()

        try:
            # Держим бота запущенным
            await asyncio.Future()  # run forever
        except KeyboardInterrupt:
            logger.warning("Получен сигнал остановки")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
