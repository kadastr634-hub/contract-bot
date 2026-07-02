import uuid
import json
import requests
from requests.auth import HTTPBasicAuth
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY

YOOKASSA_API = "https://api.yookassa.ru/v3"


def create_payment(user_id: int, analysis_id: int, amount: int,
                   return_url: str = "https://t.me") -> tuple:
    idempotency_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Полный анализ договора #{analysis_id}",
        "metadata": {
            "user_id": str(user_id),
            "analysis_id": str(analysis_id)
        }
    }
    try:
        resp = requests.post(
            f"{YOOKASSA_API}/payments",
            json=payload,
            auth=HTTPBasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers={
                "Idempotence-Key": idempotency_key,
                "Content-Type": "application/json"
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"], data["confirmation"]["confirmation_url"]
    except Exception as e:
        print(f"[PAYMENTS] Ошибка: {e}")
        return None


def check_payment_status(payment_id: str):
    try:
        resp = requests.get(
            f"{YOOKASSA_API}/payments/{payment_id}",
            auth=HTTPBasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("status")
    except Exception as e:
        print(f"[PAYMENTS] Ошибка проверки: {e}")
        return None


def parse_webhook(body: bytes):
    try:
        data = json.loads(body)
        obj = data.get("object", {})
        meta = obj.get("metadata", {})
        return {
            "event": data.get("event"),
            "payment_id": obj.get("id"),
            "status": obj.get("status"),
            "user_id": int(meta.get("user_id", 0)),
            "analysis_id": int(meta.get("analysis_id", 0))
        }
    except Exception as e:
        print(f"[PAYMENTS] Ошибка парсинга: {e}")
        return None