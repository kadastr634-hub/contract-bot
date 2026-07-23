import re
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from config import GIGACHAT_TOKEN, GIGACHAT_VERIFY_SSL

llm = GigaChat(credentials=GIGACHAT_TOKEN, verify_ssl_certs=GIGACHAT_VERIFY_SSL)


RISK_MARKERS = (
    "полученн", "по усмотрению", "разумн", "самостоятельн",
    "при наличии возможности", "вправе",
)

FINANCIAL_TERMS = (
    "оплат", "вознагражден", "стоимост", "цен", "сумм", "денеж",
    "штраф", "неустой", "расход", "налог", "удержан", "задолж",
)

FORMAL_TERMS = ("подсуд", "персональн", "конфиденц")


def detect_risk_markers(text: str) -> list[str]:
    """Возвращает найденные в тексте маркеры неоднозначности без дублей."""
    lowered = text.lower()
    return [marker for marker in RISK_MARKERS if marker in lowered]


def build_pro_prompt(text: str, role: str, verdict: str = "", score: int = 0) -> str:
    text = text[:25000] if len(text) > 25000 else text
    verdict_hint = ""
    if verdict and score:
        verdict_hint = f"\nВАЖНО: используй именно этот вердикт: {verdict}, Score: {score}\n"
    markers = detect_risk_markers(text)
    markers_hint = ", ".join(markers) if markers else "не обнаружены автоматически"
    is_fragment = len(text) < 3000
    scope = (
        "Передан фрагмент договора. Анализируй только фактически переданный текст. "
        "Не считай риском отсутствие разделов о подсудности, конфиденциальности, "
        "персональных данных, реквизитов и иных условий, которых во фрагменте нет."
        if is_fragment else
        "Передан договор или крупная часть договора. Анализируй все фактически имеющиеся условия."
    )
    return f"""Ты — AI Risk Engine для анализа договоров. Ты профессиональный юрист-аналитик.
Роль клиента: {role}
{verdict_hint}
Дай ПОЛНЫЙ профессиональный анализ договора.

ОБЪЁМ ТЕКСТА: {scope}
АВТОМАТИЧЕСКИ НАЙДЕННЫЕ МАРКЕРЫ НЕОДНОЗНАЧНОСТИ: {markers_hint}

ДОКУМЕНТ:
{text}

ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА:

VERDICT: [используй вердикт из подсказки выше]
SCORE: [используй score из подсказки выше]
SUMMARY: [2-3 предложения общего вывода по договору]

RISK_1_TITLE: [название риска]
RISK_1_POINT: [номер пункта договора где найден риск, например "4.2" или "раздел об ответственности"]
RISK_1_DESC: [описание риска, 2-4 предложения]
RISK_1_CONSEQUENCE: [финансовые и/или правовые последствия для клиента]
RISK_1_WAS: [опасная формулировка из договора или её пересказ]
RISK_1_NOW: [рекомендуемая замена — конкретная формулировка]

RISK_2_TITLE: [название риска]
RISK_2_POINT: [номер пункта]
RISK_2_DESC: [описание]
RISK_2_CONSEQUENCE: [последствия]
RISK_2_WAS: [текущая формулировка]
RISK_2_NOW: [рекомендуемая замена]

[Продолжай RISK_3, RISK_4 ... до RISK_7 если рисков больше]

NEGOTIATION: [переговорная стратегия — 3-5 пунктов, каждый с привязкой к конкретному риску и пункту договора. Формат: "1. Добейтесь исключения условия о праве исполнителя пересматривать цену (Риск 1, п. 4.2)."]
FINAL_RECOMMENDATION: [итоговый совет]

ПРАВИЛА:
- Анализируй строго с позиции роли: {role}
- Сначала ищи риски возможной потери денег: базу и момент расчёта
  вознаграждения, налоги и удержания, расходы, очередность платежей,
  двойную оплату, штрафы и иные финансовые последствия
- Затем ищи односторонние преимущества, право одной стороны самостоятельно
  определять порядок исполнения или толковать договор, двойное толкование и
  неопределённые термины
- Любой риск возможной потери денег обязательно включай в первые три риска
- Каждый самостоятельный финансовый или односторонний риск оформляй отдельно
- Подсудность, персональные данные и конфиденциальность ставь после практически
  значимых рисков; для фрагмента не придумывай риски отсутствующих разделов
- Формулировки «полученная сумма», «по усмотрению», «разумный срок», «вправе»,
  «самостоятельно определяет» и «при наличии возможности» считай сигналами
  повышенного риска, если они влияют на права, деньги или порядок исполнения
- RISK_X_POINT — обязательно заполнять, не оставлять пустым
- Найди все значимые риски (до 7)
- Правки БЫЛО→СТАЛО должны быть конкретными юридическими формулировками
- НЕ пиши вступлений и послесловий вне формата"""


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


