import asyncio
import time
import sys
from contextlib import redirect_stderr, redirect_stdout

from threading import Thread
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from collections import deque

from bot import start_game_bot
from bot_utils.tee_io import _TeeIO
from devices.device import Device
from devices.wincap import click_in_window, find_window_by_title, screenshot_window_np
from tg.bot_config import BotConfig
from tg.telegram_bot import TelegramBot


class GameBotService:
    """Сервис для интеграции бота с захватом скриншотов"""

    def __init__(
        self,
        bot_token: str,
        admin_users: list = None,
        window_title: str = "Rogue Hearts",
    ):
        self.bot = TelegramBot(bot_token, admin_users)
        self.window_title = window_title
        self.hwnd = None
        self.screenshot_thread = None
        # Rolling log storage for worker thread output
        self._log_lines: deque[str] = deque(maxlen=2000)
        self._stdout_tee: _TeeIO | None = None
        self._stderr_tee: _TeeIO | None = None

        # Добавляем дополнительные команды
        self.bot.add_command_handler("screenshot", self._screenshot_command)
        self.bot.add_command_handler("window", self._window_info_command)
        self.bot.add_command_handler("status", self.status_command)
        self.bot.add_command_handler("start_game", self._start_game)
        self.bot.add_command_handler("close_game", self._close_game)
        self.bot.add_command_handler("start_game_bot", self.start)
        self.bot.add_command_handler("stop_game_bot", self.stop)
        self.bot.add_command_handler("click", self.click)
        self.bot.add_command_handler("logs", self.logs_command)
        # Зарегистрировать список команд для меню Telegram
        self.bot.set_command_list(
            [
                ("screenshot", "📷"),
                ("window", "🪟"),
                ("start_game", "🗡️"),
                ("click", "🖱️/click x y"),
                ("start_game_bot", "🤖"),
                ("status", "📊"),
                ("close_game", "❌"),
                ("help", "ℹ️"),
                ("ping", "📶"),
                ("stop_game_bot", "🛑(don't work)"),
                ("logs", "📝"),
            ]
        )
        self.bot.welcome_message.append("/screenshot - получить текущий скриншот\n\n")
        self.bot.welcome_message.append("/window - получить информацию об окне\n\n")
        self.bot.welcome_message.append("/status - показать статус бота\n\n")
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

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        status_message = (
            "📊 Статус бота:\n\n"
            f"Бот активен: {self.screenshot_thread and self.screenshot_thread.is_alive()}\n"
            f"tg Обработчиков: {len(self.bot.application.handlers[0])}"
        )
        await update.message.reply_text(status_message)

    async def _start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._find_window():
            await update.message.reply_text(f"🪟 '{self.window_title}' уже запущен")
            return

        try:
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
            if not self.hwnd:
                await update.message.reply_text("❌ Окно не найдено")
                return

            frame = screenshot_window_np(self.hwnd, client_only=True)
            await self.bot.send_screenshot(frame, update, context)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка захвата: {str(e)}")

    async def _window_info_command(self, update: Update, context):
        """Информация о целевом окне"""
        try:
            self._find_window()
            if self.hwnd:
                message = f"🪟 Окно найдено: {self.window_title}\nHWND: {self.hwnd}"
            else:
                message = f"❌ Окно '{self.window_title}' не найдено"

            await update.message.reply_text(message)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

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

    def _game_bot_worker(self):
        try:
            # Prepare tee outputs so we don't lose console logs
            if self._stdout_tee is None:
                self._stdout_tee = _TeeIO(self._log_lines, sys.__stdout__)
            if self._stderr_tee is None:
                self._stderr_tee = _TeeIO(self._log_lines, sys.__stderr__, label="ERR ")

            # Redirect only within this thread's execution block.
            # Note: sys.stdout is process-wide; during this block, other threads' prints
            # will also be captured and still forwarded to the real console.
            with redirect_stdout(self._stdout_tee), redirect_stderr(self._stderr_tee):
                start_game_bot()
        except Exception as e:
            print(f"Ошибка в потоке game-бота: {e}")
            # C:\dev\python\game_bot_service.py:216: RuntimeWarning: coroutine 'TelegramBot.notify_admins' was never awaited
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

            if not self._log_lines:
                await update.message.reply_text("ℹ️ Лог пуст.")
                return

            lines = list(self._log_lines)[-n:]
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
        """Запуск сервиса"""
        if self.screenshot_thread and self.screenshot_thread.is_alive():
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
        self.screenshot_thread = Thread(target=self._game_bot_worker, daemon=True)
        self.screenshot_thread.start()

        status_message = (
            "📊 Статус бота:\n\n"
            f"Бот активен: {self.screenshot_thread and self.screenshot_thread.is_alive()}\n"
            f"tg Обработчиков: {len(self.bot.application.handlers[0])}"
        )
        await update.message.reply_text(status_message)

    async def stop(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ):
        """Остановка сервиса"""
        print("⏹️ Остановка сервиса game-бота...")
        if self.screenshot_thread:
            # There is no safe way to forcibly kill a thread in Python.
            # You should implement a flag to signal the thread to exit gracefully.
            # For now, we just wait for it to finish (if possible).
            print("⏹️ Ожидание завершения потока game-бота...")
            # Optionally, set a flag here to signal the thread to stop if your worker supports it.
            self.screenshot_thread.join(timeout=5)

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
