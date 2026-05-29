# Эта строка должна быть в самом верху, где остальные импорты
from webserver import keep_alive

# bot.py
import discord
from discord import app_commands
from discord.ext import commands
import aiofiles
import os
from datetime import datetime
from typing import Dict, List
import json

from config import (
    BOT_TOKEN, GUILD_ID, TICKET_CATEGORY_ID,
    LOG_CHANNEL_ID, MODERATOR_ROLE_ID, MODERATOR_ROLE_IDS, TICKET_SETTINGS
)

# --- Настройки бота ---
intents = discord.Intents.default()
intents.message_content = True

class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.active_tickets: Dict[int, dict] = {}
        self.ticket_counter = 1

        # Создаём папку для транскриптов, если её нет
        if not os.path.exists(TICKET_SETTINGS["transcript_folder"]):
            os.makedirs(TICKET_SETTINGS["transcript_folder"])

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Синхронизировано с сервером {GUILD_ID}")

        # Добавляем постоянное представление (кнопка всегда активна)
        self.add_view(TicketPanelView())

bot = TicketBot()

# --- Вспомогательные функции ---
def get_ticket_number() -> int:
    """Получает следующий номер тикета из файла"""
    try:
        with open("ticket_counter.json", "r") as f:
            data = json.load(f)
            return data.get("counter", 1)
    except FileNotFoundError:
        return 1

def save_ticket_number(number: int):
    """Сохраняет номер тикета"""
    with open("ticket_counter.json", "w") as f:
        json.dump({"counter": number}, f)

