import os
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from config import TELEGRAM_TOKEN, PAID_PRICE
from database import (
    init_db, get_or_create_user, set_user_role, get_user_role,
    save_analysis, get_analysis, save_pro_result,
    create_payment_record, update_payment_status,
    get_user_agreement, save_user_agreement
)
from payments import create_payment, check_payment_status
from ai_engine import (
    build_free_prompt, build_pro_prompt, ask_gigachat,
    parse_free, parse_pro, get_verdict, format_pro_result
)

import fitz
import docx as docx_lib

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BOT] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

ROLES = {
    "1": "Собственник бизнеса",
    "2": "Арендатор",
    "3": "Арендодатель",
    "4": "Заказчик",
    "5": "Исполнитель",
    "6": "Поставщик",
    "7": "Покупатель"
}

def extract_pdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    finally:
        if os.path.exists(path):
            os.remove(path)

def extract_docx(path: str) -> str:
    try:
        doc = docx_lib.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    finally:
        if os.path.exists(path):
            os.remove(path)

def format_free_result(data: dict, analysis_id: int):
    verdict = get_verdict(data["score"])
    risk_title = data.get("risk_title", "—")

    try:
        total_int = int(data.get("total_risks", 1))
    except (ValueError, TypeError):
        total_int = 1

    if total_int == 1:
        risks_line = "⚠️ Обнаружен <b>1 риск</b>"
        risk_header = "⚠️ <b>КЛЮЧЕВОЙ РИСК</b>"
        hidden_block = ""
        all_risks_line = "полный разбор найденного риска с конкретным пунктом"
    else:
        risks_line = f"⚠️ Обнаружено рисков: <b>{total_int}</b>"
        risk_header = f"⚠️ <b>КЛЮЧЕВОЙ РИСК (1 из {total_int})</b>"
        hidden_count = total_int - 1
        if hidden_count == 1:
            hidden_word = "риск скрыт"
        elif hidden_count < 5:
            hidden_word = "риска скрыты"
        else:
            hidden_word = "рисков скрыты"
        hidden_block = f"\n<b>+ ещё {hidden_count} {hidden_word}</b>\n"
        all_risks_line = f"все {total_int} риска с конкретными пунктами договора"

    text = (
        f"📌 <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>\n\n"
        f"{verdict}\n\n"
        f"📊 <b>Score:</b> {data['score']}/10\n"
        f"{risks_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{risk_header}\n\n"
        f"<b>{risk_title}</b>\n\n"
        f"В договоре есть условие, которое в случае спора работает против вас.\n"
        f"Это может стоить вам денег.\n"
        f"{hidden_block}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Чтобы узнать:\n"
        f"— {all_risks_line}\n"
        f"— чем каждый грозит в деньгах\n"
        f"— готовые формулировки «Было → Стало»\n"
        f"— как обсуждать со второй стороной\n\n"
        f"👇"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"🔓 Получить полный разбор — {PAID_PRICE} ₽",
            callback_data=f"pay_{analysis_id}"
        )
    ]])

    return text, keyboard
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username or "")

    # Проверяем давал ли пользователь согласие
    agreed = await get_user_agreement(user.id)

    if not agreed:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Согласен с политикой — начать",
                callback_data="agree"
            )
        ], [
            InlineKeyboardButton(
                "📄 Политика обработки данных",
                url="https://telegra.ph/Politika-obrabotki-personalnyh-dannyh-07-04-3"
            )
        ]])
        await update.message.reply_text(
            "🤖 <b>Можно подписывать AI</b>\n\n"
            "Перед началом работы ознакомьтесь с политикой "
            "обработки персональных данных и дайте согласие.\n\n"
            "Нажимая «Согласен», вы подтверждаете что ознакомились "
            "с политикой и даёте согласие на обработку данных.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    await show_main_menu(update.message)


async def show_main_menu(message):
    await message.reply_text(
        "🤖 <b>Можно подписывать AI</b>\n\n"
        "Проверяю договоры перед подписанием за 30 секунд.\n\n"
        "<b>Что умею:</b>\n\n"
        "📄 Анализирую PDF, DOCX и текст договора\n"
        "⚖️ Нахожу все опасные условия и риски\n"
        "💰 Показываю где можно потерять деньги\n"
        "✍️ Даю готовые формулировки «Было → Стало»\n"
        "🧠 Строю переговорную стратегию\n\n"
        "<b>Выберите роль — отправьте цифру:</b>\n\n"
        "👤 <b>1</b> — Собственник бизнеса\n"
        "🏢 <b>2</b> — Арендатор\n"
        "🏠 <b>3</b> — Арендодатель\n"
        "📄 <b>4</b> — Заказчик\n"
        "🛠 <b>5</b> — Исполнитель\n"
        "🚚 <b>6</b> — Поставщик\n"
        "🛒 <b>7</b> — Покупатель\n\n"
        "После выбора роли отправьте договор 👇",
        parse_mode="HTML"
    )


async def agree_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await save_user_agreement(user_id)
    await query.message.reply_text(
        "✅ Спасибо! Согласие зафиксировано."
    )
    await show_main_menu(query.message)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📄 Открыть политику",
            url="https://telegra.ph/Politika-obrabotki-personalnyh-dannyh-07-04-3"
        )
    ]])
    await update.message.reply_text(
        "📋 <b>Политика обработки персональных данных</b>\n\n"
        "Нажмите кнопку ниже чтобы ознакомиться с политикой.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    try:
        analysis_id = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("❌ Ошибка. Загрузите договор заново.")
        return
    await query.message.reply_text("⏳ Создаю ссылку на оплату...")
    result = create_payment(user_id, analysis_id, PAID_PRICE)
    if not result:
        await query.message.reply_text("❌ Не удалось создать платёж. Попробуйте через минуту.")
        return
    payment_id, confirm_url = result
    await create_payment_record(user_id, analysis_id, payment_id, PAID_PRICE)
    log.info(f"Создан платёж {payment_id} user={user_id} analysis={analysis_id}")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💳 Оплатить", url=confirm_url)
    ], [
        InlineKeyboardButton("✅ Я оплатил — проверить", callback_data=f"check_{payment_id}")
    ]])
    await query.message.reply_text(
        f"💳 <b>Оплата полного анализа</b>\n\n"
        f"Сумма: <b>{PAID_PRICE} ₽</b>\n\n"
        f"Нажмите «Оплатить», после оплаты вернитесь сюда "
        f"и нажмите «Я оплатил — проверить».\n\n"
        f"<i>Принимаем: Visa, Mastercard, Мир, СБП</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Проверяю...")
    user_id = update.effective_user.id
    try:
        payment_id = query.data.split("_", 1)[1]
    except IndexError:
        await query.message.reply_text("❌ Ошибка проверки.")
        return
    status = check_payment_status(payment_id)
    log.info(f"Проверка платежа {payment_id}: {status}")
    if status == "succeeded":
        await update_payment_status(payment_id, "succeeded")
        await query.message.reply_text(
            "✅ <b>Оплата подтверждена!</b>\n\n"
            "🧠 Анализируем договор. Обычно это занимает до 30 секунд.",
            parse_mode="HTML"
        )
        await send_pro_analysis(user_id, payment_id, query.message)
    elif status == "pending":
        await query.message.reply_text("⏳ Оплата ещё обрабатывается.\n\nПодождите минуту и нажмите «Я оплатил» снова.")
    elif status == "canceled":
        await query.message.reply_text("❌ Платёж отменён.\n\nНажмите «Получить полный разбор» снова.")
    else:
        await query.message.reply_text("Статус обновляется. Если оплата прошла — подождите минуту и проверьте снова.")

