import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import logging
from datetime import datetime
from market_fetcher import fetch_ohlcv
import random

logger = logging.getLogger(__name__)

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).fillna(0)
    loss = -delta.clip(upper=0).fillna(0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> float:
    """Обчислює Average True Range"""
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    atr_val = df['tr'].rolling(period).mean().iloc[-1]
    return round(atr_val, 8)

def calculate_tp_sl(entry: float, signal_type: str) -> tuple:
    """
    Розраховує TP і SL на основі Reward:Risk (RR).
    Фіксуємо ризик (SL) у відсотках, наприклад 2%.
    RR обираємо із професійного набору [3..5] (3:1, 4:1, 5:1) — максимум 5:1.
    TP (%) = risk% * RR
    Повертаємо: tp, sl, roi_pct, rr
    """
    risk_pct = 2.0  # фіксований ризик у відсотках (SL = -2%)
    rr = random.choice([3, 4, 5])  # RR обмежено до максимум 5:1
    reward_pct = risk_pct * rr  # TP у відсотках
    
    if signal_type == 'BUY':
        tp = entry * (1 + reward_pct / 100.0)
        sl = entry * (1 - risk_pct / 100.0)
    elif signal_type == 'SELL':
        tp = entry * (1 - reward_pct / 100.0)
        sl = entry * (1 + risk_pct / 100.0)
    else:
        tp = entry * 1.01
        sl = entry * 0.99
        reward_pct = 1.0
        rr = 0

    return tp, sl, round(reward_pct, 2), rr

def keltner_breakout(df: pd.DataFrame):
    """Стратегія Keltner Channel Breakout"""
    period = 20
    atr_mult = 2.0
    
    df['ma'] = df['close'].rolling(period).mean()
    df['atr'] = df['high'].rolling(period).apply(
        lambda arr: float(np.mean(np.diff(arr))) if len(arr) > 1 else 0.0,
        raw=True
    )
    
    df['upper'] = df['ma'] + (df['atr'] * atr_mult)
    df['lower'] = df['ma'] - (df['atr'] * atr_mult)
    
    close = df['close'].iloc[-1]
    upper = df['upper'].iloc[-1]
    lower = df['lower'].iloc[-1]
    
    if close > upper:
        tp, sl, roi_pct, rr = calculate_tp_sl(close, 'BUY')
        return 'BUY', close, tp, sl, roi_pct, rr
    elif close < lower:
        tp, sl, roi_pct, rr = calculate_tp_sl(close, 'SELL')
        return 'SELL', close, tp, sl, roi_pct, rr
    else:
        return 'NEUTRAL', close, close * 1.01, close * 0.99, 0, 0

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    """Обчислює MACD"""
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def macd_strategy(df: pd.DataFrame):
    """MACD Based Strategy"""
    close = df['close']
    macd_line, signal_line, histogram = macd(close)
    
    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]
    last_hist = histogram.iloc[-1]
    prev_hist = histogram.iloc[-2] if len(histogram) > 1 else 0
    
    current_price = close.iloc[-1]
    
    if last_macd > last_signal and prev_hist < 0 and last_hist > 0:
        tp, sl, roi_pct, rr = calculate_tp_sl(current_price, 'BUY')
        return 'BUY', current_price, tp, sl, roi_pct, rr
    elif last_macd < last_signal and prev_hist > 0 and last_hist < 0:
        tp, sl, roi_pct, rr = calculate_tp_sl(current_price, 'SELL')
        return 'SELL', current_price, tp, sl, roi_pct, rr
    else:
        return 'NEUTRAL', current_price, current_price * 1.01, current_price * 0.99, 0, 0

def rsi_strategy(df: pd.DataFrame):
    """RSI Based Strategy (Overbought/Oversold)"""
    close = df['close']
    rsi_vals = rsi(close, period=14)
    current_rsi = rsi_vals.iloc[-1]
    current_price = close.iloc[-1]
    
    if current_rsi < 30:
        tp, sl, roi_pct, rr = calculate_tp_sl(current_price, 'BUY')
        return 'BUY', current_price, tp, sl, roi_pct, rr
    elif current_rsi > 70:
        tp, sl, roi_pct, rr = calculate_tp_sl(current_price, 'SELL')
        return 'SELL', current_price, tp, sl, roi_pct, rr
    else:
        return 'NEUTRAL', current_price, current_price * 1.01, current_price * 0.99, 0, 0


