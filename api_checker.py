import logging
import time
import ccxt
import requests
import schedule
from datetime import datetime
from config import KRAKEN_API_KEY, KRAKEN_API_SECRET, GEMINI_API_KEY
from db import reset_daily_signals

logger = logging.getLogger(__name__)

class APIChecker:
    def __init__(self):
        self.last_check = {}
        self.check_interval = 1 * 24 * 3600  # 1 день у секундах (замість 5 днів)
    
    def check_bybit(self):
        """Перевіряє Bybit API"""
        try:
            exchange = ccxt.kraken({
                'apiKey': KRAKEN_API_KEY,
                'secret': KRAKEN_API_SECRET,
                'enableRateLimit': True
            })
            
            # Спроба отримати баланс
            balance = exchange.fetch_balance()
            logger.info(f"✅ Bybit API: Working | Balance: {len(balance)} currencies")
            return True
        except Exception as e:
            logger.error(f"❌ Bybit API: FAILED - {type(e).__name__} - {str(e)}")
            return False
    
    def check_gemini(self):
        """Перевіряє Gemini API"""
        try:
            headers = {'Content-Type': 'application/json'}
            payload = {
                'contents': [{'parts': [{'text': 'test'}]}]
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                logger.info(f"✅ Gemini API: Working")
                return True
            else:
                logger.error(f"❌ Gemini API: FAILED - HTTP {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Gemini API: FAILED - {type(e).__name__} - {str(e)}")
            return False
    
    def check_all(self):
        """Перевіряє всі API кожні 5 днів"""
        now = time.time()
        
        for api_name in ['bybit', 'gemini']:
            last = self.last_check.get(api_name, 0)
            
            if now - last > self.check_interval:
                logger.info(f"🔍 Перевіряю {api_name.upper()} API...")
                
                if api_name == 'bybit':
                    self.check_bybit()
                elif api_name == 'gemini':
                    self.check_gemini()
                
                self.last_check[api_name] = now

# Глобальний екземпляр
api_checker = APIChecker()

def start_api_checker():
    """Перевіряти API регулярно"""
    schedule.every(5).days.do(api_checker.check_all)
    
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Перевіра кожну годину

def schedule_daily_reset():
    """Планує щоденний скид сигналів о 8:00 UTC"""
    schedule.every().day.at("08:00").do(reset_daily_signals)
    logger.info("✅ Daily signal reset scheduled for 08:00 UTC")
    
    while True:
        schedule.run_pending()
        time.sleep(60)