def parse_pro(raw: str):
    if not raw:
        return None

    def find(pattern, default=""):
        m = re.search(pattern, raw, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    result = {
        "verdict": find(r"VERDICT:\s*(.+?)(?:\n|SCORE)"),
        "score": max(0, min(int(find(r"SCORE:\s*(\d+)") or "5"), 10)),
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
            "point": find(rf"RISK_{i}_POINT:\s*(.+?)(?:\n|$)"),
            "desc": find(rf"RISK_{i}_DESC:\s*(.+?)(?:\nRISK_{i}_CONSEQUENCE|$)"),
            "consequence": find(rf"RISK_{i}_CONSEQUENCE:\s*(.+?)(?:\nRISK_{i}_WAS|$)"),
            "was": find(rf"RISK_{i}_WAS:\s*(.+?)(?:\nRISK_{i}_NOW|$)"),
            "now": find(rf"RISK_{i}_NOW:\s*(.+?)(?:\n\nRISK|\nNEGOTIATION|$)"),
        })

    if not result["risks"]:
        result["raw"] = raw

    return result


def prioritize_analysis(data: dict, source_text: str) -> dict:
    """Поднимает подтверждённые финансовые риски и корректирует Score."""
    if not data:
        return data

    def priority(risk: dict) -> tuple[int, int]:
        content = " ".join(str(value) for value in risk.values()).lower()
        financial = any(term in content for term in FINANCIAL_TERMS)
        one_sided = any(term in content for term in RISK_MARKERS)
        formal_only = any(term in content for term in FORMAL_TERMS) and not financial
        return (0 if financial else 1 if one_sided else 3 if formal_only else 2, 0)

    data["risks"] = sorted(data.get("risks", []), key=priority)
    marker_count = len(detect_risk_markers(source_text))
    if marker_count:
        data["score"] = min(10, max(0, int(data.get("score", 5))) + min(marker_count, 2))
        data["verdict"] = get_verdict(data["score"])
    return data


def build_free_result(data: dict) -> dict:
    """Создаёт FREE-витрину из уже готового полного анализа."""
    risks = data.get("risks", []) if data else []
    return {
        "score": data.get("score", 5) if data else 5,
        "risk_title": risks[0].get("title", "Риск не определён") if risks else "Риск не определён",
    }


def get_verdict(score: int) -> str:
    if score <= 3:
        return "🟢 Можно подписывать"
    elif score <= 6:
        return "🟡 Можно подписывать с правками"
    else:
        return "🔴 Нельзя подписывать"


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
    final += (
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚖️ <i>Результат сформирован с использованием технологий "
        "искусственного интеллекта и носит информационно-рекомендательный "
        "характер. Не является юридическим заключением и не заменяет "
        "консультацию юриста. Загруженный текст договора используется только "
        "для этого анализа и не передаётся третьим лицам.</i>\n\n"
        "💼 Можете загрузить следующий договор."
    )
    messages.append(final)

    return messages
