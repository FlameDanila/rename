"""
Discord-бот: перемешивает участников голосового канала вызывающего
и выставляет им серверные ники 1, 2, 3... Оригинальные ники сохраняются
в JSON и возвращаются командой /restore.

Зависимости: pip install -U discord.py
Запуск:      python bot.py  (токен берётся из .env рядом с bot.py: DISCORD_TOKEN=xxx)
"""
import json
import os
import random
from pathlib import Path

import discord
from discord import app_commands

BASE_DIR = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    """Минимальный разбор .env (KEY=VALUE), значения из файла имеют приоритет над окружением."""
    if not path.exists():
        return
    # utf-8-sig — Блокнот Windows часто добавляет BOM, из-за которого первый ключ портится
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        os.environ[key] = value.strip().strip("\"'")


load_env(BASE_DIR / ".env")

TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit(f"DISCORD_TOKEN не найден: впиши его в {BASE_DIR / '.env'} (DISCORD_TOKEN=...)")
if TOKEN.startswith("http"):
    raise SystemExit("В DISCORD_TOKEN лежит URL (вебхук?). Нужен токен бота: Developer Portal -> Bot -> Reset Token.")

STORE = BASE_DIR / "original_nicks.json"

intents = discord.Intents.default()
intents.members = True       # нужно включить "Server Members Intent" в Developer Portal
intents.voice_states = True


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = Bot()


# ---------- хранилище оригинальных ников ----------

def load_store() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save_store(data: dict) -> None:
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- команды ----------

@bot.tree.command(name="numbers", description="Случайно пронумеровать участников твоего голосового канала")
@app_commands.guild_only()
@app_commands.default_permissions(manage_nicknames=True)
async def numbers(interaction: discord.Interaction):
    caller = interaction.user
    if not caller.voice or not caller.voice.channel:
        await interaction.response.send_message("Сначала зайди в голосовой канал.", ephemeral=True)
        return

    await interaction.response.defer()

    people = [m for m in caller.voice.channel.members if not m.bot]
    random.shuffle(people)

    data = load_store()
    guild_store = data.setdefault(str(interaction.guild_id), {})
    done, failed = [], []

    for i, member in enumerate(people, start=1):
        original = member.nick  # None = ника на сервере не было
        try:
            await member.edit(nick=str(i), reason=f"/numbers от {caller}")
        except discord.Forbidden:
            failed.append(member.mention)
            continue
        # сохраняем только самый первый оригинал, чтобы повторный /numbers не затёр его цифрой
        guild_store.setdefault(str(member.id), original)
        done.append(f"**{i}** — {member.mention}")

    save_store(data)

    text = "\n".join(done) or "Никого переименовать не удалось."
    if failed:
        text += "\n\nНе хватило прав (владелец сервера или роль выше бота): " + ", ".join(failed)
    await interaction.followup.send(text, allowed_mentions=discord.AllowedMentions.none())


@bot.tree.command(name="restore", description="Вернуть оригинальные ники")
@app_commands.guild_only()
@app_commands.default_permissions(manage_nicknames=True)
async def restore(interaction: discord.Interaction):
    await interaction.response.defer()

    data = load_store()
    guild_store = data.get(str(interaction.guild_id), {})
    restored, failed = 0, []

    for member_id, original in list(guild_store.items()):
        member = interaction.guild.get_member(int(member_id))
        if member is None:  # ушёл с сервера — просто забываем
            guild_store.pop(member_id)
            continue
        try:
            await member.edit(nick=original, reason=f"/restore от {interaction.user}")
            guild_store.pop(member_id)
            restored += 1
        except discord.Forbidden:
            failed.append(member.mention)

    save_store(data)

    text = f"Восстановлено ников: {restored}."
    if failed:
        text += "\nНе удалось: " + ", ".join(failed)
    await interaction.followup.send(text, allowed_mentions=discord.AllowedMentions.none())


bot.run(TOKEN)
