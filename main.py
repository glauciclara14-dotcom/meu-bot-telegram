import os
import json
import re
import unidecode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from flask import Flask, request, jsonify

# --- CONFIGURAÇÕES ---
# O token do bot agora será carregado de uma variável de ambiente,
# o que é mais seguro do que deixá-lo no código.
TOKEN_BOT = os.environ.get("BOT_TOKEN")

USUARIO_ADMIN = "@AllanSilvaSantos"
CHAVE_PIX = "14958298711"
NOME_RECEBEDOR = "Turbo Streaming VIP"
CIDADE_RECEBEDOR = "RIO DE JANEIRO"

USUARIOS_JSON = "usuarios.json"

# --- STREAMINGS (nome, descricao, valor) ---
STREAMINGS = {
    "stream1": {"nome": "0101 - CLARO TV + COMPLETO TELA - R$23,00", "descricao": "Todos os canais e filmes liberados para você curtir! 💻", "valor": 23.00},
    "stream2": {"nome": "0102 - PRIME VÍDEO - R$13,00", "descricao": "Filmes, canais e esportes para você e toda a sua família! 💻", "valor": 13.00},
    # ... (adicione todos os seus streamings aqui) ...
}

# --- FUNÇÕES DE ARMAZENAMENTO ---

def carregar_usuarios():
    if os.path.exists(USUARIOS_JSON):
        with open(USUARIOS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def salvar_usuarios(usuarios):
    with open(USUARIOS_JSON, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, indent=2, ensure_ascii=False)

# --- FUNÇÕES PIX ---

def monta_campo(id_campo, valor):
    valor_str = str(valor)
    tamanho = len(valor_str)
    return f"{id_campo}{tamanho:02}{valor_str}"

def calcula_crc16(payload: str) -> str:
    crc = 0xFFFF
    for c in payload.encode('utf-8'):
        crc ^= c << 8
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def limpar_txid(txid):
    txid_clean = re.sub(r'[^A-Za-z0-9]', '', txid)[:25]
    return txid_clean

def gerar_pix_copia_cola(chave_pix, valor, descricao, txid):
    valor_str = f"{valor:.2f}"
    txid_limpo = limpar_txid(txid)
    nome_clean = unidecode.unidecode(NOME_RECEBEDOR).upper()
    cidade_clean = unidecode.unidecode(CIDADE_RECEBEDOR).upper()

    payload = ""
    payload += monta_campo("00", "01")  # Payload Format Indicator
    payload += monta_campo(
        "26",
        monta_campo("00", "BR.GOV.BCB.PIX") +
        monta_campo("01", chave_pix)
    )
    payload += monta_campo("52", "0000")
    payload += monta_campo("53", "986")
    payload += monta_campo("54", valor_str)
    payload += monta_campo("58", "BR")
    payload += monta_campo("59", nome_clean)
    payload += monta_campo("60", cidade_clean)
    payload += monta_campo("62", monta_campo("05", txid_limpo))

    payload += "6304"
    crc = calcula_crc16(payload)
    payload += crc

    return payload

# --- FUNÇÕES DE MENU ---

def menu_principal():
    keyboard = [
        [InlineKeyboardButton("🏅 Assinaturas Premium", callback_data="abrir_streamings")],
        [InlineKeyboardButton("💰 Fazer Recarga", callback_data="fazer_recarga")],
        [InlineKeyboardButton("👤 Perfil", callback_data="ver_perfil")],
        [InlineKeyboardButton("🛠 Suporte", url=f"https://t.me/{USUARIO_ADMIN.lstrip('@')}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_streamings_menu():
    keyboard = []
    for key, info in STREAMINGS.items():
        keyboard.append([InlineKeyboardButton(info["nome"], callback_data=f"detalhes_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")])
    return InlineKeyboardMarkup(keyboard)

def build_detalhes_menu(stream_key):
    stream = STREAMINGS[stream_key]
    texto = f"🛍 SERVIÇO: *{stream['nome']}*\n💸 VALOR: R$ {stream['valor']:.2f}"
    keyboard = [
        [InlineKeyboardButton("⚡ Comprar", callback_data=f"comprar_{stream_key}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="abrir_streamings")],
    ]
    return texto, InlineKeyboardMarkup(keyboard)

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    usuarios = carregar_usuarios()

    if chat_id not in usuarios:
        usuarios[chat_id] = {
            "nome": update.effective_user.full_name,
            "username": update.effective_user.username or "",
            "saldo": 0.0,
            "logins_comprados": 0,
            "pix_inseridos": 0.0,
        }
        salvar_usuarios(usuarios)

    user = usuarios[chat_id]
    texto = (
        f"Olá, *{user['nome']}* (@{user['username']})\n\n"
        f"ID: `{chat_id}`\n"
        f"Saldo Atual: *R$ {user['saldo']:.2f}*\n\n"
        "🔥 Seja bem-vindo(a) à Turbo Streaming VIP 🔥\n\n"
        "✅ Mais barato que o plano oficial\n"
        "✅ Acesso imediato\n"
        "✅ 100% seguro e confiável\n\n"
        "Escolha uma opção abaixo para começar:"
    )

    if os.path.exists("logo_bot.png"):
        with open("logo_bot.png", "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=texto,
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
    else:
        await update.message.reply_text(
            texto,
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = str(query.message.chat.id)

    usuarios = carregar_usuarios()
    user = usuarios.get(chat_id)
    if not user:
        usuarios[chat_id] = {
            "nome": query.from_user.full_name,
            "username": query.from_user.username or "",
            "saldo": 0.0,
            "logins_comprados": 0,
            "pix_inseridos": 0.0,
        }
        user = usuarios[chat_id]
        salvar_usuarios(usuarios)

    if data == "abrir_streamings":
        texto = (
            "🏅 Temos o que você precisa em termos de Assinaturas Premium!\n\n"
            "👌 Aqui você contrata com total qualidade.\n"
            "🛡 Pagamentos via saldo garantem agilidade e segurança.\n\n"
            "✅ Escolha seu streaming e divirta-se!"
        )
        await query.edit_message_text(texto, reply_markup=build_streamings_menu())
        return

    elif data.startswith("detalhes_"):
        stream_key = data.split("_")[1]
        texto, teclado = build_detalhes_menu(stream_key)
        await query.edit_message_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    elif data == "voltar_menu":
        texto = (
            f"Olá, *{user['nome']}* (@{user['username']})\n\n"
            f"ID: `{chat_id}`\n"
            f"Saldo Atual: *R$ {user['saldo']:.2f}*\n\n"
            "🔥 Seja bem-vindo(a) à Turbo Streaming VIP 🔥\n\n"
            "✅ Mais barato que o plano oficial\n"
            "✅ Acesso imediato\n"
            "✅ 100% seguro e confiável\n\n"
            "Escolha uma opção abaixo para começar:"
        )
        await query.edit_message_text(texto, reply_markup=menu_principal(), parse_mode="Markdown")
        return

    elif data == "fazer_recarga":
        texto = (
            "💰 Para recarregar seu saldo, envie o valor desejado em reais (exemplo: 30.00).\n"
            "Após isso, você receberá o código PIX para pagamento."
        )
        await query.edit_message_text(texto)
        context.user_data["recarga_ativa"] = True
        return

    elif data == "ver_perfil":
        texto = (
            f"👤 *Perfil do Usuário*\n\n"
            f"Nome: {user['nome']}\n"
            f"Username: @{user['username']}\n"
            f"ID: {chat_id}\n\n"
            f"💰 *Carteira*\n"
            f"Saldo Atual: R$ {user['saldo']:.2f}\n\n"
            f"🛒 *Compras*\n"
            f"Logins Comprados: {user['logins_comprados']}\n"
            f"PIX Inseridos: R$ {user['pix_inseridos']:.2f}\n"
        )
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=menu_principal())
        return

    elif data.startswith("comprar_"):
        stream_key = data.split("_")[1]
        stream = STREAMINGS.get(stream_key)
        if not stream:
            await query.answer("Streaming não encontrado.", show_alert=True)
            return

        valor = stream["valor"]
        if user["saldo"] < valor:
            falta = valor - user["saldo"]
            await query.answer(f"❌ Saldo insuficiente! Faltam R$ {falta:.2f}. Faça recarga e tente novamente.", show_alert=True)
            return

        user["saldo"] -= valor
        user["logins_comprados"] += 1
        salvar_usuarios(usuarios)

        admin_id = await get_admin_chat_id_async(context)
        if admin_id:
            texto_admin = (
                f"🛒 *Nova Compra*\n"
                f"Usuário: {user['nome']} (@{user['username']})\n"
                f"ID: {chat_id}\n"
                f"Streaming: {stream['nome']}\n"
                f"Valor: R$ {valor:.2f}\n"
                f"Saldo Atual do Usuário: R$ {user['saldo']:.2f}\n\n"
                "⚠️ Compre do fornecedor e envie o acesso para o cliente!"
            )
            await context.bot.send_message(admin_id, texto_admin, parse_mode="Markdown")

        await query.edit_message_text(
            f"✅ Compra realizada com sucesso!\n\n"
            f"Streaming: {stream['nome']}\n"
            f"Valor debitado: R$ {valor:.2f}\n"
            f"Saldo atual: R$ {user['saldo']:.2f}\n\n"
            "Aguarde o envio do acesso pelo administrador."
        )
        return

    else:
        await query.answer("Opção inválida.", show_alert=True)

async def texto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    usuarios = carregar_usuarios()
    user = usuarios.get(chat_id)
    text = update.message.text.strip()

    if context.user_data.get("recarga_ativa"):
        try:
            valor = float(text.replace(",", "."))
            if valor <= 0:
                raise ValueError
        except:
            await update.message.reply_text("❌ Valor inválido. Por favor, envie um número válido para a recarga (ex: 30.00).")
            return

        txid = f"recarga_{chat_id}"
        pix_code = gerar_pix_copia_cola(CHAVE_PIX, valor, "Recarga Turbo Streaming VIP", txid)
        context.user_data["recarga_valor"] = valor
        context.user_data["recarga_pix"] = pix_code
        context.user_data["recarga_ativa"] = False
        context.user_data["aguardando_comprovante"] = True

        texto_pix = (
            f"💰 Para recarregar R$ {valor:.2f}, faça o pagamento via PIX usando o código abaixo:\n\n"
            f"`{pix_code}`\n\n"
            "⚠️ Após o pagamento, envie o comprovante (foto ou texto) aqui neste chat."
        )
        await update.message.reply_text(texto_pix, parse_mode="Markdown")
        return

    if context.user_data.get("aguardando_comprovante"):
        if update.message.photo or (update.message.text and not update.message.text.startswith("/")):
            valor = context.user_data.get("recarga_valor")
            if not valor:
                await update.message.reply_text("❌ Erro no valor da recarga, por favor recomece o processo.")
                context.user_data["aguardando_comprovante"] = False
                return

            file_id = None
            if update.message.photo:
                file_id = update.message.photo[-1].file_id

            admin_id = await get_admin_chat_id_async(context)
            texto_admin = (
                f"💳 *Nova recarga solicitada*\n"
                f"Usuário: {user['nome']} (@{user['username']})\n"
                f"ID: {chat_id}\n"
                f"Valor: R$ {valor:.2f}\n\n"
                "Envie /confirmar_recarga {chat_id} {valor} para aprovar."
            )
            await context.bot.send_message(admin_id, texto_admin, parse_mode="Markdown")
            if file_id:
                await context.bot.send_photo(admin_id, file_id)

            await update.message.reply_text("✅ Comprovante recebido! Agora aguarde a confirmação do administrador.")
            context.user_data["aguardando_comprovante"] = False
            return
        else:
            await update.message.reply_text("❌ Por favor, envie uma foto ou texto válido como comprovante.")
            return

    await update.message.reply_text("👋 Use o menu para navegar. Digite /start para começar.")

async def confirmar_recarga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = await get_admin_chat_id_async(context)
    user_id = update.effective_user.id
    if user_id != admin_id:
        await update.message.reply_text("❌ Comando disponível apenas para o administrador.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Uso correto: /confirmar_recarga <chat_id> <valor>")
        return

    chat_id, valor_str = args
    usuarios = carregar_usuarios()
    user = usuarios.get(chat_id)
    if not user:
        await update.message.reply_text("❌ Usuário não encontrado.")
        return

    try:
        valor = float(valor_str)
    except:
        await update.message.reply_text("❌ Valor inválido.")
        return

    user["saldo"] += valor
    user["pix_inseridos"] += valor
    salvar_usuarios(usuarios)

    await update.message.reply_text(f"✅ Saldo de R$ {valor:.2f} creditado para o usuário {user['nome']} (ID: {chat_id}).")

    await context.bot.send_message(chat_id, f"✅ Sua recarga de R$ {valor:.2f} foi confirmada e o saldo está disponível.")

async def enviar_acesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = await get_admin_chat_id_async(context)
    user_id = update.effective_user.id
    if user_id != admin_id:
        await update.message.reply_text("❌ Comando disponível apenas para o administrador.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso correto: /enviar_acesso <chat_id> <mensagem>")
        return

    chat_id = args[0]
    mensagem = " ".join(args[1:])

    try:
        await context.bot.send_message(chat_id, mensagem)
        await update.message.reply_text(f"✅ Mensagem enviada para {chat_id}.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar mensagem: {e}")

# --- Função para recuperar admin chat_id do arquivo ---
async def get_admin_chat_id_async(context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists("admin_chat_id.txt"):
        with open("admin_chat_id.txt", "r") as f:
            id_str = f.read().strip()
            if id_str.isdigit():
                return int(id_str)
    return None

async def set_admin_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.username != USUARIO_ADMIN.lstrip("@"):
        await update.message.reply_text("❌ Você não é o administrador autorizado.")
        return

    chat_id = update.effective_chat.id
    with open("admin_chat_id.txt", "w") as f:
        f.write(str(chat_id))
    await update.message.reply_text(f"✅ Chat ID do administrador salvo: {chat_id}")


# --- CONFIGURAÇÃO PARA WEBHOOKS ---
app = Flask(__name__)
# O TOKEN_BOT será injetado pela Railway de forma segura
application = ApplicationBuilder().token(TOKEN_BOT).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("confirmar_recarga", confirmar_recarga))
application.add_handler(CommandHandler("enviar_acesso", enviar_acesso))
application.add_handler(CommandHandler("salvar_admin", set_admin_chat_id))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(MessageHandler(filters=(filters.TEXT | filters.PHOTO), callback=texto_handler))

@app.route("/", methods=["GET", "POST"])
def webhook_handler():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.dispatcher.process_update(update)
    return jsonify({"status": "ok"})

# --- FIM DA CONFIGURAÇÃO WEBHOOKS ---

def main():
    print("O bot está pronto para receber webhooks.")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)