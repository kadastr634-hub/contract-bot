from dotenv import load_dotenv
import os

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
PAID_PRICE = int(os.getenv("PAID_PRICE", "1490"))
GIGACHAT_VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() in {
    "1", "true", "yes", "on"
}

REQUIRED_ENV_VARS = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "GIGACHAT_TOKEN": GIGACHAT_TOKEN,
    "YOOKASSA_SHOP_ID": YOOKASSA_SHOP_ID,
    "YOOKASSA_SECRET_KEY": YOOKASSA_SECRET_KEY,
}


def validate_config():
    missing = [name for name, value in REQUIRED_ENV_VARS.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Add them to .env locally or Railway Variables in production."
        )
