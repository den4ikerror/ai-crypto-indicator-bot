import ccxt
import pandas as pd
import logging
from config import KRAKEN_API_KEY, KRAKEN_API_SECRET   # замінено

logger = logging.getLogger(__name__)

# Ініціалізація Kraken
exchange = ccxt.kraken({
    'apiKey': KRAKEN_API_KEY,
    'secret': KRAKEN_API_SECRET,
    'enableRateLimit': True
})

def fetch_ohlcv(symbol: str = 'BTC/USDT', timeframe: str = '2h', limit: int = 200):
    try:
        if not symbol or '/' not in symbol:
            raise ValueError(f"❌ Неправильний формат символу: {symbol}")
        
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        if not bars or len(bars) < 2:
            raise ValueError(f"❌ Недостатньо даних для {symbol}")
        
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        logger.info(f"✅ Дані завантажені: {symbol} {timeframe} ({len(df)} свічок)")
        return df
    except ccxt.ExchangeError as e:
        logger.error(f"❌ Exchange error: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Fetch OHLCV error: {e}")
        raise