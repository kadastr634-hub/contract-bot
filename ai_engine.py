import re
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from config import GIGACHAT_TOKEN

llm = GigaChat(credentials=GIGACHAT_TOKEN, verify_ssl_certs=False)


# =====================
# ПРОМПТЫ
# =====================

def build_free_prompt(text: str, role: str) -> str:
    text = text[:20000] if len(text) > 20000 else text
    return f"""Ты — AI Risk Engine для анализа договоров.
Роль клиента: {role}

Проанализируй договор и верни ТОЛЬКО структурированный результат.

ДОКУМЕНТ:
{text}

ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА:

VERDICT: [🟢 Можно подписывать / 🟡 Можно подписывать с правками / 🔴 Нельзя подписывать]
SCORE: [целое число от 0 до 10]
TOTAL_RISKS: [количество рисков]
RISK_TITLE: [общее название риска — БЕЗ юридических терминов, простыми словами]
RISK_CATEGORY: [одна фраза — к чему относится: деньги / сроки / ответственность / расторжение / конфиденциальность]
RISK_QUOTE: [короткая цитата из договора 1-2 предложения — именно те слова из текста, которые создают этот риск. Цитируй дословно.]

ПРАВИЛА — очень важно:
- НЕ указывай номера пунктов
- НЕ давай рекомендаций что делать
- НЕ объясняй подробно что происходит
- Название риска — общее, тревожное, без деталей
- Цитата — короткая, дословная, из реального текста договора
- Анализируй с позиции роли: {role}"""


def build_pro_prompt(text: str, role: str) -> str:
    text = text[:25000] if len(text) > 25000 else text
    return f"""Ты — AI Risk Engine для анализа договоров. Ты профессиональный юрист-аналитик.
Роль клиента: {role}

Дай ПОЛНЫЙ профессиональный анализ договора.

ДОКУМЕНТ:
{text}

ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА:

VERDICT: [🟢 Можно подписывать / 🟡 Можно подписывать с правками / 🔴 Нельзя подписывать]
SCORE: [0-10]
SUMMARY: [2-3 предложения общего вывода по договору]

RISK_1_TITLE: [название риска]
RISK_1_DESC: [описание риска, 2-4 предложения]
RISK_1_CONSEQUENCE: [финансовые и/или правовые последствия для клиента]
RISK_1_WAS: [опасная формулировка из договора или её пересказ]
RISK_1_NOW: [рекомендуемая замена — конкретная формулировка]

RISK_2_TITLE: [название риска]
RISK_2_DESC: [описание]
RISK_2_CONSEQUENCE: [последствия]
RISK_2_WAS: [текущая формулировка]
RISK_2_NOW: [рекомендуемая замена]

[Продолжай RISK_3, RISK_4 ... до RISK_7 если рисков больше]

NEGOTIATION: [переговорная стратегия — 3-5 конкретных пункта что требовать от второй стороны]
FINAL_RECOMMENDATION: [итоговый совет: подписывать как есть / только после правок / не подписывать]

ПРАВИЛА:
- Анализируй строго с позиции роли: {role}
- Найди все значимые риски (до 7)
- Правки БЫЛО→СТАЛО должны быть конкретными юридическими формулировками
- Переговорная стратегия — конкретные аргументы, не общие советы
- НЕ пиши вступлений и послесловий вне формата"""


# =====================
# ВЫЗОВ GIGACHAT
# =====================

def ask_gigachat(prompt: str):
    try:
        response = llm.chat(
            Chat(messages=[
                Messages(
                    role=MessagesRole.SYSTEM,
                    content="Ты профессиональный AI-аналитик договоров. "
                            "Отвечай ТОЛЬКО по заданному формату. Без вступлений."
                ),
                Messages(role=MessagesRole.USER, content=prompt)
            ])
        )
        if not response or not response.choices:
            return None
        return response.choices[0].message.content
    except Exception as e:
        print(f"[AI] Ошибка GigaChat: {e}")
        return None


# =====================
# ПАРСИНГ ОТВЕТОВ
# =====================

