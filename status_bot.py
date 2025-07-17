# pocket‑arcade nightly status bot – **private votes + dynamic time**
# python 3.10+, discord.py 2.x  (pip install discord.py)
# ------------------------------------------------------
# env vars (fallbacks only – can be overridden at runtime):
#   DISCORD_TOKEN        – bot token (required)
#   MEMBER_IDS           – comma‑separated discord user ids to poll
#   STATUS_CHANNEL_ID    – id of #status channel for summary
#   POLL_HOUR            – default hour (24h, default 20)
#   POLL_MINUTE          – default minute (default 59)
#   TIMEOUT_MIN          – minutes voters have to respond (default 15)
#   KILL_FILE            – killswitch path (default ./bot_disabled)
# ------------------------------------------------------
# runtime commands (dm/any channel the bot sees):
#   !settime HH:MM       – permanently change daily poll time
#   !next HH:MM          – set a **one‑off** poll time for tonight only
#   !off / !on           – toggle killswitch
#   !setmembers @user1 @user2 ... – set which users to poll
#   !setchannel #channel – set status channel for summaries
#   !settimeout MINUTES  – set response timeout
#   !config              – show current configuration
#   !test                – test poll (sends DMs immediately)
#   !ping                – simple ping/pong test
# bot saves persistent config in ./bot_config.json so changes survive restarts.

import os, asyncio, datetime, json, discord
from discord.ext import tasks, commands

TOKEN   = os.getenv("DISCORD_TOKEN")
TIMEOUT = int(os.getenv("TIMEOUT_MIN", 15))
KILL    = os.getenv("KILL_FILE", "bot_disabled")
CONFIG  = "bot_config.json"      # persistent settings
NEXT    = "next_poll.txt"        # one‑off override

# ---------- helpers ---------------------------------------------------------

def load_config():
    """Load all config from file, with env var fallbacks."""
    default_config = {
        "hour": int(os.getenv("POLL_HOUR", 20)),
        "minute": int(os.getenv("POLL_MINUTE", 59)),
        "members": [int(x) for x in os.getenv("MEMBER_IDS", "").split(',') if x],
        "channel_id": int(os.getenv("STATUS_CHANNEL_ID", 0)),
        "timeout": TIMEOUT
    }
    
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG) as f:
                data = json.load(f)
            # merge with defaults
            for key, value in data.items():
                if key in default_config:
                    default_config[key] = value
        except Exception as e:
            print(f"config load error: {e}")
    return default_config

def save_config(config_data):
    """Save config to file."""
    with open(CONFIG, "w") as f:
        json.dump(config_data, f, indent=2)

# load initial config
config = load_config()
POLL_H = config["hour"]
POLL_M = config["minute"]
MEMBERS = config["members"]
CHAN_ID = config["channel_id"]
TIMEOUT = config["timeout"]

intents = discord.Intents.default()
intents.message_content = True  # needed for commands
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- voting view -----------------------------------------------------

class PollView(discord.ui.View):
    def __init__(self, voters: list[int], votes: dict[int, str]):
        super().__init__(timeout=TIMEOUT*60)
        self.voters = voters
        self.votes  = votes

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id in self.voters

    async def _handle(self, interaction: discord.Interaction, choice: str):
        uid = interaction.user.id
        self.votes[uid] = choice
        await interaction.response.send_message(f"recorded: **{choice}** – ty!", ephemeral=True)
        if len(self.votes) == len(self.voters):
            self.stop()

    @discord.ui.button(label="work", style=discord.ButtonStyle.success)
    async def yes(self, inter: discord.Interaction, _: discord.ui.Button):
        await self._handle(inter, "yes")

    @discord.ui.button(label="skip", style=discord.ButtonStyle.danger)
    async def no(self, inter: discord.Interaction, _: discord.ui.Button):
        await self._handle(inter, "no")

# ---------- utility ---------------------------------------------------------

async def post_summary(votes: dict[int, str]):
    if CHAN_ID == 0:
        print("no status channel configured")
        return
    chan = bot.get_channel(CHAN_ID) or await bot.fetch_channel(CHAN_ID)
    yes = [uid for uid, v in votes.items() if v == "yes"]
    
    # add date for readability
    today = datetime.datetime.now().strftime("%b %d")
    
    if len(yes) == len(MEMBERS):
        await chan.send(f"✅ **{today}** everyone is in – hop on voice!")
    else:
        await chan.send(f"❌ **{today}** session skipped (not all confirmed)")


def due_time():
    """Return (hour, minute) for tonight's poll, respecting one‑off override."""
    if os.path.exists(NEXT):
        try:
            with open(NEXT) as f:
                line = f.read().strip()
            h, m = map(int, line.split(':'))
            return h, m
        except Exception:
            pass  # corruption -> ignore
    return POLL_H, POLL_M


def poll_due() -> bool:
    now = datetime.datetime.now()
    h, m = due_time()
    return now.hour == h and now.minute == m

# ---------- background task -------------------------------------------------

@tasks.loop(minutes=1)
async def nightly_poll():
    if not poll_due() or os.path.exists(KILL) or not MEMBERS:
        return
    # clear one‑off override once it's triggered
    if os.path.exists(NEXT):
        os.remove(NEXT)
    votes: dict[int, str] = {}
    view = PollView(MEMBERS, votes)
    for uid in MEMBERS:
        try:
            user = await bot.fetch_user(uid)
            await user.send("work on pocket arcade tonight?", view=view)
        except Exception as e:
            print("dm failed", uid, e)
    await view.wait()
    await post_summary(votes)