async def send_pro_analysis(user_id: int, payment_id: str, message):
    from database import get_payment_by_id
    payment = await get_payment_by_id(payment_id)
    if not payment:
        await message.reply_text("❌ Не найдена запись платежа. Напишите нам.")
        return
    analysis = await get_analysis(payment["analysis_id"])
    if not analysis:
        await message.reply_text("❌ Не найден документ. Загрузите договор повторно — этот анализ будет бесплатным.")
        return
    raw_pro = None
    for attempt in range(2):
        raw_pro = ask_gigachat(
        build_pro_prompt(
            analysis["doc_text"],
            analysis["role"] or "Не указана",
            analysis["verdict"] or "",
            analysis["score"] or 0
        )
    )
        if raw_pro:
            break
        if attempt == 0:
            log.warning("GigaChat не ответил, повторная попытка...")
            time.sleep(3)
    if not raw_pro:
        await message.reply_text(
            "⚠️ Сервис анализа сейчас временно перегружен.\n\n"
            "Обычно это занимает менее минуты.\n\n"
            "Если анализ не придёт в течение 2 минут — напишите нам."
        )
        return
    pro_data = parse_pro(raw_pro)
    if pro_data:
        await save_pro_result(payment["analysis_id"], pro_data)
        messages = format_pro_result(pro_data)
    else:
        messages = [f"📋 <b>Полный анализ:</b>\n\n{raw_pro[:3500]}"]
    for msg in messages:
        await message.reply_text(msg, parse_mode="HTML")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Проверить ещё один договор", callback_data="new_analysis")
    ]])
    await message.reply_text(
        "✅ <b>Анализ завершён.</b>\n\nХотите проверить ещё один договор?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def new_analysis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    role = await get_user_role(user.id)
    if role:
        await query.message.reply_text(
            f"📄 Отправьте следующий договор.\n\nТекущая роль: <b>{role}</b>\nЧтобы изменить роль — отправьте цифру от 1 до 7.",
            parse_mode="HTML"
        )
    else:
        await query.message.reply_text(
            "Отправьте цифру чтобы выбрать роль:\n\n"
            "👤 <b>1</b> — Собственник бизнеса\n"
            "🏢 <b>2</b> — Арендатор\n"
            "🏠 <b>3</b> — Арендодатель\n"
            "📄 <b>4</b> — Заказчик\n"
            "🛠 <b>5</b> — Исполнитель\n"
            "🚚 <b>6</b> — Поставщик\n"
            "🛒 <b>7</b> — Покупатель",
            parse_mode="HTML"
        )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    await get_or_create_user(user_id, user.username or "")
    # Защита от спама
    if update.message.text:
        spam_keywords = ["казино", "casino", "ставки", "бонус", "фрибет", 
                        "lucky", "кэшбэк", "выплат", "http", "https", "t.me/+"]
        msg_lower = update.message.text.lower()
        if any(kw in msg_lower for kw in spam_keywords):
            log.warning(f"Спам от user={user_id}: {update.message.text[:50]}")
            return
    text = None
    doc_type = "text"
    if update.message.text:
        raw = update.message.text.strip()
        if raw in ROLES:
            await set_user_role(user_id, ROLES[raw])
            await update.message.reply_text(
                f"✅ <b>Роль выбрана:</b> {ROLES[raw]}\n\n📄 Теперь отправьте договор:\n— PDF\n— DOCX\n— или вставьте текст",
                parse_mode="HTML"
            )
            return
        text = raw
    if update.message.document:
        file = await update.message.document.get_file()
        filename = update.message.document.file_name.lower()
        ts = int(time.time())
        if filename.endswith(".pdf"):
            path = f"/tmp/doc_{user_id}_{ts}.pdf"
            await file.download_to_drive(path)
            text = extract_pdf(path)
            doc_type = "pdf"
        elif filename.endswith(".docx"):
            path = f"/tmp/doc_{user_id}_{ts}.docx"
            await file.download_to_drive(path)
            text = extract_docx(path)
            doc_type = "docx"
        else:
            await update.message.reply_text("⚠️ Только PDF и DOCX файлы.")
            return
    if not text:
        await update.message.reply_text("📄 Отправьте договор:\n— PDF файл\n— DOCX файл\n— или вставьте текст")
        return
    if len(text.strip()) < 100:
        await update.message.reply_text("⚠️ Текст слишком короткий.")
        return
    role = await get_user_role(user_id) or "Не указана"
    loading_msg = await update.message.reply_text("⏳ Анализирую договор...")
    raw_ai = None
    for attempt in range(2):
        raw_ai = ask_gigachat(build_free_prompt(text, role))
        if raw_ai:
            break
        if attempt == 0:
            time.sleep(3)
    try:
        await loading_msg.delete()
    except Exception:
        pass
    if not raw_ai:
        await update.message.reply_text("⚠️ Сервис анализа сейчас временно перегружен.\n\nПопробуйте через 1–2 минуты.")
        return
    data = parse_free(raw_ai)
    if not data:
        await update.message.reply_text("⚠️ Сервис анализа сейчас временно перегружен.\n\nПопробуйте через минуту.")
        return
    verdict = get_verdict(data["score"])
    analysis_id = await save_analysis(
        user_id=user_id, role=role, doc_type=doc_type,
        doc_text=text, verdict=verdict, score=data["score"],
        free_result=data
    )
    log.info(f"Анализ #{analysis_id} user={user_id} score={data['score']} role={role}")
    result_text, keyboard = format_free_result(data, analysis_id)
    await update.message.reply_text(result_text, reply_markup=keyboard, parse_mode="HTML")

async def post_init(application):
    await init_db()
    log.info("БД инициализирована")

app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("privacy", privacy_command))
app.add_handler(CallbackQueryHandler(agree_callback, pattern=r"^agree$"))
app.add_handler(CallbackQueryHandler(pay_callback, pattern=r"^pay_\d+$"))
app.add_handler(CallbackQueryHandler(check_payment_callback, pattern=r"^check_.+$"))
app.add_handler(CallbackQueryHandler(new_analysis_callback, pattern=r"^new_analysis$"))
app.add_handler(MessageHandler(filters.ALL, handle))

log.info("🚀 BOT STARTING...")
app.run_polling()