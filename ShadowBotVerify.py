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
ALLOWED_STAFF_ROLES = ["Mod", "Owner"]

# ==========================================
# İSTATİSTİK KANAL AYARLARI
# ==========================================
STATS_CHANNEL_ID = 123456789012345678  # <--- Buraya kendi ses kanalının ID'sini yaz!

# AGRESSIVE ANTI-NUKE RATELIMITS (Saniyede 1 işlem sınırı)
LIMIT_TIME = 5.0  # Kaç saniye kontrol edilecek
MAX_ALLOWED = 1   # Bu saniyede en fazla kaç işleme izin var (1 idealdir, 2. işlem nuke sayılır)

def is_staff_member(member: discord.Member) -> bool:
    if member.id == SPECIAL_OWNER_ID or member.id == member.guild.owner_id:
        return True
    return any(r.name in ALLOWED_STAFF_ROLES for r in member.roles)

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

async def update_server_stats(guild):
    """Sunucu üye sayısına göre ses kanalının adını günceller"""
    if not guild: return
    
    ch = guild.get_channel(STATS_CHANNEL_ID)
    if ch and isinstance(ch, discord.VoiceChannel):
        total_members = guild.member_count
        new_name = f"「🌍」Community: {total_members} People"
        
        # Eğer kanal adı zaten aynıysa Discord API'sini gereksiz yormamak için güncelleme yapma
        if ch.name != new_name:
            try:
                await ch.edit(name=new_name)
            except Exception as e:
                print(f"Stats Channel Update Error: {e}")

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
            await interaction.response.send_message("✅ Verification successful! Welcome to the server.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Hierarchy error.", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="persistent_ticket_close", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("❌ Only staff members can close tickets!", ephemeral=True)
            return

        if interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("🔒 Ticket closing in 5 seconds...", ephemeral=False)
            await asyncio.sleep(5)
            await interaction.channel.delete()

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_ticket_open", emoji="📩")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        tn = f"ticket-{member.name.lower()}".replace(" ", "-")
        
        if discord.utils.get(guild.channels, name=tn): 
            await interaction.followup.send("⚠️ You already have an open ticket!", ephemeral=True)
            return
            
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        for role_name in ALLOWED_STAFF_ROLES:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ch = await guild.create_text_channel(name=tn, overwrites=overwrites)
            embed = discord.Embed(
                title="🎫 Support Ticket Created", 
                description=f"Welcome {member.mention},\n\nOur support team will be with you shortly.",
                color=discord.Color.blue()
            )
            await ch.send(embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"✅ Ticket created successfully: {ch.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create ticket: {e}", ephemeral=True)

# ==========================================
# MAIN BOT CLASS WITH ULTRA ANTI-NUKE
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
        
        # Hafıza tabanlı anlık takip sözlükleri (Daha hızlı tetiklenme için)
        self.action_logs = {
            "channel_delete": {},
            "role_delete": {},
            "ban": {},
            "kick": {},
            "bot_add": {}
        }

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
log_channel_id = None  

def is_admin_slash():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_staff_member(interaction.user):
            return True
        await interaction.response.send_message("❌ You do not have permission to use this administrative command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.event
async def on_ready():
    print(f"[{bot.user.name}] SECURITY BOT IS ONLINE. Type s!sync to load commands.")
    # Bot açılır açılmaz ana sunucunun istatistiğini günceller
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await update_server_stats(guild)

async def send_log(embed):
    if log_channel_id:
        ch = bot.get_channel(log_channel_id)
        if ch: await ch.send(embed=embed)

# ==========================================
# GELİŞMİŞ KURŞUN GEÇİRMEZ ANTI-NUKE MOTORU
# ==========================================
async def dynamic_nuke_check(guild, action_type, discord_action):
    """Saniyeler içinde nuke atan kişiyi tespit edip yok eden ana motor"""
    if not bot.anti_nuke_status or not guild: return

    # Audit log'dan son işlemi aşırı hızlıca çek
    async for entry in guild.audit_logs(action=discord_action, limit=1):
        user = entry.user
        
        # Botun kendisi veya ana kurucu ise işlem yapma
        if user.id == bot.user.id or user.id == SPECIAL_OWNER_ID: return
        
        # Sunucu sahibi hesabı çalınmış olabilir, nuke atıyorsa onu bile engelle!
        # (İstersen aşağıdaki satırı aktif edebilirsin, şimdilik owner korumalı)
        if user.id == guild.owner_id: return 

        current_time = time.time()
        if user.id not in bot.action_logs[action_type]:
            bot.action_logs[action_type][user.id] = []

        # Zaman aşımına uğramış eski kayıtları temizle
        bot.action_logs[action_type][user.id] = [t for t in bot.action_logs[action_type][user.id] if current_time - t <= LIMIT_TIME]
        
        # Yeni işlemi listeye ekle
        bot.action_logs[action_type][user.id].append(current_time)

        # Eğer belirlenen sürede limit aşıldıysa ACİL MÜDAHALE
        if len(bot.action_logs[action_type][user.id]) > MAX_ALLOWED:
            await execute_emergency_punishment(guild, user, f"Mass {action_type.replace('_', ' ').title()}")

async def execute_emergency_punishment(guild, user, reason):
    """Zararlı yetkiliyi saniyeler içinde sunucudan kazıyan fonksiyon"""
    try:
        member = await guild.fetch_member(user.id)
        if not member: return

        # 1. HAMLE: Tüm rollerini hemen sil (Rol silmek banlamaktan daha hızlıdır ve yetkilerini anında sıfırlar!)
        try: 
            await member.edit(roles=[], reason="Anti-Nuke Emergency Lockdown")
        except: pass

        # 2. HAMLE: Kalıcı veritabanına ekle ve banla
        save_banned_user(member.id)
        await member.ban(reason=f"🚨 SHADOW ANTI-NUKE: {reason}")

        # Log Gönder
        embed = discord.Embed(
            title="🚨 ULTRA ANTI-NUKE TETİKLENDİ", 
            description=f"**Saldırgan:** {member.mention} (`{member.id}`)\n**Sebep:** {reason}\n\n**Uygulanan İşlem:** Bütün rolleri alındı ve sunucudan kalıcı olarak uzaklaştırıldı.",
            color=discord.Color.dark_red()
        )
        await send_log(embed)
    except Exception as e:
        print(f"Punishment Error: {e}")

# --- TETİKLEYİCİ EVENTLER ---

@bot.event
async def on_guild_channel_delete(channel):
    await dynamic_nuke_check(channel.guild, "channel_delete", discord.AuditLogAction.channel_delete)

@bot.event
async def on_guild_role_delete(role):
    await dynamic_nuke_check(role.guild, "role_delete", discord.AuditLogAction.role_delete)

@bot.event
async def on_member_ban(guild, user):
    await dynamic_nuke_check(guild, "ban", discord.AuditLogAction.ban)

@bot.event
async def on_member_remove(member):
    await update_server_stats(member.guild)
    # Sağ tık kick işlemlerini yakalamak için
    await dynamic_nuke_check(member.guild, "kick", discord.AuditLogAction.kick)

@bot.event
async def on_member_join(member):
    await update_server_stats(member.guild)
    # Karalistede ise anında re-ban
    if member.id in load_banned_users():
        try: await member.ban(reason="Blacklist Auto-Reban"); return
        except: pass
        
    # Sunucuya izinsiz bot ekleme koruması (En büyük nuke yöntemlerinden biri)
    if member.bot and bot.anti_nuke_status:
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
            inviter = entry.user
            if inviter.id != SPECIAL_OWNER_ID and inviter.id != member.guild.owner_id:
                # Botu ekleyen yetkiliyi anında banla ve eklenen botu şutla
                await execute_emergency_punishment(member.guild, inviter, "Unauthorized Bot Invitation")
                try: await member.ban(reason="Anti-Nuke: Unapproved Malicious Bot")
                except: pass

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
    global scam_trap_channel_id
    if message.author.bot or not message.guild: return

    if scam_trap_channel_id and message.channel.id == scam_trap_channel_id:
        try:
            await message.delete()
            save_banned_user(message.author.id)
            await message.author.ban(reason="Honeypot Trap")
            return
        except: pass

    if not is_staff_member(message.author) and re.search(r'(https?://[^\s]+)|(discord\.gg/[^\s]+)', message.content.lower()):
        try:
            await message.delete()
            return
        except: pass

    await bot.process_commands(message)

# ==========================================
# SLASH COMMANDS (ALL ADMINS ONLY)
# ==========================================

@bot.tree.command(name="anti_nuke", description="Enables or disables the anti-nuke system.")
@app_commands.describe(durum="True = Enabled, False = Disabled")
@is_admin_slash()
async def assignment_antinuke(interaction: discord.Interaction, durum: bool):
    bot.anti_nuke_status = durum
    await interaction.response.send_message(f"🛡️ Anti-Nuke status updated: {durum}", ephemeral=True)

@bot.tree.command(name="copyserver", description="Copies all channels and categories.")
@is_admin_slash()
async def assignment_copyserver(interaction: discord.Interaction, main_server_id: str, target_server_id: str):
    await interaction.response.defer(ephemeral=True)
    main_guild = bot.get_guild(int(main_server_id))
    target_guild = bot.get_guild(int(target_server_id))

    if not main_guild or not target_guild:
        await interaction.followup.send("❌ One of the servers could not be found!", ephemeral=True)
        return

    for channel in main_guild.channels:
        try: await channel.delete()
        except: pass

    category_mapping = {}
    for category in sorted(target_guild.categories, key=lambda c: c.position):
        try:
            new_cat = await main_guild.create_category(name=category.name, position=category.position)
            category_mapping[category.id] = new_cat
        except: pass

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
@is_admin_slash()
async def assignment_checkbanfile(interaction: discord.Interaction):
    if not os.path.exists(BAN_FILE):
        await interaction.response.send_message("❌ Blacklist database file is empty.", ephemeral=True)
        return
    await interaction.response.send_message(file=discord.File(BAN_FILE), ephemeral=True)

@bot.tree.command(name="timeout", description="Mutes a user.")
@is_admin_slash()
async def assignment_timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "None"):
    try:
        await user.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"✅ {user.name} has been timed out successfully.")
    except:
        await interaction.response.send_message("❌ Insufficient permissions.", ephemeral=True)

