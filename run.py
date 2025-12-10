import sys
import logging
import threading
from config import TG_BOT_TOKEN, KRAKEN_API_KEY, KRAKEN_API_SECRET, GEMINI_API_KEY

# Налаштувати логування — показувати тільки найважливіше
logging.basicConfig(
    level=logging.WARNING,
    format='%(message)s'
)

# Тільки для бота — інформаційне логування
logger = logging.getLogger(__name__)
bot_logger = logging.getLogger('bot')
bot_logger.setLevel(logging.INFO)

def check_config():
    """Перевірити конфігурації"""
    errors = []
    
    if not TG_BOT_TOKEN:
        errors.append("❌ TG_BOT_TOKEN не встановлено")
    if not KRAKEN_API_KEY or not KRAKEN_API_SECRET:
        errors.append("❌ KRAKEN API ключі не встановлено")
    if not GEMINI_API_KEY:
        errors.append("❌ GEMINI_API_KEY не встановлено")
    
    if errors:
        for err in errors:
            logger.error(err)
        return False
    
    logger.info("✅ Конфігурації готові")
    return True

def main():
    """Запустити бота з перевірками"""
    if not check_config():
        sys.exit(1)
    
    try:
        from bot import main as run_bot
        from api_checker import schedule_daily_reset
        
        logger.info("🚀 Запуск AI Crypto Indicator Bot...")
        
        # Щоденний скид сигналів
        reset_thread = threading.Thread(target=schedule_daily_reset, daemon=True)
        reset_thread.start()
        logger.info("🔄 Daily reset scheduler запущено")
        
        # Бот в головному потоці
        run_bot()
    except KeyboardInterrupt:
        logger.info("⏹️ Бот зупинено")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Критична помилка: {type(e).__name__} - {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
