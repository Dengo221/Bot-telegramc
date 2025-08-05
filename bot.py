import os
import telebot
from telebot import types
import threading
import time
import json
import uuid
import re
import shutil
from requests.exceptions import ConnectionError, ReadTimeout

# =================================================================================
# --- CONFIGURAÇÃO PRINCIPAL ---
# =================================================================================
BOT_TOKEN = '7989480763:AAF70BVLtgDPQb02ZcU0H0344quLBJVKeUc' 
ADMIN_ID = 7731277691
GRUPO_LINK = "https://t.me/CT_GOMES_SEARCH"
DIRETORIO_DE_BUSCA = 'database'
DIRETORIO_CACHE = 'cache'

# =================================================================================
# --- CONFIGURAÇÃO DO SISTEMA DE CRÉDITOS ---
# =================================================================================
MEMBROS_POR_CREDITO_LOTE = 10
CREDITOS_GANHOS_POR_LOTE = 5
CUSTO_POR_PESQUISA = 1
CREDITOS_INICIAIS_GRATIS = 5

# =================================================================================
# --- ARQUIVOS DE DADOS ---
# =================================================================================
CREDITOS_FILE = 'user_credits.json'
REFERRAL_FILE = 'user_referrals.json'
GIFTS_FILE = 'gift_cards.json'
USERS_FILE = 'users.json'
VIPS_FILE = 'vips.json'
GROUPS_FILE = 'monitored_groups.json'

# =================================================================================
# --- INICIALIZAÇÃO DO BOT ---
# =================================================================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')

