import os
import time
import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Для статичного аналізу (Pylance) — покажи типове ім'я, але не впливає на виконання
if TYPE_CHECKING:
    import schedule  # type: ignore

try:
    import schedule  # type: ignore
except Exception:
    schedule = None
    logger.warning("schedule module not available; cleanup will run in simple loop")

def cleanup_files():
    """Видаляє лишні файли"""
    for file in os.listdir('.'):
        if file.endswith('.png') and file.startswith('chart_'):
            try:
                os.remove(file)
                logger.info(f"🗑️ Видалено: {file}")
            except Exception as e:
                logger.error(f"❌ Не вдалося видалити {file}: {e}")

def start_cleanup_scheduler():
    """Запускає планувальник чистки кожну годину"""
    if schedule:
        schedule.every(1).hour.do(cleanup_files)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        # fallback: простий цикл кожну годину
        while True:
            cleanup_files()
            time.sleep(3600)

if __name__ == '__main__':
    start_cleanup_scheduler()
