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
# bot saves persistent config in ./bot_config.json so changes survive restarts.

import os, asyncio, datetime, json, discord
from discord.ext import tasks, commands

TOKEN   = os.getenv("DISCORD_TOKEN")
MEMBERS = [int(x) for x in os.getenv("MEMBER_IDS", "").split(',') if x]
CHAN_ID = int(os.getenv("STATUS_CHANNEL_ID", 0))
TIMEOUT = int(os.getenv("TIMEOUT_MIN", 15))
KILL    = os.getenv("KILL_FILE", "bot_disabled")
CONFIG  = "bot_config.json"      # persistent settings
NEXT    = "next_poll.txt"        # one‑off override

# ---------- helpers ---------------------------------------------------------

def load_config():
    default_hour   = int(os.getenv("POLL_HOUR", 20))
    default_minute = int(os.getenv("POLL_MINUTE", 59))
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG) as f:
                data = json.load(f)
            return data.get("hour", default_hour), data.get("minute", default_minute)
        except Exception:
            pass  # fall through if file corrupt
    return default_hour, default_minute

def save_config(h: int, m: int):
    with open(CONFIG, "w") as f:
        json.dump({"hour": h, "minute": m}, f)

POLL_H, POLL_M = load_config()

intents = discord.Intents.none()
intents.dm_messages = True
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
    async def yes(self, _: discord.ui.Button, inter: discord.Interaction):
        await self._handle(inter, "yes")

    @discord.ui.button(label="skip", style=discord.ButtonStyle.danger)
    async def no(self, _: discord.ui.Button, inter: discord.Interaction):
        await self._handle(inter, "no")

# ---------- utility ---------------------------------------------------------

async def post_summary(votes: dict[int, str]):
    chan = bot.get_channel(CHAN_ID) or await bot.fetch_channel(CHAN_ID)
    yes = [uid for uid, v in votes.items() if v == "yes"]
    if len(yes) == len(MEMBERS):
        await chan.send("✅ everyone is in – hop on voice!")
    else:
        await chan.send("❌ session skipped (not all confirmed)")


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
    if not poll_due() or os.path.exists(KILL):
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
    save_config(h, m)
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

# ---------- lifecycle -------------------------------------------------------

@bot.event
async def on_ready():
    print("bot online as", bot.user)
    nightly_poll.start()

bot.run(TOKEN)