# =================================================================================
# --- FUNÇÕES DE GERENCIAMENTO DE DADOS ---
# =================================================================================
def load_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_data(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def get_user_credits(user_id):
    return load_data(CREDITOS_FILE).get(str(user_id), 0)

def add_user_credits(user_id, amount):
    credits_data = load_data(CREDITOS_FILE)
    current_credits = credits_data.get(str(user_id), 0)
    credits_data[str(user_id)] = current_credits + amount
    save_data(credits_data, CREDITOS_FILE)
    return credits_data[str(user_id)]

def use_credit(user_id):
    if get_user_credits(user_id) >= CUSTO_POR_PESQUISA:
        add_user_credits(user_id, -CUSTO_POR_PESQUISA)
        return True
    return False

def save_user_info(user):
    users_data = load_data(USERS_FILE)
    user_id_str = str(user.id)
    if user_id_str not in users_data:
        users_data[user_id_str] = user.first_name
        save_data(users_data, USERS_FILE)
        return True
    return False

def is_vip(user_id):
    return str(user_id) in load_data(VIPS_FILE)

def toggle_vip(user_id):
    vips_data = load_data(VIPS_FILE)
    user_id_str = str(user_id)
    if user_id_str in vips_data:
        del vips_data[user_id_str]
        new_status = False
    else:
        vips_data[user_id_str] = True
        new_status = True
    save_data(vips_data, VIPS_FILE)
    return new_status

def get_monitored_groups():
    return load_data(GROUPS_FILE).get('groups', [])

def add_monitored_group(group_id):
    groups_data = load_data(GROUPS_FILE)
    if 'groups' not in groups_data: groups_data['groups'] = []
    if group_id not in groups_data['groups']:
        groups_data['groups'].append(group_id)
        save_data(groups_data, GROUPS_FILE)
        return True
    return False

def remove_monitored_group(group_id):
    groups_data = load_data(GROUPS_FILE)
    if 'groups' in groups_data and group_id in groups_data['groups']:
        groups_data['groups'].remove(group_id)
        save_data(groups_data, GROUPS_FILE)
        return True
    return False

# =================================================================================
# --- LÓGICA DE BUSCA (COM FILTRAGEM) ---
# =================================================================================
def is_url(text):
    return re.search(r"https?://|www\.", text)

def clean_line(line, filter_type):
    """Lógica de extração do Anomaly, agora com um filtro aplicado."""
    line = line.strip()
    for sep in ['|', '/', ' ', '>']:
        line = line.replace(sep, ':')
    
    parts = line.split(':')
    parts = [p.strip() for p in parts if p.strip()]
    
    if len(parts) < 2:
        return None
        
    if any(is_url(p) for p in parts):
        parts = [p for p in parts if not is_url(p)]
        
    if len(parts) >= 2:
        username, password = parts[-2], parts[-1]
    else:
        return None
        
    if not (3 <= len(username) <= 64 and 3 <= len(password) <= 64):
        return None
    
    # Aplica o filtro solicitado pelo usuário
    if filter_type == 'email':
        if '@' not in username:
            return None
    elif filter_type == 'numero':
        # Permite um '+' opcional no início, mas o resto deve ser número
        if not username.replace('+', '', 1).isdigit():
            return None
    elif filter_type == 'usuario':
        if '@' in username or username.replace('+', '', 1).isdigit():
            return None
    # Se o filtro for 'todos', não faz nada e aceita qualquer tipo

    return f"{username}:{password}"

def scan_file(file_path, keyword, filter_type, chunk_size=16777216):
    """Escaneia um único arquivo de forma robusta, passando o filtro."""
    found_lines = set()
    encodings = ['utf-8', 'ISO-8859-1', 'latin1', 'windows-1252']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
                buffer = ""
                while True:
                    chunk = file.read(chunk_size)
                    if not chunk:
                        if buffer and keyword.lower() in buffer.lower():
                            for line in buffer.splitlines():
                                if keyword.lower() in line.lower():
                                    cleaned = clean_line(line, filter_type)
                                    if cleaned:
                                        found_lines.add(cleaned)
                        break
                    
                    buffer += chunk
                    lines = buffer.splitlines(keepends=True)
                    
                    if not lines[-1].endswith(('\n', '\r')):
                        buffer = lines.pop()
                    else:
                        buffer = ""

                    for line in lines:
                        if keyword.lower() in line.lower():
                            cleaned = clean_line(line, filter_type)
                            if cleaned:
                                found_lines.add(cleaned)
            break
        except Exception:
            continue
    return found_lines

def search_in_directory(chat_id, message_id, keyword, filter_type):
    try:
        # Adapta o nome do arquivo de cache para incluir o filtro
        keyword_filename = re.sub(r'[\\/*?:"<>|]', "", keyword)
        cache_filename = f"{keyword_filename}_{filter_type}.txt"
        cache_filepath = os.path.join(DIRETORIO_CACHE, cache_filename)

        if os.path.exists(cache_filepath):
            bot.edit_message_text(f"⚡️ **Resultado encontrado no cache!**\nEnviando instantaneamente...", chat_id, message_id)
            with open(cache_filepath, 'rb') as f:
                total_logins = sum(1 for _ in f)
                f.seek(0)
                caption = (
                    f"📄 **Resultados para `{keyword}`** (Filtro: {filter_type})\n\n"
                    f"▪️ **Logins Encontrados:** `{total_logins}`\n"
                    f"ℹ️ _Cache! Para uma nova busca, use /limparcache._"
                )
                bot.send_document(chat_id, f, caption=caption)
            bot.delete_message(chat_id, message_id)
            return
        
        start_time = time.time()
        bot.edit_message_text(f"🔍 **Iniciando busca profunda...**\nFiltro aplicado: `{filter_type}`. Isso pode levar um tempo.", chat_id, message_id)

        if not os.path.isdir(DIRETORIO_DE_BUSCA):
            bot.edit_message_text(f"❌ **Erro Crítico:** O diretório `{DIRETORIO_DE_BUSCA}` não foi encontrado.", chat_id, message_id)
            return

        txt_files = [os.path.join(DIRETORIO_DE_BUSCA, f) for f in os.listdir(DIRETORIO_DE_BUSCA) if f.endswith('.txt')]
        if not txt_files:
            bot.edit_message_text(f"❌ **Erro:** Nenhum arquivo `.txt` encontrado em `{DIRETORIO_DE_BUSCA}`.", chat_id, message_id)
            return

        all_found_lines = set()
        total_files = len(txt_files)
        
        for i, file_path in enumerate(txt_files):
            progress = ((i + 1) / total_files) * 100
            try:
                bot.edit_message_text(
                    f"👨‍💻 **Buscando por `{keyword}`...** (Filtro: {filter_type})\n\n"
                    f"▪️ Arquivos Verificados: {i+1}/{total_files}\n"
                    f"⏳ Progresso: {progress:.0f}%",
                    chat_id, message_id
                )
            except telebot.apihelper.ApiTelegramException as e:
                if 'message is not modified' not in str(e): print(f"Erro ao editar mensagem: {e}")
            
            all_found_lines.update(scan_file(file_path, keyword, filter_type))

        duration = time.time() - start_time
        
        bot.edit_message_text("✅ **Busca Finalizada!**\nPreparando e salvando os resultados...", chat_id, message_id)

        if not all_found_lines:
            bot.send_message(chat_id, f"🤷‍♂️ Nenhum resultado encontrado para: `{keyword}` com o filtro `{filter_type}`.")
            bot.delete_message(chat_id, message_id)
            return

        sorted_results = sorted(list(all_found_lines))

        with open(cache_filepath, 'w', encoding='utf-8') as f:
            for line in sorted_results:
                f.write(line + '\n')

        with open(cache_filepath, 'rb') as f:
            caption = (
                f"📄 **Resultados para `{keyword}`** (Filtro: {filter_type})\n\n"
                f"▪️ **Logins Encontrados:** `{len(sorted_results)}`\n"
                f"▪️ **Duração da Busca:** `{duration:.2f} segundos`"
            )
            bot.send_document(chat_id, f, caption=caption)
        
        bot.delete_message(chat_id, message_id)

    except Exception as e:
        print(f"Erro na busca: {e}")
        try:
            bot.edit_message_text(f"🚨 **Ocorreu um erro inesperado durante a busca.**\n\n`{e}`", chat_id, message_id)
        except Exception as inner_e:
            print(f"Erro ao enviar mensagem de erro: {inner_e}")
            bot.send_message(chat_id, "🚨 Ocorreu um erro crítico na busca.")

# =================================================================================
# --- VERIFICADOR DE MEMBRO DO GRUPO ---
# =================================================================================
def check_membership(func):
    def wrapper(message_or_call):
        user = message_or_call.from_user
        chat_id = message_or_call.message.chat.id if isinstance(message_or_call, types.CallbackQuery) else message_or_call.chat.id
        save_user_info(user)
        
        monitored_groups = get_monitored_groups()
        if not monitored_groups:
            bot.send_message(chat_id, "⚠️ Nenhum grupo de verificação configurado. Contate o administrador.")
            return

        is_member = False
        for group_id in monitored_groups:
            try:
                member = bot.get_chat_member(group_id, user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    is_member = True
                    break 
            except Exception:
                continue

        if is_member:
            func(message_or_call)
        else:
            send_join_message(chat_id)
            
    return wrapper

def send_join_message(chat_id):
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➡️ Entrar no Grupo Principal", url=GRUPO_LINK))
    bot.send_message(chat_id, "**❌ Acesso Negado!**\n\nVocê precisa ser membro de um dos nossos grupos parceiros para usar o bot.", reply_markup=markup)

# =================================================================================
# --- COMANDOS DO BOT ---
# =================================================================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    is_new_user = save_user_info(user)
    
    welcome_message = "🤖 **Bem-vindo(a) de volta!**\n\nDigite /ajuda para ver os comandos disponíveis."
    if is_new_user:
        add_user_credits(user.id, CREDITOS_INICIAIS_GRATIS)
        welcome_message = f"🤖 **Bem-vindo(a), {user.first_name}!**\n\nVocê ganhou `{CREDITOS_INICIAIS_GRATIS}` créditos grátis para começar!\n\nDigite /ajuda para aprender a usar o bot."

    credits = get_user_credits(user.id)
    vip_status = " (VIP ✨)" if is_vip(user.id) else ""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"💰 Meus Créditos ({credits}){vip_status}", callback_data='my_credits'),
        types.InlineKeyboardButton("🎁 Resgatar Código", callback_data='redeem_gift'),
        types.InlineKeyboardButton("ℹ️ Ajuda", callback_data='show_help'),
        types.InlineKeyboardButton("🔗 Nosso Grupo", url=GRUPO_LINK),
        types.InlineKeyboardButton("👨‍💻 Suporte", url=f"tg://user?id={ADMIN_ID}")
    )
    bot.reply_to(message, welcome_message, reply_markup=markup)

