import asyncio
import time
from threading import Thread

from devices.device import Device
from devices.wincap import find_window_by_title, screenshot_window_np
from tg.bot_config import BotConfig
from tg.telegram_bot import TelegramBot


class GameBotService:
    """Сервис для интеграции бота с захватом скриншотов"""

    def __init__(self, bot_token: str, window_title: str = "Rogue Hearts"):
        self.bot = TelegramBot(bot_token)
        self.window_title = window_title
        self.hwnd = None
        self.running = False
        self.screenshot_thread = None

        # Добавляем дополнительные команды
        self.bot.add_command_handler("screenshot", self._live_screenshot_command)
        self.bot.add_command_handler("window", self._window_info_command)
        self.bot.add_command_handler("close", self._close_window_command)

    async def _close_window_command(self, update, context):
        """Команда для закрытия окна"""
        try:
            device = Device("127.0.0.1", 58526)
            device.connect()
            device.force_stop_rogue_hearts()
            device.close()

            await update.message.reply_text(f"🪟 Окно '{self.window_title}' закрыто")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def _live_screenshot_command(self, update, context):
        """Команда для получения живого скриншота"""
        try:
            if not self.hwnd:
                await update.message.reply_text("❌ Окно не найдено")
                return

            # Делаем новый скриншот
            frame = screenshot_window_np(self.hwnd, client_only=True)
            self.bot.update_image(frame)

            # Отправляем обновленный скриншот
            await self.bot.screenshot_command(update, context)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка захвата: {str(e)}")

    async def _window_info_command(self, update, context):
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
        """Рабочий поток для периодического обновления скриншотов"""
        last_update = 0
        update_interval = 500.0  # Обновляем каждые 5 секунд

        while self.running:
            try:
                current_time = time.time()

                # Проверяем, нужно ли обновить скриншот
                if current_time - last_update >= update_interval:
                    if self.hwnd or self._find_window():
                        frame = screenshot_window_np(self.hwnd, client_only=True)
                        self.bot.update_image(frame)
                        last_update = current_time

                time.sleep(1)  # Проверяем каждую секунду

            except Exception as e:
                print(f"Ошибка в потоке game-бота: {e}")
                time.sleep(5)  # Ждем дольше при ошибке

    async def start(self):
        """Запуск сервиса"""
        print("🚀 Запуск сервиса game-бота...")

        # Ищем окно
        self._find_window()

        # Запускаем поток для скриншотов
        self.running = True
        self.screenshot_thread = Thread(target=self._game_bot_worker, daemon=True)
        self.screenshot_thread.start()

        # Запускаем бота
        await self.bot.run()

    def stop(self):
        """Остановка сервиса"""
        print("⏹️ Остановка сервиса game-бота...")
        self.running = False
        if self.screenshot_thread:
            self.screenshot_thread.join(timeout=5)


# Пример использования
async def main():
    """Основная функция"""
    config = BotConfig()
    service = GameBotService(
        config.get("telegram.bot_token"),
        config.get("screenshot.window_title"),
    )

    try:
        await service.start()
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    finally:
        service.stop()


if __name__ == "__main__":
    asyncio.run(main())
