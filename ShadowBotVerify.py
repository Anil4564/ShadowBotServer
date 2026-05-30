import discord
import datetime
import re
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import time
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ==========================================
# SETTINGS AND DATABASE SYSTEM
# ==========================================
GUILD_ID = 1496194010187042889
SPECIAL_OWNER_ID = 1424590067577655358
BAN_FILE = "/data/banned_users.txt"

def load_banned_users():
    if not os.path.exists(BAN_FILE):
        return {}
    banned_dict = {}
    with open(BAN_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 2 and parts[0].isdigit():
                    uid = int(parts[0])
                    banned_dict[uid] = parts[1] if parts[1] == "lifetime" else float(parts[1])
            elif line.isdigit():
                banned_dict[int(line)] = "lifetime"
    return banned_dict

def save_all_banned_users(banned_dict):
    os.makedirs(os.path.dirname(BAN_FILE), exist_ok=True)
    with open(BAN_FILE, "w") as f:
        for uid, expire in banned_dict.items():
            f.write(f"{uid}|{expire}\n")

def save_banned_user(user_id, duration_days=0):
    banned = load_banned_users()
    if duration_days <= 0:
        banned[user_id] = "lifetime"
    else:
        expire_timestamp = time.time() + (duration_days * 86400)
        banned[user_id] = expire_timestamp
    save_all_banned_users(banned)

def remove_banned_user(user_id):
    banned = load_banned_users()
    if user_id in banned:
        del banned[user_id]
        save_all_banned_users(banned)

def get_total_bans():
    return len(load_banned_users())

# ==========================================
# BUTTON AND PANEL VIEWS
# ==========================================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green, custom_id="persistent_verify_button", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Member")
        if not role:
            await interaction.response.send_message("❌ 'Member' role could not be found!", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("⚠️ You are already verified!", ephemeral=True)
            return
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Verification successful!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Hierarchy error.", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="persistent_ticket_close", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("🔒 Closing in 5 seconds...", ephemeral=False)
            await asyncio.sleep(5)
            await interaction.channel.delete()

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_ticket_open", emoji="📩")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        tn = f"ticket-{member.name.lower()}".replace(" ", "-")
        if discord.utils.get(guild.channels, name=tn): 
            await interaction.response.send_message("⚠️ You already have a ticket!", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        try:
            ch = await guild.create_text_channel(name=tn, overwrites=overwrites)
            await ch.send(embed=discord.Embed(title="Support", description="Click the red button to close."), view=TicketCloseView())
            await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)
        except: pass

class AntiNukeBotActionView(discord.ui.View):
    def __init__(self, guild_id, bot_id):
        super().__init__(timeout=None)
        pass 

# ==========================================
# MAIN BOT CLASS
# ==========================================
class ShadowBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        intents.reactions = True  
        intents.guilds = True  
        intents.moderation = True 
        super().__init__(command_prefix="s!", intents=intents)
        self.anti_nuke_status = True  
        self.channel_deletions = {}   
        self.role_deletions = {}      
        self.member_bans = {}         

    async def setup_hook(self):
        self.add_view(VerifyView())
        self.add_view(TicketOpenView())
        self.add_view(TicketCloseView())
        self.loop.create_task(self.check_expired_bans())

    async def check_expired_bans(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                banned_list = load_banned_users()
                ct = time.time()
                chg = False
                guild = self.get_guild(GUILD_ID)
                if guild:
                    for uid, exp in list(banned_list.items()):
                        if exp != "lifetime" and ct >= exp:
                            del banned_list[uid]
                            chg = True
                            try: await guild.unban(discord.Object(id=uid))
                            except: pass
                if chg: save_all_banned_users(banned_list)
            except: pass
            await asyncio.sleep(60)

bot = ShadowBot()
scam_trap_channel_id = None
scam_panel_message_id = None  
log_channel_id = None  

@bot.event
async def on_ready():
    print(f"[{bot.user.name}] IS ONLINE. Type s!sync in your server to load commands.")

async def send_log(embed):
    if log_channel_id:
        ch = bot.get_channel(log_channel_id)
        if ch: await ch.send(embed=embed)

# ==========================================
# PROTECTION TRIGGERS (ANTI-NUKE)
# ==========================================
async def nuke_punish(guild, user_id, action_type):
    try:
        member = await guild.fetch_member(user_id)
        if member.id == guild.owner_id or member.id == SPECIAL_OWNER_ID or member.id == bot.user.id: return 
        try: await member.edit(roles=[])
        except: pass
        save_banned_user(member.id)
        await member.ban(reason=f"Anti-Nuke: {action_type}")
        await send_log(discord.Embed(title="🚨 ANTI-NUKE TRIGGERED", description=f"{member.mention} has been punished. Reason: {action_type}"))
    except: pass

@bot.event
async def on_member_join(member):
    if member.id in load_banned_users():
        try: await member.ban(reason="Blacklist Auto-Reban"); return
        except: pass
    if member.bot and bot.anti_nuke_status:
        owner = await bot.fetch_user(SPECIAL_OWNER_ID)
        if owner:
            try: await owner.send(f"⚠️ A new bot has been added to the server: {member.mention}")
            except: pass

@bot.event
async def on_guild_channel_delete(channel):
    if not bot.anti_nuke_status or not channel.guild: return
    async for e in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        uid = e.user.id
        ct = time.time()
        if uid not in bot.channel_deletions: bot.channel_deletions[uid] = []
        channel_deletions = bot.channel_deletions[uid]
        channel_deletions.append(ct)
        bot.channel_deletions[uid] = [t for t in channel_deletions if ct - t <= 10]
        if len(bot.channel_deletions[uid]) >= 2: await nuke_punish(channel.guild, uid, "Mass Channel Deletion")

@bot.event
async def on_guild_role_delete(role):
    if not bot.anti_nuke_status or not role.guild: return
    async for e in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        uid = e.user.id
        ct = time.time()
        if uid not in bot.role_deletions: bot.role_deletions[uid] = []
        role_deletions = bot.role_deletions[uid]
        role_deletions.append(ct)
        bot.role_deletions[uid] = [t for t in role_deletions if ct - t <= 10]
        if len(bot.role_deletions[uid]) >= 2: await nuke_punish(role.guild, uid, "Mass Role Deletion")

@bot.event
async def on_member_ban(guild, user):
    if not bot.anti_nuke_status: return
    async for e in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
        uid = e.user.id
        if uid == bot.user.id: return
        ct = time.time()
        if uid not in bot.member_bans: bot.member_bans[uid] = []
        member_bans = bot.member_bans[uid]
        member_bans.append(ct)
        bot.member_bans[uid] = [t for t in member_bans if ct - t <= 10]
        if len(bot.member_bans[uid]) >= 2: await nuke_punish(guild, uid, "Mass Ban")

# ==========================================
# MESSAGE CONTROLS AND LOGS
# ==========================================
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild: return
    embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red())
    embed.add_field(name="Author", value=message.author.mention)
    embed.add_field(name="Content", value=message.content or "Empty / Embed")
    await send_log(embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.orange())
    embed.add_field(name="Before", value=before.content)
    embed.add_field(name="After", value=after.content)
    await send_log(embed)

@bot.event
async def on_message(message):
    global scam_trap_channel_id, scam_panel_message_id
    if message.author.bot or not message.guild: return

    if scam_trap_channel_id and message.channel.id == scam_trap_channel_id:
        try:
            await message.delete()
            save_banned_user(message.author.id)
            await message.author.ban(reason="Honeypot Trap")
            return
        except: pass

    allowed_roles = ["Mod", "Owner"]
    is_staff = any(r.name in allowed_roles for r in message.author.roles) or message.author.id == message.guild.owner_id or message.author.id == SPECIAL_OWNER_ID
    
    if not is_staff and re.search(r'(https?://[^\s]+)|(discord\.gg/[^\s]+)', message.content.lower()):
        try:
            await message.delete()
            return
        except: pass

    await bot.process_commands(message)

# ==========================================
# SLASH COMMANDS (ALL ENGLISH)
# ==========================================

@bot.tree.command(name="anti_nuke", description="Enables or disables the anti-nuke system.")
@app_commands.describe(durum="True = Enabled, False = Disabled")
async def assignment_antinuke(interaction: discord.Interaction, durum: bool):
    bot.anti_nuke_status = durum
    await interaction.response.send_message(f"🛡️ Anti-Nuke status updated: {durum}", ephemeral=True)

@bot.tree.command(name="copyserver", description="Copies all channels and categories from a source server to a main server.")
@app_commands.describe(main_server_id="The server ID that will be wiped and set up", target_server_id="The source server ID to copy from")
async def assignment_copyserver(interaction: discord.Interaction, main_server_id: str, target_server_id: str):
    await interaction.response.defer(ephemeral=True)
    main_guild = bot.get_guild(int(main_server_id))
    target_guild = bot.get_guild(int(target_server_id))

    if not main_guild or not target_guild:
        await interaction.followup.send("❌ One of the servers could not be found!", ephemeral=True)
        return

    # Wiping channels
    for channel in main_guild.channels:
        try: await channel.delete()
        except: pass

    # Cloning Categories
    category_mapping = {}
    for category in sorted(target_guild.categories, key=lambda c: c.position):
        try:
            new_cat = await main_guild.create_category(name=category.name, position=category.position)
            category_mapping[category.id] = new_cat
        except: pass

    # Cloning Channels
    for channel in sorted(target_guild.channels, key=lambda c: c.position):
        if isinstance(channel, discord.CategoryChannel): continue
        target_cat = category_mapping.get(channel.category_id) if channel.category else None
        try:
            if isinstance(channel, discord.TextChannel):
                await main_guild.create_text_channel(name=channel.name, topic=channel.topic, category=target_cat)
            elif isinstance(channel, discord.VoiceChannel):
                await main_guild.create_voice_channel(name=channel.name, user_limit=channel.user_limit, category=target_cat)
        except: pass

    await interaction.followup.send("✅ Server cloning process completed successfully!", ephemeral=True)

@bot.tree.command(name="check-ban-file", description="Checks the blacklist database file.")
async def assignment_checkbanfile(interaction: discord.Interaction):
    if not os.path.exists(BAN_FILE):
        await interaction.response.send_message("❌ Blacklist database file is empty.", ephemeral=True)
        return
    await interaction.response.send_message(file=discord.File(BAN_FILE), ephemeral=True)

@bot.tree.command(name="timeout", description="Mutes a user for a specific duration.")
@app_commands.describe(user="The target member", minutes="Duration in minutes", reason="Reason for timeout")
async def assignment_timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "None"):
    try:
        await user.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"✅ {user.name} has been timed out successfully.")
    except:
        await interaction.response.send_message("❌ Insufficient permissions.", ephemeral=True)