@bot.message_handler(commands=['ajuda'])
def command_help(message):
    help_text = (
        "ℹ️ **Como Usar o Bot**\n\n"
        "Meu principal comando é o `/pesquisar`.\n\n"
        "1. Digite o comando seguido da palavra-chave.\n"
        "   *Exemplo:* `/pesquisar netflix.com`\n\n"
        "2. O bot irá te perguntar qual tipo de login você quer.\n"
        "3. Clique no botão correspondente (Email, Usuário, etc.) para iniciar a busca.\n\n"
        "**Outros Comandos:**\n"
        "`/start` - Inicia o bot e mostra o menu.\n"
        "`/resgatar <code>` - Resgata um código de presente.\n"
        "`/ajuda` - Mostra esta mensagem de ajuda."
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['pesquisar'])
@check_membership
def handle_search(message):
    user_id = message.from_user.id
    
    if not is_vip(user_id):
        if get_user_credits(user_id) < CUSTO_POR_PESQUISA:
            bot.reply_to(message, f"⚠️ **Créditos Insuficientes!**\n\nVocê precisa de `{CUSTO_POR_PESQUISA}` crédito(s) para pesquisar.")
            return
        # O crédito só será debitado quando a busca realmente começar (após clicar no botão)
    
    try:
        keyword = message.text.split(maxsplit=1)[1]
    except IndexError:
        bot.reply_to(message, "⚠️ **Uso incorreto!**\n\n*Exemplo: `/pesquisar google.com`*\n\nDigite /ajuda para mais informações.")
        return

    # Cria o menu de opções de filtro
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📧 Email:Senha", callback_data=f"filter_email_{keyword}"),
        types.InlineKeyboardButton("👤 Usuário:Senha", callback_data=f"filter_usuario_{keyword}"),
        types.InlineKeyboardButton("📞 Número:Senha", callback_data=f"filter_numero_{keyword}"),
        types.InlineKeyboardButton("🌐 Todos os Tipos", callback_data=f"filter_todos_{keyword}")
    )
    bot.reply_to(message, f"🔎 **Qual tipo de login você deseja para `{keyword}`?**\n\nSelecione uma opção abaixo para iniciar a busca.", reply_markup=markup)