# ---------- commands --------------------------------------------------------

@bot.command(help="mute auto‑polls")
async def off(ctx):
    open(KILL, "w").close()
    await ctx.send("auto‑poll muted ✅")

@bot.command(help="unmute auto‑polls")
async def on(ctx):
    try: os.remove(KILL)
    except FileNotFoundError:
        pass
    await ctx.send("auto‑poll live again 🔔")

@bot.command(help="permanently set poll time, ex: !settime 21:30")
async def settime(ctx, time: str):
    try:
        h, m = map(int, time.split(':'))
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception:
        await ctx.send("format: !settime HH:MM (24h)")
        return
    global POLL_H, POLL_M
    POLL_H, POLL_M = h, m
    config["hour"] = h
    config["minute"] = m
    save_config(config)
    await ctx.send(f"daily poll time set to {h:02d}:{m:02d} ✅")

@bot.command(help="override tonight only, ex: !next 22:00")
async def next(ctx, time: str):
    try:
        h, m = map(int, time.split(':'))
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception:
        await ctx.send("format: !next HH:MM (24h)")
        return
    with open(NEXT, "w") as f:
        f.write(f"{h:02d}:{m:02d}")
    await ctx.send(f"override set: tonight's poll at {h:02d}:{m:02d} ⏰")

@bot.command(help="set which users to poll, ex: !setmembers @user1 @user2")
async def setmembers(ctx, *members: discord.Member):
    if not members:
        await ctx.send("format: !setmembers @user1 @user2 @user3...")
        return
    global MEMBERS
    MEMBERS = [m.id for m in members]
    config["members"] = MEMBERS
    save_config(config)
    member_names = ", ".join([m.display_name for m in members])
    await ctx.send(f"members set to: {member_names} ✅")

@bot.command(help="set status channel for summaries, ex: !setchannel #status")
async def setchannel(ctx, channel: discord.TextChannel):
    global CHAN_ID
    CHAN_ID = channel.id
    config["channel_id"] = CHAN_ID
    save_config(config)
    await ctx.send(f"status channel set to #{channel.name} ✅")

@bot.command(help="set response timeout in minutes, ex: !settimeout 20")
async def settimeout(ctx, minutes: int):
    if minutes < 1 or minutes > 60:
        await ctx.send("timeout must be between 1-60 minutes")
        return
    global TIMEOUT
    TIMEOUT = minutes
    config["timeout"] = TIMEOUT
    save_config(config)
    await ctx.send(f"response timeout set to {minutes} minutes ✅")

@bot.command(help="show current configuration")
async def showconfig(ctx):
    member_names = []
    for uid in MEMBERS:
        try:
            user = await bot.fetch_user(uid)
            member_names.append(user.display_name)
        except:
            member_names.append(f"Unknown ({uid})")
    
    channel_name = "Not set"
    if CHAN_ID != 0:
        try:
            channel = bot.get_channel(CHAN_ID) or await bot.fetch_channel(CHAN_ID)
            channel_name = f"#{channel.name}"
        except:
            channel_name = f"Unknown ({CHAN_ID})"
    
    embed = discord.Embed(title="Bot Configuration", color=0x00ff00)
    embed.add_field(name="Members", value=", ".join(member_names) if member_names else "None set", inline=False)
    embed.add_field(name="Status Channel", value=channel_name, inline=True)
    embed.add_field(name="Poll Time", value=f"{POLL_H:02d}:{POLL_M:02d}", inline=True)
    embed.add_field(name="Timeout", value=f"{TIMEOUT} minutes", inline=True)
    embed.add_field(name="Auto-poll", value="🔔 Enabled" if not os.path.exists(KILL) else "🔇 Disabled", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(help="simple ping test")
async def ping(ctx):
    await ctx.send("🏓 pong!")

@bot.command(help="test poll (sends DMs immediately)")
async def test(ctx):
    if not MEMBERS:
        await ctx.send("❌ no members configured! use `!setmembers @user1 @user2...` first")
        return
    
    await ctx.send(f"🧪 sending test poll to {len(MEMBERS)} members...")
    
    votes: dict[int, str] = {}
    view = PollView(MEMBERS, votes)
    success_count = 0
    
    for uid in MEMBERS:
        try:
            user = await bot.fetch_user(uid)
            await user.send("🧪 **TEST POLL** - work on pocket arcade tonight?", view=view)
            success_count += 1
        except Exception as e:
            print(f"test dm failed for {uid}: {e}")
    
    await ctx.send(f"✅ test poll sent to {success_count}/{len(MEMBERS)} members")
    
    # wait for responses or timeout
    await view.wait()
    
    # send test summary
    if CHAN_ID != 0:
        await post_summary(votes)
    else:
        yes_count = len([v for v in votes.values() if v == "yes"])
        await ctx.send(f"🧪 test results: {yes_count}/{len(votes)} voted yes")

# ---------- lifecycle -------------------------------------------------------

@bot.event
async def on_ready():
    print("bot online as", bot.user)
    print(f"config: {len(MEMBERS)} members, channel {CHAN_ID}, time {POLL_H:02d}:{POLL_M:02d}")
    nightly_poll.start()

bot.run(TOKEN)