@bot.tree.command(name="ban-user", description="Bans a user and adds them to the persistent blacklist.")
@app_commands.describe(user="The target user", days="Duration in days (0 = Lifetime)", reason="Reason for ban")
async def assignment_banuser(interaction: discord.Interaction, user: discord.User, days: int, reason: str = "None"):
    save_banned_user(user.id, duration_days=days)
    try:
        await interaction.guild.ban(user, reason=reason)
        await interaction.response.send_message(f"✅ {user.name} has been banned and added to the blacklist.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to ban the user.", ephemeral=True)

@bot.tree.command(name="unban-user", description="Removes a user from the blacklist and lifts their ban.")
@app_commands.describe(user_id="The Discord User ID")
async def assignment_unbanuser(interaction: discord.Interaction, user_id: str):
    uid = int(user_id)
    remove_banned_user(uid)
    try:
        await interaction.guild.unban(discord.Object(id=uid))
        await interaction.response.send_message("✅ User ban and blacklist removed successfully.", ephemeral=True)
    except:
        await interaction.response.send_message("⚠️ Removed from the blacklist database, but the user wasn't banned on this server.", ephemeral=True)

@bot.tree.command(name="channel-lock", description="Locks a channel for regular members.")
@app_commands.describe(channel="The channel to lock")
async def assignment_channellock(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        overwrites = channel.overwrites
        for role in interaction.guild.roles:
            if role.name not in ["Mod", "Owner"] and not role.managed:
                overwrites[role] = discord.PermissionOverwrite(send_messages=False)
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message(f"🔒 {channel.mention} has been locked.", ephemeral=True)
    except: pass

# ==========================================
# SYNC COMMAND (SAFE AND STABLE)
# ==========================================
@bot.command(name="sync")
async def sync_commands(ctx):
    if ctx.author.id != SPECIAL_OWNER_ID and ctx.author.id != ctx.guild.owner_id:
        return

    await ctx.send("🔄 **Starting global slash command synchronization... Please wait.**")
    try:
        await bot.tree.sync()
        await ctx.send("✅ **Success!** Application commands have been pushed to Discord's global cache.\n\n⚠️ *Notice: It might take up to 10-15 minutes for Discord to display the slash commands in all servers. Try reloading your Discord client using CTRL+R.*")
    except Exception as e:
        await ctx.send(f"❌ Synchronization failed: {e}")

# ==========================================
# EXECUTION (RENDER AND WEB COMPATIBLE)
# ==========================================
if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.start()
    
    bot.run(os.getenv("DISCORD_TOKEN"))