def generate_chart_image(df: pd.DataFrame):
    try:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df['ts'], df['close'], linewidth=2.5, color='#00BCD4', label='Ціна')
        ax.fill_between(df['ts'], df['low'], df['high'], alpha=0.1, color='#00BCD4')
        ax.set_ylabel('Ціна (USDT)', fontsize=11, fontweight='bold')
        ax.set_xlabel('Час', fontsize=11, fontweight='bold')
        ax.set_title('Аналіз ринку в реальному часі', fontsize=13, fontweight='bold')
        ax.grid(True, alpha=0.2, linestyle='--')
        ax.legend(fontsize=10)
        
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#0d0d0d')
        ax.tick_params(colors='#ffffff')
        ax.xaxis.label.set_color('#ffffff')
        ax.yaxis.label.set_color('#ffffff')
        ax.title.set_color('#ffffff')
        
        buf = BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format='png', dpi=100, facecolor='#1a1a1a')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        raise


def generate_signal_message(symbol='BTC/USDT', timeframe=None, use_gemini=False):
    """Генерує сигнал з випадковою стратегією та таймфреймом"""
    try:
        # Обрати випадковий таймфрейм
        if timeframe is None:
            timeframe = random.choice(['1h', '4h', '1d'])
        
        logger.info(f"🧠 AI: Starting signal generation for {symbol} ({timeframe})")
        
        df = fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
        if df is None or len(df) < 2:
            raise ValueError(f"❌ Немає даних для {symbol}")
        
        # Обрати випадкову стратегію
        strategy_name = random.choice(['keltner_breakout', 'macd', 'rsi'])
        logger.info(f"🧠 AI: Using strategy: {strategy_name}")
        
        if strategy_name == 'keltner_breakout':
            signal_type, entry, tp, sl, roi_pct, rr = keltner_breakout(df)
        elif strategy_name == 'macd':
            signal_type, entry, tp, sl, roi_pct, rr = macd_strategy(df)
        else:  # rsi
            signal_type, entry, tp, sl, roi_pct, rr = rsi_strategy(df)

        logger.info(f"🧠 AI: Computing indicators")
        atr_val = atr(df, period=14)
        rsi_val = rsi(df['close']).iloc[-1]
        rsi_val = round(rsi_val, 1) if not pd.isna(rsi_val) else 50.0
        
        ma_20 = df['close'].rolling(20).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        trend = "📉 Down" if current_price < ma_20 else "📈 Up"
        
        signal_icon = "🔼" if signal_type == "BUY" else "🔽" if signal_type == "SELL" else "⚪"
        
        # Замість обчислення ROI від значень повторно — використовуємо roi_pct та rr
        if signal_type == 'BUY':
            roi_display = roi_pct
        elif signal_type == 'SELL':
            roi_display = roi_pct
        else:
            roi_display = 0

        msg = []
        msg.append(f"📊 {symbol} {timeframe.upper()}")
        msg.append(f"🧠 Strategy: {strategy_name}")
        msg.append(f"{signal_icon} Signal: {signal_type}")
        msg.append(f"💵 Entry: {entry:.4f}")
        msg.append(f"🎯 TP: {tp:.4f} (ROI: +{roi_display}% | RR: {rr}:1)")
        msg.append(f"🛑 SL: {sl:.4f} (Risk: -2%)")
        msg.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        msg.append(f"📏 ATR: {atr_val}")
        msg.append("")
        msg.append(f"📊 {symbol.split('/')[0]} ({timeframe.upper()}): {trend}")
        msg.append(f"RSI: {rsi_val} | Trend: {'Bullish ⬆️' if current_price > ma_20 else 'Bearish ⬇️'}")
        
        full_msg = '\n'.join(msg)
        logger.info(f"✅ AI: Signal generated successfully with {strategy_name} (ROI: {roi_display}%)")
        chart_buf = generate_chart_image(df)
        return full_msg, chart_buf
    except Exception as e:
        logger.error(f"❌ AI: Signal generation FAILED - {type(e).__name__} - {str(e)}")
        raise