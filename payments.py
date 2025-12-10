from db import set_plan
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)

plan_config = {
    'starter': {'signals_daily': 2, 'days': 30},
    'pro': {'signals_daily': 5, 'days': 30},
    'bot1_year': {'signals_daily': 2, 'days': 365},
    'bot2_year': {'signals_daily': 5, 'days': 365}
}

def purchase_plan(chat_id: int, plan_key: str):
    try:
        if plan_key not in plan_config:
            raise ValueError(f"Unknown plan: {plan_key}")
        
        config = plan_config[plan_key]
        signals_daily = config['signals_daily']
        days = config['days']
        expires = int((datetime.utcnow() + timedelta(days=days)).timestamp())
        
        logger.info(f"💳 Processing purchase: user={chat_id}, plan={plan_key}, daily={signals_daily}, days={days}")
        set_plan(chat_id, plan_key, expires, signals_daily=signals_daily)
        logger.info(f"✅ Purchase completed: user={chat_id}, plan={plan_key}, signals_daily={signals_daily}")
        return True
    except Exception as e:
        logger.error(f"❌ Purchase FAILED: user={chat_id}, plan={plan_key} - {type(e).__name__} - {str(e)}")
        raise