@bot.message_handler(commands=['resgatar'])
@check_membership
def handle_redeem_command(message):
    try:
        code = message.text.split(maxsplit=1)[1]
        redeem_gift_code(message.from_user, code)
    except IndexError:
        bot.reply_to(message, "⚠️ **Uso incorreto!**\n*Ex: `/resgatar MEU-CODIGO-123`*")

# =================================================================================
# --- DETECÇÃO DE NOVOS MEMBROS ---
# =================================================================================
@bot.message_handler(content_types=['new_chat_members'])
def new_member_handler(message):
    if message.chat.id not in get_monitored_groups(): return
    adder = message.from_user
    save_user_info(adder)
    added_members_count = len([m for m in message.new_chat_members if not m.is_bot and m.id != adder.id])
    if added_members_count == 0: return
    referrals_data = load_data(REFERRAL_FILE)
    user_referrals = referrals_data.get(str(adder.id), 0) + added_members_count
    if user_referrals >= MEMBROS_POR_CREDITO_LOTE:
        lotes_ganhos = user_referrals // MEMBROS_POR_CREDITO_LOTE
        creditos_a_adicionar = lotes_ganhos * CREDITOS_GANHOS_POR_LOTE
        new_total_credits = add_user_credits(adder.id, creditos_a_adicionar)
        referrals_data[str(adder.id)] = user_referrals % MEMBROS_POR_CREDITO_LOTE
        try:
            bot.send_message(adder.id, f"🎉 **Parabéns!**\nVocê adicionou membros e ganhou `+{creditos_a_adicionar}` créditos!\nSeu saldo agora é de `{new_total_credits}`.")
        except Exception:
            bot.send_message(message.chat.id, f"🎉 Parabéns, {adder.first_name}! Você ganhou `+{creditos_a_adicionar}` créditos por adicionar novos membros!")
    else:
        referrals_data[str(adder.id)] = user_referrals
    save_data(referrals_data, REFERRAL_FILE)

# =================================================================================
# --- PAINEL DE ADMINISTRAÇÃO E CALLBACKS ---
# =================================================================================
@bot.message_handler(commands=['limparcache'], func=lambda msg: msg.from_user.id == ADMIN_ID)
def clear_cache_command(message):
    try:
        if os.path.exists(DIRETORIO_CACHE):
            shutil.rmtree(DIRETORIO_CACHE)
            os.makedirs(DIRETORIO_CACHE)
            bot.reply_to(message, "✅ **Cache limpo com sucesso!**\nTodas as próximas buscas serão feitas diretamente na base de dados.")
        else:
            os.makedirs(DIRETORIO_CACHE)
            bot.reply_to(message, "ℹ️ A pasta de cache foi criada. Nenhuma ação de limpeza foi necessária.")
    except Exception as e:
        bot.reply_to(message, f"🚨 **Erro ao limpar o cache:**\n`{e}`")

