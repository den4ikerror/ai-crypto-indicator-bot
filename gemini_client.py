import requests
import logging
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self, api_key=GEMINI_API_KEY):
        self.api_key = api_key
        self.endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent'

    def analyze_market(self, prompt: str) -> str:
        try:
            headers = {'Content-Type': 'application/json'}
            payload = {
                'contents': [{'parts': [{'text': prompt}]}]
            }
            url = f"{self.endpoint}?key={self.api_key}"
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            
            if resp.status_code != 200:
                logger.error(f"Gemini API error: {resp.status_code}")
                return '❌ Помилка аналізу AI'
            
            data = resp.json()
            text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            return text if text else '❌ Немає відповіді від AI'
        except Exception as e:
            logger.error(f"Gemini client error: {e}")
            return f'❌ Помилка AI: {str(e)}'