@bot.tree.command(name="ban-user", description="Bans a user and adds to blacklist.")
@is_admin_slash()
async def assignment_banuser(interaction: discord.Interaction, user: discord.User, days: int, reason: str = "None"):
    save_banned_user(user.id, duration_days=days)
    try:
        await interaction.guild.ban(user, reason=reason)
        await interaction.response.send_message(f"✅ {user.name} has been banned.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to ban.", ephemeral=True)

@bot.tree.command(name="unban-user", description="Removes user from blacklist.")
@is_admin_slash()
async def assignment_unbanuser(interaction: discord.Interaction, user_id: str):
    uid = int(user_id)
    remove_banned_user(uid)
    try:
        await interaction.guild.unban(discord.Object(id=uid))
        await interaction.response.send_message("✅ User unbanned.", ephemeral=True)
    except:
        await interaction.response.send_message("⚠️ Unbanned from DB only.", ephemeral=True)

@bot.tree.command(name="channel-lock", description="Locks a channel.")
@is_admin_slash()
async def assignment_channellock(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        overwrites = channel.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(send_messages=False)
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message(f"🔒 {channel.mention} locked.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="channel-unlock", description="Unlocks a channel.")
@is_admin_slash()
async def assignment_channelunlock(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        overwrites = channel.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(send_messages=True)
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message(f"🔓 {channel.mention} unlocked.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="secure-server-permissions", description="Locks down all channel permissions for security.")
@is_admin_slash()
async def assignment_secureserverpermissions(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    member_role = discord.utils.get(guild.roles, name="Member")
    everyone_role = guild.default_role

    if not member_role:
        await interaction.followup.send("❌ 'Member' role could not be found!", ephemeral=True)
        return

    success_count = 0
    for channel in guild.channels:
        try:
            overwrites = channel.overwrites
            if isinstance(channel, discord.VoiceChannel):
                overwrites[everyone_role] = discord.PermissionOverwrite(connect=False)
                overwrites[member_role] = discord.PermissionOverwrite(connect=False)
            else:
                overwrites[everyone_role] = discord.PermissionOverwrite(view_channel=False)
                overwrites[member_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
            await channel.edit(overwrites=overwrites)
            success_count += 1
        except: continue
    await interaction.followup.send(f"✅ Permissions synchronized for `{success_count}` channels.", ephemeral=True)

@bot.tree.command(name="setup-verify", description="Sends verification panel.")
@is_admin_slash()
async def setup_verify(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="🔒 Member Verification", description="Click green button to verify.", color=discord.Color.green())
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.followup.send("✅ Posted.", ephemeral=True)

@bot.tree.command(name="setup-ticket", description="Sends ticket panel.")
@is_admin_slash()
async def setup_ticket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="📩 Create a Support Ticket", description="Click blue button to open a ticket.", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=TicketOpenView())
    await interaction.followup.send("✅ Posted.", ephemeral=True)

# ==========================================
# SYNC COMMAND
# ==========================================
@bot.command(name="sync")
async def sync_commands(ctx):
    if ctx.author.id != SPECIAL_OWNER_ID and ctx.author.id != ctx.guild.owner_id: return
    await ctx.send("🔄 **Syncing commands...**")
    try:
        await bot.tree.sync()
        await ctx.send("✅ **Success!** Slash commands loaded.")
    except Exception as e:
        await ctx.send(f"❌ Failed: {e}")

if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.start()
    bot.run(os.getenv("DISCORD_TOKEN"))