@bot.message_handler(commands=['admin'], func=lambda msg: msg.from_user.id == ADMIN_ID)
def admin_panel(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Divulgar Mensagem", callback_data='admin_broadcast'),
        types.InlineKeyboardButton("🎁 Gerar Gift Card", callback_data='admin_gen_gift'),
        types.InlineKeyboardButton("🗑️ Limpar Cache de Buscas", callback_data='admin_clear_cache'),
        types.InlineKeyboardButton("👥 Gerenciar Usuários", callback_data='admin_list_users_0'),
        types.InlineKeyboardButton("✨ Gerenciar VIPs", callback_data='admin_list_vips_0'),
        types.InlineKeyboardButton("🌐 Gerenciar Grupos", callback_data='admin_manage_groups'),
        types.InlineKeyboardButton("📊 Estatísticas do Bot", callback_data='admin_stats')
    )
    bot.reply_to(message, "👑 **Painel de Administração** 👑\n\nSelecione uma opção:", reply_markup=markup)

def ask_for_broadcast_message(message):
    if message.text == '/cancelar':
        bot.send_message(message.chat.id, "Divulgação cancelada.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👤 Para todos os USUÁRIOS", callback_data='broadcast_to_users'),
        types.InlineKeyboardButton("🌐 Para todos os GRUPOS", callback_data='broadcast_to_groups'),
        types.InlineKeyboardButton("↩️ Cancelar", callback_data='admin_back_from_broadcast')
    )
    try:
        fwd_msg = bot.forward_message(message.chat.id, message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "Para quem você deseja enviar esta mensagem?", reply_markup=markup)
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ocorreu um erro ao processar a mensagem: {e}")

def broadcast_message_thread(target, message_to_forward):
    if target == 'users':
        chat_ids = load_data(USERS_FILE).keys()
        target_name = "usuários"
    else: # groups
        chat_ids = get_monitored_groups()
        target_name = "grupos"

    if not chat_ids:
        bot.send_message(ADMIN_ID, f"❌ Nenhum {target_name} encontrado para enviar a mensagem.")
        return

    total = len(chat_ids)
    sent_count = 0
    failed_count = 0
    
    status_msg = bot.send_message(ADMIN_ID, f"📢 Iniciando envio para `{total}` {target_name}...")

    for i, chat_id in enumerate(chat_ids):
        try:
            bot.forward_message(chat_id, from_chat_id=message_to_forward.chat.id, message_id=message_to_forward.message_id)
            sent_count += 1
        except Exception:
            failed_count += 1
        
        if i > 0 and i % 20 == 0:
            time.sleep(1)

    bot.edit_message_text(
        f"✅ **Divulgação Concluída!**\n\n▪️ **Enviado com sucesso:** `{sent_count}`\n▪️ **Falhas:** `{failed_count}`",
        chat_id=ADMIN_ID,
        message_id=status_msg.message_id
    )
    bot.delete_message(message_to_forward.chat.id, message_to_forward.message_id)

def redeem_gift_code(user, code):
    gifts_data = load_data(GIFTS_FILE)
    if code in gifts_data and gifts_data[code]['active']:
        amount = gifts_data[code]['credits']
        new_total = add_user_credits(user.id, amount)
        gifts_data[code]['active'] = False
        gifts_data[code]['redeemed_by'] = f"{user.first_name} ({user.id})"
        save_data(gifts_data, GIFTS_FILE)
        bot.send_message(user.id, f"✅ **Código resgatado!**\nVocê ganhou `+{amount}` créditos.\nSeu novo saldo é de `{new_total}`.")
    else:
        bot.send_message(user.id, "❌ **Código inválido ou já utilizado!**")

def ask_for_gift_amount(message):
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError()
        gifts_data = load_data(GIFTS_FILE)
        code = f"GIFT-{str(uuid.uuid4().hex[:8]).upper()}"
        gifts_data[code] = {"credits": amount, "active": True, "redeemed_by": None}
        save_data(gifts_data, GIFTS_FILE)
        bot.reply_to(message, f"✅ **Gift Card gerado!**\n\nCódigo: `{code}`\nValor: `{amount}` créditos")
    except (ValueError, TypeError):
        bot.reply_to(message, "❌ Valor inválido. Insira um número positivo.")