async def create_transcript(channel: discord.TextChannel) -> str:
    """Создаёт транскрипт канала"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{TICKET_SETTINGS['transcript_folder']}/{channel.name}_{timestamp}.txt"

    async with aiofiles.open(filename, "w", encoding="utf-8") as f:
        await f.write(f"=== ТРАНСКРИПТ ТИКЕТА: {channel.name} ===\n")
        await f.write(f"=== Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            author = message.author.display_name
            content = message.clean_content or "[Вложение или embed]"
            await f.write(f"[{timestamp}] {author}: {content}\n")

            if message.attachments:
                for att in message.attachments:
                    await f.write(f"  → Вложение: {att.url}\n")

        await f.write(f"\n=== КОНЕЦ ТРАНСКРИПТА ===\n")

    return filename

# --- Модальное окно для апелляции (древнегреческий стиль) ---
class AppealModal(discord.ui.Modal, title="🏛️ АПЕЛЛЯЦИЯ К АГОРЕ"):
    def __init__(self):
        super().__init__(timeout=300)

    punishment_type = discord.ui.TextInput(
        label="Вид наказания",
        placeholder="Например: Мут / Варн / Бан / Кик",
        style=discord.TextStyle.short,
        required=True,
        max_length=50
    )

    who_issued = discord.ui.TextInput(
        label="Кто выдал наказание?",
        placeholder="Ник модератора, если помнишь",
        style=discord.TextStyle.short,
        required=False,
        max_length=50
    )

    reason = discord.ui.TextInput(
        label="Почему считаешь наказание несправедливым?",
        placeholder="Изложи свои аргументы... Доказательства приложи в канале после открытия тикета.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    evidence_note = discord.ui.TextInput(
        label="Скриншоты / доказательства",
        placeholder="Укажи, какие доказательства у тебя есть (прикрепишь в тикете)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Проверяем, нет ли уже открытого тикета у пользователя
        for channel in interaction.guild.text_channels:
            if channel.category_id == TICKET_CATEGORY_ID and channel.topic:
                if str(interaction.user.id) in channel.topic:
                    await interaction.followup.send(
                        "⚠️ У тебя уже открыт активный тикет! Закрой его перед созданием нового.",
                        ephemeral=True
                    )
                    return

        # Получаем номер тикета
        ticket_num = get_ticket_number()
        ticket_name = f"апелляция-{ticket_num:04d}"

        # Получаем категорию и все роли модераторов
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        mod_role = interaction.guild.get_role(MODERATOR_ROLE_ID)  # основная роль для пинга
        mod_roles = [r for r in (interaction.guild.get_role(rid) for rid in MODERATOR_ROLE_IDS) if r]

        if not category:
            await interaction.followup.send(
                "❌ Ошибка конфигурации: категория тикетов не найдена!",
                ephemeral=True
            )
            return

        if not mod_roles:
            await interaction.followup.send(
                "❌ Ошибка конфигурации: ни одна роль модератора не найдена!",
                ephemeral=True
            )
            return

        # Права доступа — базовые
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            )
        }
        # Добавляем права для всех ролей модераторов
        for role in mod_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True
            )

        # Создаём канал
        channel = await interaction.guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites,
            topic=f"{interaction.user.id} | Создан: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        # Сохраняем информацию
        bot.active_tickets[channel.id] = {
            "user_id": interaction.user.id,
            "created_at": datetime.now(),
            "closed": False
        }

        # Увеличиваем счётчик
        save_ticket_number(ticket_num + 1)

        # Отправляем приветственное сообщение в тикет (древнегреческий стиль)
        embed = discord.Embed(
            title="🏛️ АГОРА АПЕЛЛЯЦИИ",
            description=(
                f"📜 **Апеллянт:** {interaction.user.mention}\n"
                f"⚖️ **Вид наказания:** {self.punishment_type.value}\n"
                f"👑 **Архонт:** {self.who_issued.value or 'Не указан'}\n\n"
                f"📝 **Основание для апелляции:**\n{self.reason.value}\n\n"
                f"📎 **Доказательства:** {self.evidence_note.value or 'Будут приложены позже'}\n\n"
                f"---\n"
                f"*«Справедливость — величайшая из добродетелей»* — Аристотель\n\n"
                f"**Правила Агоры:**\n"
                f"> 1. Один тикет — одно дело\n"
                f"> 2. Никаких оскорблений архонтов\n"
                f"> 3. Жди ответа до 24 часов\n"
                f"> 4. Решение можно обжаловать один раз у верховного жреца"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Тикет #{ticket_num:04d} | Создан {datetime.now().strftime('%d.%m.%Y')}")

        view = TicketControlView(channel.id, interaction.user.id)
        await channel.send(f"{mod_role.mention} {interaction.user.mention}", embed=embed, view=view)

        # Уведомляем пользователя
        await interaction.followup.send(
            f"✅ Тикет создан! Переходи в {channel.mention} и прикрепи доказательства, если они у тебя есть.\n"
            f"⚖️ Архонты рассмотрят твою апелляцию в ближайшее время.",
            ephemeral=True
        )

# --- Кнопка создания тикета ---
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Постоянная кнопка

    @discord.ui.button(
        label="📜 Открыть Агору",
        style=discord.ButtonStyle.primary,
        emoji="🏛️",
        custom_id="open_ticket_button"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Отправляем модальное окно
        modal = AppealModal()
        await interaction.response.send_modal(modal)

# --- Кнопки управления тикетом ---
class TicketControlView(discord.ui.View):
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id

    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав: любой модератор из списка ролей или создатель тикета
        user_role_ids = {r.id for r in interaction.user.roles}
        is_moderator = bool(user_role_ids & set(MODERATOR_ROLE_IDS))
        if not (is_moderator or interaction.user.id == self.user_id):
            await interaction.response.send_message("❌ Ты не можешь закрыть этот тикет!", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
            return

        # Отправляем подтверждение
        confirm_view = ConfirmCloseView(self.channel_id, self.user_id)
        await interaction.response.send_message(
            "🏛️ **Ты уверен, что хочешь закрыть агору?**\n"
            "После закрытия будет создан транскрипт, и канал будет удалён.",
            view=confirm_view,
            ephemeral=True
        )

    @discord.ui.button(label="📄 Транскрипт", style=discord.ButtonStyle.secondary, emoji="📄")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        transcript_file = await create_transcript(channel)

        with open(transcript_file, "rb") as f:
            await interaction.followup.send(
                "📜 Вот транскрипт Агоры:",
                file=discord.File(f, os.path.basename(transcript_file)),
                ephemeral=True
            )

class ConfirmCloseView(discord.ui.View):
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.user_id = user_id

    @discord.ui.button(label="✅ Да, закрыть", style=discord.ButtonStyle.success)
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Канал уже удалён!", ephemeral=True)
            return

        await interaction.response.send_message("🏛️ Агора закрывается. Создаю транскрипт...", ephemeral=True)

        # Создаём транскрипт
        transcript_file = await create_transcript(channel)

        # Отправляем в лог-канал
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            with open(transcript_file, "rb") as f:
                embed = discord.Embed(
                    title="📜 Агора закрыта",
                    description=f"**Канал:** {channel.name}\n**Закрыл:** {interaction.user.mention}\n**Время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    color=discord.Color.red()
                )
                await log_channel.send(embed=embed, file=discord.File(f, os.path.basename(transcript_file)))

        # Удаляем канал
        await channel.delete()

        # Удаляем транскрипт с диска
        os.remove(transcript_file)

        # Обновляем информацию
        if channel.id in bot.active_tickets:
            bot.active_tickets[channel.id]["closed"] = True

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🏛️ Закрытие Агоры отменено.", ephemeral=True)
        self.stop()

# --- Команда для отправки панели тикетов ---
@bot.tree.command(
    name="агора",
    description="🏛️ Отправить панель для создания тикетов-апелляций",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.default_permissions(administrator=True)
async def agora_panel(interaction: discord.Interaction):
    """Отправляет панель с кнопкой для создания тикета (только для админов)"""
    embed = discord.Embed(
        title="🏛️ АГОРА АПЕЛЛЯЦИИ",
        description=(
            "*«Несправедливый приговор можно сломать, как глиняный черепок. "
            "Честная апелляция — это право каждого метека и гражданина»*\n\n"
            "Если ты считаешь, что наказание было вынесено несправедливо, "
            "нажми на кнопку ниже и открой свою Агору.\n\n"
            "**Правила Агоры:**\n"
            "• Один тикет — одно дело\n"
            "• Без оскорблений архонтов\n"
            "• Приложи доказательства\n"
            "• Жди ответа до 24 часов"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="Roma aeterna, iustitia aeterna")

    view = TicketPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Панель Агоры отправлена!", ephemeral=True)

# --- Команда статистики ---
@bot.tree.command(
    name="статистика",
    description="📊 Показать статистику тикетов на сервере",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.default_permissions(manage_guild=True)
async def stats_command(interaction: discord.Interaction):
    total_ever = get_ticket_number() - 1

    # Считаем активные тикеты прямо по каналам категории
    active = 0
    category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
    if category:
        active = sum(
            1 for ch in interaction.guild.text_channels
            if ch.category_id == TICKET_CATEGORY_ID
        )

    closed = max(0, total_ever - active)

    embed = discord.Embed(
        title="📊 СТАТИСТИКА АГОРЫ",
        color=discord.Color.gold()
    )
    embed.add_field(name="📜 Всего открыто", value=str(total_ever), inline=True)
    embed.add_field(name="🟢 Активных", value=str(active), inline=True)
    embed.add_field(name="🔒 Закрыто", value=str(closed), inline=True)
    embed.set_footer(text=f"Запрошено: {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Запуск бота ---
@bot.event
async def on_ready():
    print(f"🤖 Бот {bot.user} запущен!")
    print(f"📊 Активен на {len(bot.guilds)} серверах")

    # Обновляем статус
    await bot.change_presence(
        activity=discord.Game(name="🏛️ Агора | /агора")
    )

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан! Создай файл .env с BOT_TOKEN=твой_токен")
        exit(1)
    keep_alive()  # Запускает Flask на порту 8080 ДО подключения к Discord
    bot.run(BOT_TOKEN)