def parse_free(raw: str):
    if not raw:
        return None

    def find(pattern, default=None):
        m = re.search(pattern, raw, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    score_raw = find(r"SCORE:\s*(\d+)")
    return {
        "score": int(score_raw) if score_raw else 5,
        "total_risks": find(r"TOTAL_RISKS:\s*(\d+)", "?"),
        "risk_title": find(r"RISK_TITLE:\s*(.+?)(?:\n|$)", "Риск не определён"),
        "risk_category": find(r"RISK_CATEGORY:\s*(.+?)(?:\n|$)", ""),
        "risk_quote": find(r"RISK_QUOTE:\s*(.+?)(?:\n\n|$)", ""),
    }


def parse_pro(raw: str):
    if not raw:
        return None

    def find(pattern, default=""):
        m = re.search(pattern, raw, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    result = {
        "verdict": find(r"VERDICT:\s*(.+?)(?:\n|SCORE)"),
        "score": int(find(r"SCORE:\s*(\d+)") or "5"),
        "summary": find(r"SUMMARY:\s*(.+?)(?:\n\nRISK|\nRISK)"),
        "risks": [],
        "negotiation": find(r"NEGOTIATION:\s*(.+?)(?:\nFINAL|FINAL_RECOMMENDATION)"),
        "final": find(r"FINAL_RECOMMENDATION:\s*(.+?)$"),
    }

    for i in range(1, 8):
        title = find(rf"RISK_{i}_TITLE:\s*(.+?)(?:\n|$)")
        if not title:
            break
        result["risks"].append({
            "title": title,
            "desc": find(rf"RISK_{i}_DESC:\s*(.+?)(?:\nRISK_{i}_CONSEQUENCE|$)"),
            "consequence": find(rf"RISK_{i}_CONSEQUENCE:\s*(.+?)(?:\nRISK_{i}_WAS|$)"),
            "was": find(rf"RISK_{i}_WAS:\s*(.+?)(?:\nRISK_{i}_NOW|$)"),
            "now": find(rf"RISK_{i}_NOW:\s*(.+?)(?:\n\nRISK|\nNEGOTIATION|$)"),
        })

    if not result["risks"]:
        result["raw"] = raw

    return result


# =====================
# ВЕРДИКТ
# =====================

def get_verdict(score: int) -> str:
    if score <= 3:
        return "🟢 Можно подписывать"
    elif score <= 6:
        return "🟡 Можно подписывать с правками"
    else:
        return "🔴 Нельзя подписывать"


# =====================
# ФОРМАТИРОВАНИЕ PRO ОТВЕТА
# =====================

def format_pro_result(data: dict) -> list:
    messages = []

    header = (
        f"📋 <b>ПОЛНЫЙ АНАЛИЗ ДОГОВОРА</b>\n\n"
        f"{data.get('verdict', '—')}\n"
        f"📊 Score: {data.get('score', '—')}/10\n\n"
    )
    if data.get("summary"):
        header += f"<b>Общий вывод:</b>\n{data['summary']}\n"
    messages.append(header)

    risks = data.get("risks", [])
    if risks:
        for i, risk in enumerate(risks, 1):
            txt = f"⚠️ <b>РИСК {i}: {risk.get('title', '—')}</b>\n\n"
            txt += f"{risk.get('desc', '')}\n\n"
            if risk.get("consequence"):
                txt += f"💥 <b>Последствие:</b>\n{risk['consequence']}\n\n"
            if risk.get("was"):
                txt += f"📄 <b>БЫЛО:</b>\n<i>{risk['was']}</i>\n\n"
            if risk.get("now"):
                txt += f"✅ <b>СТАЛО:</b>\n<i>{risk['now']}</i>\n\n"
            messages.append(txt)
    elif data.get("raw"):
        messages.append(f"📋 <b>Результат анализа:</b>\n\n{data['raw'][:3000]}")

    final = "━━━━━━━━━━━━━━━━━━━━\n\n"
    if data.get("negotiation"):
        final += f"🧠 <b>ПЕРЕГОВОРНАЯ СТРАТЕГИЯ:</b>\n{data['negotiation']}\n\n"
    if data.get("final"):
        final += f"✅ <b>ИТОГОВАЯ РЕКОМЕНДАЦИЯ:</b>\n{data['final']}\n\n"
    final += "━━━━━━━━━━━━━━━━━━━━\n\n"
final += (
    "⚖️ <i>Результат сформирован с использованием технологий "
    "искусственного интеллекта и носит информационно-рекомендательный "
    "характер. Не является юридическим заключением и не заменяет "
    "консультацию юриста. Загруженный текст договора используется только "
    "для этого анализа и не передаётся третьим лицам.</i>\n\n"
)
    messages.append(final)

    return messages