from telegram import Update
from telegram.ext import ContextTypes

WELCOME_TEXT = (
    "✈️ <b>Düşük İrtifa'ya Hoş Geldin!</b>\n\n"
    "Ben senin uçuş asistanınım. Benimle yazarak her şeyi yapabilirsin — menüye gerek yok!\n\n"
    "� <b>Bana şunları yazabilirsin:</b>\n\n"
    "  <i>\"İstanbul'dan Antalya'ya 15 Haziran bilet bak\"</i>\n"
    "  <i>\"En ucuz yurt dışı uçuşları nereye?\"</i>\n"
    "  <i>\"Londra'ya direkt uçuş var mı?\"</i>\n"
    "  <i>\"Haziranda tatile çıkmak istiyorum\"</i>\n"
    "  <i>\"Takiplerim neler?\"</i>\n\n"
    "Hadi başlayalım! Nereye uçmak istiyorsun? ✈️"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["chat_history"] = []
    await update.message.reply_text(WELCOME_TEXT, parse_mode="HTML")