def ask_for_credits_change(message, user_id_to_edit):
    try:
        amount = int(message.text)
        new_total = add_user_credits(user_id_to_edit, amount)
        user_name = load_data(USERS_FILE).get(str(user_id_to_edit), f"ID {user_id_to_edit}")
        bot.reply_to(message, f"✅ Créditos alterados para **{user_name}**.\nNovo saldo: `{new_total}`.")
    except (ValueError, TypeError):
        bot.reply_to(message, "❌ Entrada inválida. Envie um número (ex: `50` ou `-10`).")

def show_user_list(chat_id, message_id, page, is_edit=True):
    users_data = load_data(USERS_FILE)
    credits_data = load_data(CREDITOS_FILE)
    if not users_data:
        bot.edit_message_text("Nenhum usuário encontrado.", chat_id, message_id)
        return
    users_list = list(users_data.items())
    items_per_page = 5
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    paginated_users = users_list[start_index:end_index]
    markup = types.InlineKeyboardMarkup(row_width=1)
    for user_id, user_name in paginated_users:
        credits = credits_data.get(user_id, 0)
        vip_status = " (VIP ✨)" if is_vip(user_id) else ""
        markup.add(types.InlineKeyboardButton(f"{user_name}{vip_status} | Créditos: {credits}", callback_data=f"admin_edit_user_{user_id}"))
    nav_buttons = []
    if page > 0: nav_buttons.append(types.InlineKeyboardButton("⬅️ Anterior", callback_data=f"admin_list_users_{page-1}"))
    if end_index < len(users_list): nav_buttons.append(types.InlineKeyboardButton("Próxima ➡️", callback_data=f"admin_list_users_{page+1}"))
    if nav_buttons: markup.row(*nav_buttons)
    markup.add(types.InlineKeyboardButton("↩️ Voltar ao Admin", callback_data="admin_back"))
    text = f"👥 **Lista de Usuários (Página {page+1})**"
    try:
        if is_edit: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' not in str(e): raise e

def show_vip_list(chat_id, message_id, page):
    users_data = load_data(USERS_FILE)
    if not users_data:
        bot.edit_message_text("Nenhum usuário encontrado para gerenciar.", chat_id, message_id)
        return
    users_list = list(users_data.items())
    items_per_page = 5
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    paginated_users = users_list[start_index:end_index]
    markup = types.InlineKeyboardMarkup(row_width=1)
    for user_id, user_name in paginated_users:
        vip_status_icon = "✅" if is_vip(user_id) else "❌"
        markup.add(types.InlineKeyboardButton(f"{vip_status_icon} {user_name}", callback_data=f"admin_toggle_vip_{user_id}_{page}"))
    nav_buttons = []
    if page > 0: nav_buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"admin_list_vips_{page-1}"))
    if end_index < len(users_list): nav_buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"admin_list_vips_{page+1}"))
    if nav_buttons: markup.row(*nav_buttons)
    markup.add(types.InlineKeyboardButton("↩️ Voltar ao Admin", callback_data="admin_back"))
    text = f"✨ **Gerenciar VIPs (Página {page+1})**\n\nClique em um usuário para adicionar ou remover do VIP."
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' not in str(e): raise e

def show_group_list(chat_id, message_id):
    monitored_groups = get_monitored_groups()
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    text = "🌐 **Grupos Monitorados**\n\n"
    if not monitored_groups:
        text += "Nenhum grupo na lista."
    else:
        for group_id in monitored_groups:
            try:
                chat_info = bot.get_chat(group_id)
                group_name = chat_info.title
            except Exception:
                group_name = "Nome Desconhecido"
            text += f"▪️ `{group_name}` (`{group_id}`)\n"
            markup.add(types.InlineKeyboardButton(f"🗑️ Remover {group_name}", callback_data=f"admin_remove_group_{group_id}"))
    
    markup.add(types.InlineKeyboardButton("➕ Adicionar Novo Grupo", callback_data="admin_add_group"))
    markup.add(types.InlineKeyboardButton("↩️ Voltar ao Admin", callback_data="admin_back"))
    
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' not in str(e): raise e

