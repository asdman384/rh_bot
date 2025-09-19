import json
import os
from typing import Dict, Any

class BotConfig:
    """Класс для управления конфигурацией бота"""
    
    def __init__(self, config_file: str = "bot_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла"""
        default_config = {
            "telegram": {
                "bot_token": "YOUR_BOT_TOKEN_HERE",
                "allowed_users": [],  # Список ID пользователей (пустой = все)
                "admin_users": []     # Список ID администраторов
            },
            "screenshot": {
                "window_title": "Rogue Hearts",
                "update_interval": 5.0,
                "quality": "high",    # "high", "medium", "low"
                "auto_update": True
            },
            "commands": {
                "enabled": [
                    "start", "help", "screenshot", "live", 
                    "status", "ping", "window"
                ],
                "admin_only": ["window", "status"]
            },
            "logging": {
                "level": "INFO",
                "file": "bot.log"
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # Обновляем дефолтную конфигурацию загруженными значениями
                self._update_dict(default_config, config)
                return default_config
            except Exception as e:
                print(f"Ошибка чтения конфигурации: {e}")
                return default_config
        else:
            # Создаем файл с дефолтной конфигурацией
            self.save_config(default_config)
            return default_config
    
    def _update_dict(self, base_dict: dict, update_dict: dict):
        """Рекурсивно обновляет словарь"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._update_dict(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def save_config(self, config: dict = None):
        """Сохранение конфигурации в файл"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
    
    def get(self, key_path: str, default=None):
        """Получение значения по пути (например, 'telegram.bot_token')"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value):
        """Установка значения по пути"""
        keys = key_path.split('.')
        config = self.config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
        self.save_config()
    
    def is_user_allowed(self, user_id: int) -> bool:
        """Проверка, разрешен ли пользователю доступ к боту"""
        allowed_users = self.get('telegram.allowed_users', [])
        # Если список пуст - доступ всем
        return len(allowed_users) == 0 or user_id in allowed_users
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        admin_users = self.get('telegram.admin_users', [])
        return user_id in admin_users

# Пример создания конфигурации
if __name__ == "__main__":
    config = BotConfig()
    print("Создан файл конфигурации bot_config.json")
    print("Пожалуйста, отредактируйте его и укажите ваш BOT_TOKEN")