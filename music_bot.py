import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from yt_dlp import YoutubeDL

# Configuração de Logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Configuração do Token (No Railway, utilize variáveis de ambiente)
TOKEN = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")

# Dicionário em memória para armazenar os resultados de busca temporários
# Estrutura: { user_id: { result_id: { "url": str, "title": str, "uploader": str } } }
SEARCH_RESULTS = {}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start para boas-vindas."""
    user_first_name = update.effective_user.first_name
    welcome_text = (
        f"Olá, {user_first_name}! 🎵\n\n"
        "Envie o nome de uma música ou artista para buscar. "
        "Eu apresentarei uma lista de resultados para você escolher e baixar o áudio em MP3."
    )
    await update.message.reply_text(welcome_text)


async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mecanismo de busca usando yt-dlp."""
    query = update.message.text.strip()
    user_id = update.effective_user.id

    if not query:
        return

    status_msg = await update.message.reply_text("🔎 Pesquisando músicas, aguarde...")

    # Configuração do yt-dlp para busca sem download imediato
    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
    }

    try:
        # Executa a busca de forma assíncrona para não bloquear o loop de eventos
        def perform_search():
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(f"ytsearch5:{query}", download=False)

        info = await asyncio.to_thread(perform_search)
        entries = info.get("entries", [])

        if not entries:
            await status_msg.edit_text("❌ Nenhuma música encontrada. Tente outros termos.")
            return

        # Guarda os resultados da busca associados ao ID do usuário
        SEARCH_RESULTS[user_id] = {}
        keyboard = []

        for idx, entry in enumerate(entries):
            res_id = str(idx)
            title = entry.get("title", "Sem título")
            uploader = entry.get("uploader", "Desconhecido")
            url = entry.get("url") or entry.get("webpage_url")

            SEARCH_RESULTS[user_id][res_id] = {
                "url": url,
                "title": title,
                "uploader": uploader,
            }

            button_text = f"🎵 {title[:40]}... - {uploader[:15]}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"dl_{res_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text("Escolha uma das opções abaixo para baixar:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro na busca: {e}")
        await status_msg.edit_text("⚠️ Ocorreu um erro ao realizar a busca. Tente novamente.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa o clique nos botões inline e realiza o download/envio."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if not data.startswith("dl_"):
        return

    res_id = data.split("_")[1]
    user_data = SEARCH_RESULTS.get(user_id, {}).get(res_id)

    if not user_data:
        await query.edit_message_text("⚠️ Busca expirada. Por favor, faça uma nova pesquisa.")
        return

    track_url = user_data["url"]
    track_title = user_data["title"]
    track_uploader = user_data["uploader"]

    await query.edit_message_text(f"⏳ Baixando '{track_title}'... Por favor, aguarde.")

    output_filename = f"audio_{user_id}_{res_id}"
    output_template = f"{output_filename}.%(ext)s"

    ydl_download_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_filename,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
    }

    final_mp3_path = f"{output_filename}.mp3"

    try:
        # Download do áudio de forma assíncrona
        def perform_download():
            with YoutubeDL(ydl_download_opts) as ydl:
                ydl.download([track_url])

        await asyncio.to_thread(perform_download)

        # Envio do arquivo via send_audio
        if os.path.exists(final_mp3_path):
            with open(final_mp3_path, "rb") as audio_file:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=audio_file,
                    title=track_title,
                    performer=track_uploader,
                )
            await query.delete_message()
        else:
            await query.edit_message_text("❌ Falha ao processar o arquivo de áudio.")

    except Exception as e:
        logger.error(f"Erro no download/envio: {e}")
        await query.edit_message_text("❌ Ocorreu um erro ao baixar este áudio.")

    finally:
        # Remoção do arquivo local para economizar armazenamento
        if os.path.exists(final_mp3_path):
            os.remove(final_mp3_path)


def main():
    """Inicia o bot."""
    if TOKEN == "SEU_TOKEN_AQUI":
        raise ValueError("Defina a variável de ambiente TELEGRAM_TOKEN ou insira o token diretamente no código.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_music))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()