def ask_for_group_id(message):
    try:
        group_id = int(message.text)
        # Garante que o ID do grupo seja negativo, como é padrão para supergrupos
        if group_id > 0:
            group_id = -group_id
        
        if add_monitored_group(group_id):
            bot.reply_to(message, f"✅ Grupo `{group_id}` adicionado com sucesso!")
        else:
            bot.reply_to(message, f"⚠️ Grupo `{group_id}` já estava na lista.")
    except (ValueError, TypeError):
        bot.reply_to(message, "❌ ID inválido. Envie apenas o número do ID do grupo (ex: `-100123456789`).")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id

    # --- LÓGICA DE FILTRO DE BUSCA ---
    if call.data.startswith('filter_'):
        parts = call.data.split('_', 2)
        filter_type = parts[1]
        keyword = parts[2]
        
        # Debita o crédito aqui, somente quando a busca é confirmada
        if not is_vip(user_id):
            if get_user_credits(user_id) < CUSTO_POR_PESQUISA:
                bot.answer_callback_query(call.id, "❌ Créditos insuficientes!", show_alert=True)
                return
            if not use_credit(user_id):
                bot.answer_callback_query(call.id, "🚨 Erro ao debitar crédito. Tente novamente.", show_alert=True)
                return
        
        bot.answer_callback_query(call.id, f"Iniciando busca com filtro: {filter_type}")
        # Edita a mensagem original para mostrar que a busca começou
        saldo_msg = "∞ (VIP)" if is_vip(user_id) else get_user_credits(user_id)
        bot.edit_message_text(f"✅ **Solicitação recebida!**\n\n_Saldo Atual: {saldo_msg}_\n\nAguarde enquanto eu procuro por `{keyword}`...", call.message.chat.id, call.message.message_id, reply_markup=None)
        threading.Thread(target=search_in_directory, args=(call.message.chat.id, call.message.message_id, keyword, filter_type)).start()
        return

    # --- LÓGICA DO ADMIN ---
    if user_id == ADMIN_ID and (call.data.startswith('admin_') or call.data.startswith('broadcast_to_')):
        bot.answer_callback_query(call.id)
        action = call.data.split('_')
        
        if action[0] == 'broadcast':
            target = action[2]
            original_message_id = call.message.message_id - 1
            class FwdMessage:
                def __init__(self, chat_id, msg_id):
                    self.chat = types.Chat(id=chat_id, type='')
                    self.message_id = msg_id
            fwd_message = FwdMessage(call.message.chat.id, original_message_id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            threading.Thread(target=broadcast_message_thread, args=(target, fwd_message)).start()
            return

        if action[1] == 'back':
            if action[-1] == 'from' and action[-2] == 'broadcast':
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.delete_message(call.message.chat.id, call.message.message_id - 1)
            else:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception: pass
            admin_panel(call.message)
        elif action[1] == 'broadcast':
            msg = bot.edit_message_text("📢 Envie a mensagem (texto, foto, etc.) que deseja divulgar.\nPara cancelar, digite /cancelar.", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(msg, ask_for_broadcast_message)
        elif action[1] == 'gen':
            msg = bot.edit_message_text("🎁 Digite a quantidade de créditos para o Gift Card:", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(msg, ask_for_gift_amount)
        elif action[1] == 'clear' and action[2] == 'cache':
            clear_cache_command(call.message)
            bot.answer_callback_query(call.id, "Comando de limpar cache executado!")
        elif action[1] == 'list' and action[2] == 'users':
            show_user_list(call.message.chat.id, call.message.message_id, int(action[3]))
        elif action[1] == 'edit':
            user_id_to_edit = action[3]
            user_name = load_data(USERS_FILE).get(user_id_to_edit, f"ID {user_id_to_edit}")
            credits = get_user_credits(user_id_to_edit)
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("↩️ Voltar", callback_data="admin_list_users_0"))
            msg = bot.edit_message_text(f"✏️ Editando **{user_name}** (Saldo: `{credits}`)\n\nEnvie a quantidade para adicionar ou remover (ex: `50` para adicionar, `-10` para remover).", call.message.chat.id, call.message.message_id, reply_markup=markup)
            bot.register_next_step_handler(msg, ask_for_credits_change, user_id_to_edit)
        elif action[1] == 'stats':
            total_users = len(load_data(USERS_FILE))
            total_credits = sum(load_data(CREDITOS_FILE).values())
            total_vips = len(load_data(VIPS_FILE))
            total_groups = len(get_monitored_groups())
            stats_text = (f"📊 **Estatísticas** 📊\n\n▪️ **Usuários Totais:** `{total_users}`\n▪️ **Créditos em Circulação:** `{total_credits}`\n▪️ **Usuários VIP:** `{total_vips}`\n▪️ **Grupos Monitorados:** `{total_groups}`")
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("↩️ Voltar", callback_data="admin_back"))
            bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        elif action[1] == 'list' and action[2] == 'vips':
            show_vip_list(call.message.chat.id, call.message.message_id, int(action[3]))
        elif action[1] == 'toggle' and action[2] == 'vip':
            user_id_to_toggle = action[3]
            current_page = int(action[4])
            toggle_vip(user_id_to_toggle)
            show_vip_list(call.message.chat.id, call.message.message_id, current_page)
        elif action[1] == 'manage' and action[2] == 'groups':
            show_group_list(call.message.chat.id, call.message.message_id)
        elif action[1] == 'add' and action[2] == 'group':
            msg = bot.edit_message_text("➕ Envie o ID do novo grupo para monitorar.\nO ID deve ser um número negativo (ex: -100123456).", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(msg, ask_for_group_id)
        elif action[1] == 'remove' and action[2] == 'group':
            group_id_to_remove = int(action[3])
            remove_monitored_group(group_id_to_remove)
            show_group_list(call.message.chat.id, call.message.message_id)
        return

    # --- LÓGICA DO USUÁRIO COMUM ---
    bot.answer_callback_query(call.id)
    if call.data == 'my_credits':
        credits = get_user_credits(user_id)
        vip_status = "\n✨ Você tem acesso VIP ilimitado!" if is_vip(user_id) else ""
        referrals = load_data(REFERRAL_FILE).get(str(user_id), 0)
        needed = MEMBROS_POR_CREDITO_LOTE - referrals
        bot.answer_callback_query(call.id, f"💰 Saldo: {credits} créditos.\n📈 Progresso: {referrals}/{MEMBROS_POR_CREDITO_LOTE} adicionados.\n🎯 Faltam {needed} para ganhar mais.{vip_status}", show_alert=True)
    elif call.data == 'redeem_gift':
        msg = bot.send_message(call.message.chat.id, "🎁 Por favor, envie o seu código de presente.")
        bot.register_next_step_handler(msg, lambda m: redeem_gift_code(m.from_user, m.text))
    elif call.data == 'show_help':
        command_help(call.message)

# =================================================================================
# --- INICIALIZAÇÃO E EXECUÇÃO DO BOT (COM SISTEMA ANTI-QUEDA) ---
# =================================================================================
def run_bot():
    """Função para rodar o bot com tratamento de exceções."""
    print("Verificando configurações...")
    if 'SEU_TOKEN_AQUI' in BOT_TOKEN or ADMIN_ID == 123456789:
        print("\n!!! ATENÇÃO !!!\nPor favor, preencha as variáveis BOT_TOKEN e ADMIN_ID.")
        return
        
    print("Criando diretórios e arquivos necessários...")
    for dir_path in [DIRETORIO_DE_BUSCA, DIRETORIO_CACHE]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Diretório '{dir_path}' criado.")
    
    for file in [CREDITOS_FILE, REFERRAL_FILE, GIFTS_FILE, USERS_FILE, VIPS_FILE, GROUPS_FILE]:
        if not os.path.exists(file):
            save_data({}, file)

    print("\nBot pronto para iniciar!")
    
    # --- CORREÇÃO ADICIONADA AQUI ---
    print("Removendo webhook antigo, se existir...")
    bot.delete_webhook()
    time.sleep(1) # Pequena pausa para garantir que o comando foi processado
    # --- FIM DA CORREÇÃO ---

    while True:
        try:
            print("Conectando ao Telegram via Polling...")
            bot.polling(none_stop=True, timeout=123)
        except (ConnectionError, ReadTimeout) as e:
            print(f"Erro de conexão: {e}. Reconectando em 15 segundos...")
            time.sleep(15)
        except KeyboardInterrupt:
            print("\nBot interrompido pelo usuário. Encerrando.")
            break
        except Exception as e:
            print(f"Ocorreu um erro inesperado: {e}")
            # Verifica se o erro é o de webhook novamente, só por segurança
            if 'webhook' in str(e).lower():
                print("Conflito de Webhook detectado. Tentando remover novamente...")
                try:
                    bot.delete_webhook()
                except Exception as del_e:
                    print(f"Falha ao tentar remover webhook: {del_e}")
            print("Reiniciando o bot em 20 segundos...")
            time.sleep(20)

if __name__ == "__main__":
    run_bot()
