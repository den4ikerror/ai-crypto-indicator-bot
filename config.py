from dotenv import load_dotenv
import os

load_dotenv()

# Tokens & API keys
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Замість Bybit додаємо Kraken
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY')
KRAKEN_API_SECRET = os.getenv('KRAKEN_API_SECRET')

ADMIN_ID = int(os.getenv('ADMIN_ID', '1595599668'))
MOD_CHANNEL_ID = int(os.getenv('MOD_CHANNEL_ID', '-1003421257189'))
# Subscription plans and pricing
PRICES = {
    'starter': 30.0,   # up to 2 signals/day
    'pro': 50.0,       # 3-5 signals/day
    'bot1_year': 270.0,
    'bot2_year': 360.0
}

USD_TO_UAH_RATE = 40.0  

# Crypto payment config
CRYPTO_PAYMENTS = {
    'usdt': {
        'name': 'USDT (TRC20)',
        'address': os.getenv('USDT_ADDRESS'),
        'network': 'Tron',
        'emoji': '💵'
    },
    'ton': {
        'name': 'TON',
        'address': os.getenv('TON_ADDRESS'),
        'network': 'TON Blockchain',
        'emoji': '🔷'
    },
    'btc': {
        'name': 'Bitcoin',
        'address': os.getenv('BTC_ADDRESS'),
        'network': 'Bitcoin',
        'emoji': '₿'
    },
    'eth': {
        'name': 'Ethereum',
        'address': os.getenv('ETH_ADDRESS'),
        'network': 'Ethereum',
        'emoji': '⟠'
    },
    'monobank': {
        'name': 'Monobank (UAH)',
        'address': 'https://send.monobank.ua/jar/7tjdex7qHm',
        'network': 'Monobank',
        'emoji': '🏦'
    }
}

# Risk configuration
def default_leverage_range():
    return (10, 50)