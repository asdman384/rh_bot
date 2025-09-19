"""
Интегрированный Telegram бот для отправки скриншотов
Работает с системой захвата экрана wincap
"""

import asyncio
import time
import threading
from typing import Optional

from devices.wincap import find_window_by_title, screenshot_window_np
from advanced_telegram_bot import AdvancedTelegramBot
from tg.bot_config import BotConfig

class IntegratedScreenshotBot(AdvancedTelegramBot):
    """Интегрированный бот с захватом скриншотов"""
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        self.window_title = config.get('screenshot.window_title', 'Rogue Hearts')
        self.update_interval = config.get('screenshot.update_interval', 5.0)
        self.auto_update = config.get('screenshot.auto_update', True)
        
        self.hwnd: Optional[int] = None
        self.running = False
        self.screenshot_thread: Optional[threading.Thread] = None
        
        # Переопределяем команды для полной функциональности
        self._override_commands()
    
    def _override_commands(self):
        """Переопределяем команды для работы с захватом экрана"""
        # Заменяем обработчик live команды
        for handler_group in self.application.handlers.values():
            for handler in handler_group[:]:  # Копируем список для безопасного изменения
                if hasattr(handler, 'callback') and hasattr(handler.callback, '__name__'):
                    if 'live_command' in handler.callback.__name__:
                        handler_group.remove(handler)
        
        # Добавляем новый обработчик
        self.add_command_handler("live", self.live_command_override, admin_only=False)
    
    async def live_command_override(self, update, context):
        """Переопределенная команда для получения живого скриншота"""
        try:
            if not self.hwnd:
                if not self._find_window():
                    await update.message.reply_text(f"❌ Окно '{self.window_title}' не найдено")
                    return
            
            # Уведомляем о начале захвата
            processing_msg = await update.message.reply_text("📸 Делаю новый скриншот...")
            
            # Делаем новый скриншот
            frame = screenshot_window_np(self.hwnd, client_only=True)
            self.update_image(frame)
            
            # Удаляем сообщение о процессе и отправляем результат
            await processing_msg.delete()
            
            # Конвертируем и отправляем
            image_bytes = self._convert_np_to_bytes(frame)
            if image_bytes is None:
                await update.message.reply_text("❌ Ошибка при обработке изображения")
                return
            
            await update.message.reply_photo(
                photo=image_bytes,
                caption="📸 Новый скриншот"
            )
            
            self.logger.info(f"Отправлен живой скриншот пользователю {update.effective_user.id}")
            
        except Exception as e:
            self.logger.error(f"Ошибка захвата живого скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка захвата: {str(e)}")
    
    async def window_command(self, update, context):
        """Переопределенная команда для информации об окне"""
        try:
            window_found = self.hwnd is not None
            
            if not window_found:
                window_found = self._find_window()
            
            if window_found:
                # Получаем дополнительную информацию об окне
                try:
                    import win32gui
                    window_rect = win32gui.GetWindowRect(self.hwnd)
                    client_rect = win32gui.GetClientRect(self.hwnd)
                    
                    message = (
                        f"🪟 **Информация об окне:**\n\n"
                        f"📝 Название: `{self.window_title}`\n"
                        f"🔧 HWND: `{self.hwnd}`\n"
                        f"📐 Размер окна: {window_rect[2] - window_rect[0]}x{window_rect[3] - window_rect[1]}\n"
                        f"📱 Клиентская область: {client_rect[2]}x{client_rect[3]}\n"
                        f"📍 Позиция: ({window_rect[0]}, {window_rect[1]})\n"
                        f"✅ Статус: Найдено и доступно"
                    )
                except Exception:
                    message = (
                        f"🪟 **Информация об окне:**\n\n"
                        f"📝 Название: `{self.window_title}`\n"
                        f"🔧 HWND: `{self.hwnd}`\n"
                        f"✅ Статус: Найдено"
                    )
            else:
                message = (
                    f"🪟 **Информация об окне:**\n\n"
                    f"📝 Целевое окно: `{self.window_title}`\n"
                    f"❌ Статус: Не найдено\n\n"
                    f"💡 Убедитесь, что окно открыто и видимо"
                )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Ошибка получения информации об окне: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def status_command(self, update, context):
        """Переопределенная команда статуса с информацией о захвате"""
        try:
            # Базовая информация
            window_status = "Найдено" if self.hwnd else "Не найдено"
            auto_update_status = "Включено" if self.auto_update and self.running else "Выключено"
            
            status_message = (
                f"📊 **Расширенный статус бота:**\n\n"
                f"✅ Бот активен\n"
                f"📷 Скриншот: {'Доступен' if self.current_image is not None else 'Недоступен'}\n"
                f"🪟 Целевое окно: {window_status}\n"
                f"🔄 Автообновление: {auto_update_status}\n"
                f"⏱️ Интервал обновления: {self.update_interval}с\n"
                f"🎯 Название окна: `{self.window_title}`\n"
            )
            
            if self.current_image is not None:
                h, w = self.current_image.shape[:2]
                status_message += f"🖼️ Размер изображения: {w}x{h}\n"
            
            if self.hwnd:
                status_message += f"🔧 HWND: `{self.hwnd}`\n"
            
            # Информация о потоке
            thread_status = "Активен" if self.screenshot_thread and self.screenshot_thread.is_alive() else "Остановлен"
            status_message += f"🧵 Поток захвата: {thread_status}\n"
            
            await update.message.reply_text(status_message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статуса: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    def _find_window(self) -> bool:
        """Поиск целевого окна"""
        try:
            self.hwnd = find_window_by_title(self.window_title)
            self.logger.info(f"Найдено окно: {self.window_title} (HWND: {self.hwnd})")
            return True
        except RuntimeError as e:
            self.logger.warning(f"Окно '{self.window_title}' не найдено: {e}")
            self.hwnd = None
            return False
    
    def _screenshot_worker(self):
        """Рабочий поток для автоматического обновления скриншотов"""
        last_update = 0
        find_window_interval = 10.0  # Ищем окно каждые 10 секунд если не найдено
        last_window_search = 0
        
        self.logger.info("Запущен поток автоматического обновления скриншотов")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Если окно не найдено, пытаемся найти его периодически
                if not self.hwnd and (current_time - last_window_search) >= find_window_interval:
                    self._find_window()
                    last_window_search = current_time
                
                # Обновляем скриншот если окно найдено и пришло время
                if self.hwnd and (current_time - last_update) >= self.update_interval:
                    try:
                        frame = screenshot_window_np(self.hwnd, client_only=True)
                        self.update_image(frame)
                        last_update = current_time
                        self.logger.debug("Скриншот автоматически обновлен")
                    except Exception as e:
                        self.logger.error(f"Ошибка автоматического захвата скриншота: {e}")
                        # Возможно окно было закрыто, сбрасываем hwnd
                        self.hwnd = None
                
                time.sleep(1)  # Проверяем каждую секунду
                
            except Exception as e:
                self.logger.error(f"Критическая ошибка в потоке скриншотов: {e}")
                time.sleep(5)  # Ждем дольше при критической ошибке
        
        self.logger.info("Поток автоматического обновления скриншотов остановлен")
    
    def start_screenshot_service(self):
        """Запуск сервиса автоматического обновления скриншотов"""
        if not self.auto_update:
            self.logger.info("Автоматическое обновление скриншотов отключено")
            return
        
        self.logger.info("Запуск сервиса автоматического обновления скриншотов...")
        
        # Ищем окно при запуске
        self._find_window()
        
        # Запускаем поток
        self.running = True
        self.screenshot_thread = threading.Thread(target=self._screenshot_worker, daemon=True)
        self.screenshot_thread.start()
        
        self.logger.info("Сервис автоматического обновления скриншотов запущен")
    
    def stop_screenshot_service(self):
        """Остановка сервиса автоматического обновления скриншотов"""
        self.logger.info("Остановка сервиса автоматического обновления скриншотов...")
        self.running = False
        
        if self.screenshot_thread and self.screenshot_thread.is_alive():
            self.screenshot_thread.join(timeout=5)
            if self.screenshot_thread.is_alive():
                self.logger.warning("Поток скриншотов не остановился вовремя")
            else:
                self.logger.info("Поток скриншотов остановлен")
    
    async def run(self):
        """Запуск бота с сервисом скриншотов"""
        self.logger.info("Запуск интегрированного Telegram Screenshot бота...")
        
        # Запускаем сервис скриншотов
        self.start_screenshot_service()
        
        try:
            # Запускаем основной бот
            await super().run()
        finally:
            # Останавливаем сервис скриншотов
            self.stop_screenshot_service()

# Функция для быстрого запуска
async def run_integrated_bot():
    """Быстрый запуск интегрированного бота"""
    config = BotConfig()
    
    # Проверяем конфигурацию
    token = config.get('telegram.bot_token')
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("❌ Не настроен токен бота!")
        print("Запустите: python setup_bot.py")
        return
    
    # Создаем и запускаем бота
    bot = IntegratedScreenshotBot(config)
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        print("🔚 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(run_integrated_bot())