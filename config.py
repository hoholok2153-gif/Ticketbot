# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID твоего сервера (GUILD)
GUILD_ID = 1509276173757186381

# ID категории, где будут создаваться тикеты
TICKET_CATEGORY_ID = 1509511921353625722

# ID канала для логов (куда отправляются закрытые тикеты)
LOG_CHANNEL_ID = 1509530832124248164

# ID ролей модераторов (кто видит тикеты) — список всех ролей
MODERATOR_ROLE_IDS = [
    1509298388578074805,
    1509288642202439760,
    1509296908643078406,
    1509298529473138870,
    1509298454277521448,
    1509277235939381329,
    1509338009290674347,
]
# Основная роль (первая из списка) — используется для пинга в тикете
MODERATOR_ROLE_ID = MODERATOR_ROLE_IDS[0]

# Настройки тикета
TICKET_SETTINGS = {
    "transcript_folder": "transcripts",
    "max_tickets_per_user": 1,
}
