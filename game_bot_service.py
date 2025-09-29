import asyncio
import logging
import time

from threading import Thread
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
    ReplyKeyboardMarkup,
)
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot import BotRunner
from devices.device import Device
from devices.wincap import click_in_window, find_window_by_title, screenshot_window_np
from tg.bot_config import BotConfig
from tg.telegram_bot import TelegramBot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)
logger = logging.getLogger(__name__)


class GameBotService:
    """Сервис для интеграции бота с захватом скриншотов"""

    REFRESH_CALLBACK = "refresh_screenshot"

    def __init__(
        self,
        bot_token: str,
        admin_users: list = None,
        window_title: str = "Rogue Hearts",
    ):
        self.bot = TelegramBot(bot_token, admin_users)
        self.window_title = window_title
        self.hwnd = None
        self.game_bot_thread = None
        # Selected boss name passed via /start_game_bot argument
        self._selected_boss: str | None = None
        self.bot_runner: BotRunner | None = None

        # Добавляем дополнительные команды
        self.bot.add_command_handler("screenshot", self._screenshot_command)
        self.bot.add_command_handler("start_game", self._start_game)
        self.bot.add_command_handler("close_game", self._close_game)
        self.bot.add_command_handler("start_game_bot", self.start)
        self.bot.add_command_handler("stop_game_bot", self.stop)
        self.bot.add_command_handler("click", self.click)
        self.bot.add_command_handler("logs", self.logs_command)
        # Callback for refreshing screenshot
        self.bot.application.add_handler(
            CallbackQueryHandler(
                self.refresh_screenshot_callback,
                pattern=f"^{self.REFRESH_CALLBACK}$",
            )
        )

        # Зарегистрировать список команд для меню Telegram
        self.bot.set_command_list(
            [
                ("screenshot", "📷"),
                ("logs", "📝"),
                ("start_game", "🗡️"),
                ("click", "🖱️/click x y"),
                ("start_game_bot", "🤖"),
                ("help", "ℹ️"),
                ("ping", "📶"),
                ("stop_game_bot", "🛑(don't work)"),
                ("close_game", "❌"),
            ]
        )
        self.bot.welcome_message.append("/screenshot - получить текущий скриншот\n\n")
        self.bot.welcome_message.append("/start_game - запустить игру\n\n")
        self.bot.welcome_message.append("/close_game - закрыть игру\n\n")
        self.bot.welcome_message.append("/start_game_bot - запустить игровой бот\n\n")
        self.bot.welcome_message.append(
            "/stop_game_bot - остановить игровой бот (don't work)\n\n"
        )
        self.bot.welcome_message.append("/click x y - кликнуть в координаты (x,y)\n\n")
        self.bot.welcome_message.append(
            "/logs [N] - последние N строк лога (по умолчанию 30)\n\n"
        )

    async def click(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /click x y"""
        x, y = 740, 500
        if len(context.args) == 2:
            try:
                x = int(context.args[0])
                y = int(context.args[1])
            except ValueError:
                await update.message.reply_text("❌ Координаты должны быть числами.")
                return

        if not self.hwnd:
            await update.message.reply_text("❌ Окно не найдено.")
            return

        click_in_window(self.hwnd, x, y, button="left", double=False)
        await update.message.reply_text(f"✅ Кликнуто в координаты ({x}, {y})")

    async def _start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._find_window():
            await update.message.reply_text(f"🪟 '{self.window_title}' уже запущен")
            return

        try:
            # TODO: this blocks main thread
            Device.start_rogue_hearts_wsa()
            time.sleep(10)  # wait for the game to load

            if self._find_window():
                await update.message.reply_text(f"🪟 '{self.window_title}' запущен")
            else:
                await update.message.reply_text(
                    f"❌ Не удалось найти '{self.window_title}'"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def _close_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            device = Device("127.0.0.1", 58526)
            device.connect()
            device.force_stop_rogue_hearts()
            self.hwnd = None
            device.close()
            await self.stop()

            await update.message.reply_text(f"🪟 Окно '{self.window_title}' закрыто")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def _screenshot_command(self, update: Update, context):
        try:
            self._find_window()
            if not self.hwnd:
                await update.message.reply_text("❌ Окно не найдено")
                return

            frame = screenshot_window_np(self.hwnd, client_only=True)

            if frame is None:
                await update.message.reply_text("❌ Нет доступного скриншота")
                return

            image_bytes = self.bot._convert_np_to_bytes(frame)
            if image_bytes is None:
                await update.message.reply_text("❌ Ошибка при обработке изображения")
                return

            button = InlineKeyboardButton(
                text="🔄 refresh", callback_data=self.REFRESH_CALLBACK
            )
            keyboard = InlineKeyboardMarkup([[button]])

            await update.message.reply_photo(
                image_bytes, self._get_caption(), reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Ошибка при отправке скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def refresh_screenshot_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Обрабатывает нажатие кнопки обновления: редактирует сообщение новым скриншотом."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()

        try:
            frame = screenshot_window_np(self.hwnd, client_only=True)

            if frame is None:
                await update.message.reply_text("❌ Нет доступного скриншота")
                return

            image_bytes = self.bot._convert_np_to_bytes(frame)
            if image_bytes is None:
                await update.message.reply_text("❌ Ошибка при обработке изображения")
                return

            button = InlineKeyboardButton(
                text="🔄 refresh", callback_data=self.REFRESH_CALLBACK
            )
            keyboard = InlineKeyboardMarkup([[button]])

            await query.message.edit_media(
                media=InputMediaPhoto(image_bytes, self._get_caption()),
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении скриншота: {e}")
            try:
                await query.answer(text=f"Ошибка: {e}", show_alert=True)
            except Exception:
                pass

    def _find_window(self):
        """Поиск целевого окна"""
        try:
            self.hwnd = find_window_by_title(self.window_title)
            print(f"✅ Найдено окно: {self.window_title} (HWND: {self.hwnd})")
            return True
        except RuntimeError as e:
            print(f"❌ Окно не найдено: {e}")
            self.hwnd = None
            return False

    def _get_caption(self):
        is_active = self.game_bot_thread and self.game_bot_thread.is_alive()
        return (
            f"📊 {time.strftime('%H:%M:%S')} Status: game bot:{'🟢' if is_active else '🔴'} tg handlers: {len(self.bot.application.handlers[0])}\n"
            f"\nTotal time: {self.bot_runner.get_total_time() if self.bot_runner else '00:00:00'}"
            f"      Total runs: {self.bot_runner.run if self.bot_runner else 0}"
            f"\nRuns per hour: {self.bot_runner.get_runs_per_hour() if self.bot_runner else 0:.2f}"
            f"       Failed runs: {self.bot_runner.failed_runs if self.bot_runner else 0}"
        )

    def _game_bot_worker(self):
        if self._selected_boss is None:
            print("❌ Босс не выбран, запуск пропущен.")
            return

        try:
            self.bot_runner = BotRunner(self._selected_boss)
            self.bot_runner.go()

        except Exception as e:
            print(f"Ошибка в потоке game-бота: {e}")
            # C:\dev\python\game_bot_service.py:216: RuntimeWarning: coroutine 'TelegramBot.notify_admins' was never awaited
            time.sleep(1)
            asyncio.run(self.bot.notify_admins(f"Ошибка в потоке game-бота: {e}"))

    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправить последние N строк лога (stdout/stderr). По умолчанию N=30."""
        try:
            n = 30
            if context.args and len(context.args) >= 1:
                try:
                    n = max(1, min(500, int(context.args[0])))
                except ValueError:
                    pass

            if self.bot_runner is None:
                await update.message.reply_text("Bot is not running")
                return

            _log_lines = self.bot_runner.last_logs_handler.get_last_logs()
            if not _log_lines:
                await update.message.reply_text("ℹ️ Лог пуст.")
                return

            lines = list(_log_lines)[-n:]
            text = "\n".join(lines).strip()
            # Telegram имеет лимит 4096 символов на сообщение.
            if len(text) <= 4000:
                await update.message.reply_text(
                    f"📝 Последние {len(lines)} строк:\n\n{text}"
                )
            else:
                # Отправим усечённую версию, чтобы не спамить множество сообщений
                clipped = text[-3800:]
                await update.message.reply_text(
                    f"📝 Последние {len(lines)} строк (усечено):\n\n…{clipped}"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    # Программный доступ к последним строкам лога
    def get_last_logs(self, n: int = 30) -> str:
        n = max(1, min(2000, int(n)))
        lines = list(self._log_lines)[-n:]
        return "\n".join(lines).strip()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск сервиса

        Ожидает аргумент с названием босса: BossDain или BossBhalor.
        Если аргумент не указан или неверен — показывает кнопки, которые отправят
        ту же команду с нужным аргументом.
        """
        # Parse boss argument
        boss_arg = None
        if context.args and len(context.args) >= 1:
            boss_arg = context.args[0]

        valid_bosses = {
            "dain",
            "bhalor",
            "khanel",
            "delingh",
            "elvira",
        }

        if not boss_arg or boss_arg not in valid_bosses:
            # Show reply keyboard with command shortcuts
            kb = ReplyKeyboardMarkup(
                [
                    ["/start_game_bot dain", "/start_game_bot bhalor"],
                    ["/start_game_bot khanel", "/start_game_bot delingh"],
                    ["/start_game_bot elvira"],
                ],
                resize_keyboard=True,
            )
            msg = "Выберите босса для запуска бота.\nНажмите кнопку ниже:"
            await update.message.reply_text(msg, reply_markup=kb)
            return

        # Store selected boss for worker usage (если потребуется)
        self._selected_boss = boss_arg

        # Далее обычный запуск
        if self.game_bot_thread and self.game_bot_thread.is_alive():
            print("⚠️ Сервис уже запущен, повторный запуск пропущен.")
            await update.message.reply_text(
                "⚠️ Сервис уже запущен, повторный запуск пропущен."
            )
            return

        print("🚀 Запуск сервиса game-бота...")

        # Ищем окно
        self._find_window()
        if not self.hwnd:
            message = f"❌ Окно '{self.window_title}' не найдено, запуск пропущен."
            print(message)
            await update.message.reply_text(message)
            return

        # Запускаем поток для скриншотов
        self.game_bot_thread = Thread(target=self._game_bot_worker, daemon=True)
        self.game_bot_thread.start()

        await update.message.reply_text(self._get_caption())

    async def stop(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ):
        """Остановка сервиса"""
        print("⏹️ Остановка сервиса game-бота...")
        if self.game_bot_thread:
            # There is no safe way to forcibly kill a thread in Python.
            # You should implement a flag to signal the thread to exit gracefully.
            # For now, we just wait for it to finish (if possible).
            print("⏹️ Ожидание завершения потока game-бота...")
            # Optionally, set a flag here to signal the thread to stop if your worker supports it.
            self.game_bot_thread.join(timeout=5)
            self.bot_runner = None

        message = "⏹️ Сервис остановлен."
        print(message)
        if update and context:
            await update.message.reply_text(message)


# Пример использования
async def main():
    """Основная функция"""
    config = BotConfig()

    await GameBotService(
        config.get("telegram.bot_token"),
        config.get("telegram.admin_users", []),
        config.get("screenshot.window_title"),
    ).bot.run()


if __name__ == "__main__":
    asyncio.run(main())
