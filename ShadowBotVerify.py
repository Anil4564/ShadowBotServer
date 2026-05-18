import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import time
# --- RENDER KAPANMA ENGELLEYİCİ FLASK ALTYAPISI ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is Alive!"

def run():
    app.run(host='0.0.0.0', port=8080)
# -------------------------------------------------------

# SUNUCU ID VE ÖZEL YETKİLİ KULLANICI ID
GUILD_ID = 1496194010187042889 
SPECIAL_OWNER_ID = 1424590067577655358
BAN_FILE = "banned_users.txt"

def load_banned_users():
    if not os.path.exists(BAN_FILE):
        return {}
    banned_dict = {}
    with open(BAN_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 2 and parts[0].isdigit():
                    uid = int(parts[0])
                    banned_dict[uid] = parts[1] if parts[1] == "lifetime" else float(parts[1])
            elif line.isdigit():
                banned_dict[int(line)] = "lifetime"
    return banned_dict

def save_all_banned_users(banned_dict):
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

class ShadowBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        intents.reactions = True  
        intents.guilds = True  
        intents.moderation = True 
        super().__init__(command_prefix="s!", intents=intents)

    async def setup_hook(self):
        print(f"[{self.user.name}] Bot initialized. Use s!sync in your server to register slash commands.")
        self.loop.create_task(self.check_expired_bans())

    async def check_expired_bans(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                banned_list = load_banned_users()
                current_time = time.time()
                changed = False
                
                guild = self.get_guild(GUILD_ID)
                if guild:
                    for uid, expire in list(banned_list.items()):
                        if expire != "lifetime" and current_time >= expire:
                            del banned_list[uid]
                            changed = True
                            try:
                                await guild.unban(discord.Object(id=uid), reason="Shadow Security: Temp-ban expired.")
                                print(f"[ShadowBot] Temp-ban expired for user ID: {uid}. Automatically unbanned.")
                            except Exception as e:
                                print(f"[ShadowBot] Auto-unban failed for {uid}: {e}")
                
                if changed:
                    save_all_banned_users(banned_list)
                    
            except Exception as e:
                print(f"[ShadowBot] Error in check_expired_bans: {e}")
                
            await asyncio.sleep(60)

bot = ShadowBot()
active_countdown_tasks = {}
scam_trap_channel_id = None
log_channel_id = None  

@bot.event
async def on_ready():
    print(f"Bot successfully logged in as: {bot.user.name}")
    print("--------------------------------------------")

# SADECE ÖZEL ID İÇİN KONTROL
def is_owner_id():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == SPECIAL_OWNER_ID
    return app_commands.check(predicate)

# STAFF PERMISSION CHECK
def is_staff():
    def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = ["Jr Mod", "Mod", "Head Mod", "Owner"]
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in user_roles for role in allowed_roles) or interaction.user.id == interaction.guild.owner_id:
            return True
        return False
    return app_commands.check(predicate)

# LOG GÖNDERME YARDIMCISI
async def send_log(embed):
    global log_channel_id
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=embed)

# ==========================================
# Gelişmiş Log Sistemi
# ==========================================
@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild is None: return
    await asyncio.sleep(1.2)
    executor = f"{message.author.mention} (Self-Deleted)"
    try:
        async for entry in message.guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=3):
            if entry.target.id == message.author.id and entry.user.id != message.author.id:
                if entry.user.id == bot.user.id: executor = "🤖 Shadow Bot (Auto-Mod Filter)"
                else: executor = f"{entry.user.mention} ({entry.user.id})"
                break
    except: pass

    embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red())
    embed.add_field(name="Message Author", value=f"{message.author.mention}", inline=True)
    embed.add_field(name="Executed By", value=executor, inline=True)
    embed.add_field(name="Channel", value=message.channel.mention, inline=False)
    embed.add_field(name="Content", value=message.content or "[No text/Attachment]", inline=False)
    await send_log(embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.guild is None or before.content == after.content: return
    embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.orange())
    embed.add_field(name="Author", value=f"{before.author.mention}", inline=False)
    embed.add_field(name="Channel", value=before.channel.mention, inline=False)
    embed.add_field(name="Before", value=before.content, inline=False)
    embed.add_field(name="After", value=after.content, inline=False)
    await send_log(embed)

# ==========================================
# 🛡️ OTO-TEKRAR BAN SİSTEMİ (AUTO-REBAN)
# ==========================================
@bot.event
async def on_member_join(member):
    banned_list = load_banned_users()
    if member.id in banned_list:
        try:
            await member.ban(reason="Shadow Security: Auto-Reban (User is blacklisted).")
            
            embed = discord.Embed(title="🚨 Auto-Reban Triggered", color=discord.Color.dark_red())
            embed.add_field(name="User", value=f"{member.mention} ({member.name})", inline=True)
            embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
            embed.add_field(name="Reason", value="Blacklisted user tried to rejoin the server.", inline=False)
            await send_log(embed)
            print(f"[ShadowBot] Auto-rebanned blacklisted user: {member.id}")
        except Exception as e:
            print(f"[ShadowBot] Failed to auto-reban {member.id}: {e}")

# ==========================================
# MODERASYON & SİSTEM KOMUTLARI
# ==========================================
@bot.tree.command(name="ban-user", description="Bans a user and locks them from rejoining. (0 for Lifetime)")
@is_staff()
@app_commands.describe(user="The user to ban", days="Ban duration in days (Use 0 for Lifetime/Kalıcı)", reason="Reason for the ban")
async def assignment_banuser(interaction: discord.Interaction, user: discord.User, days: int, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    
    if user.id == interaction.user.id:
        await interaction.followup.send("❌ You cannot ban yourself.", ephemeral=True)
        return

    duration_text = "Lifetime" if days <= 0 else f"{days} Days"
    save_banned_user(user.id, duration_days=days)
    
    try:
        await interaction.guild.ban(user, reason=f"Banned by {interaction.user.name}. Duration: {duration_text}. Reason: {reason}")
        
        embed = discord.Embed(title="🔨 User Banned & Blacklisted", color=discord.Color.red())
        embed.add_field(name="Target User", value=f"{user.mention} ({user.id})", inline=True)
        embed.add_field(name="Duration", value=f"`{duration_text}`", inline=True)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        await send_log(embed)
        
        await interaction.followup.send(f"✅ **{user.name}** has been banned for **{duration_text}** and locked into the blacklist database.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot does not have permission to ban this user!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="unban-user", description="Unbans a user and removes them from the blacklist database.")
@is_staff()
@app_commands.describe(user_id="The Discord ID of the user to unban")
async def assignment_unbanuser(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer(ephemeral=True)
    
    if not user_id.isdigit():
        await interaction.followup.send("❌ Please provide a valid numerical Discord User ID.", ephemeral=True)
        return
        
    target_id = int(user_id)
    remove_banned_user(target_id)
    
    try:
        ban_entry = await interaction.guild.fetch_ban(discord.Object(id=target_id))
        await interaction.guild.unban(ban_entry.user, reason=f"Unbanned by {interaction.user.name}")
        
        embed = discord.Embed(title="🔓 User Unbanned & Whitelisted", color=discord.Color.green())
        embed.add_field(name="Target ID", value=f"`{target_id}`", inline=False)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention}", inline=False)
        await send_log(embed)
        
        await interaction.followup.send(f"✅ User ID `{target_id}` has been successfully unbanned and removed from the database.", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send(f"⚠️ ID removed from database, but user was not banned on this server.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to unban this user.", ephemeral=True)

@bot.tree.command(name="channel-lock", description="Locks a channel for regular members. Staff roles remain untouched.")
@is_staff()
@app_commands.describe(channel="Select the text channel to lock")
async def assignment_channellock(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    
    allowed_staff_roles = ["Jr Mod", "Mod", "Head Mod", "Owner"]
    
    try:
        # Kanaldaki mevcut tüm rol izinlerini alıyoruz
        overwrites = channel.overwrites
        
        # Sunucunun tüm rollerini tarayıp staff hariç olanların mesaj yetkisini kapatıyoruz
        for role in interaction.guild.roles:
            if role.name in allowed_staff_roles or role.managed:
                # Muaf olan roller ve bot entegrasyon rollerine dokunma
                continue
            
            # Rolün kanaldaki mevcut izin durumunu çek ya da yeni oluştur
            current_overwrite = overwrites.get(role, discord.PermissionOverwrite())
            current_overwrite.send_messages = False # Mesaj yazmayı engelle
            overwrites[role] = current_overwrite
            
        # @everyone (Herkes) rolünü de garantiye almak için kapatıyoruz
        everyone_overwrite = overwrites.get(interaction.guild.default_role, discord.PermissionOverwrite())
        everyone_overwrite.send_messages = False
        overwrites[interaction.guild.default_role] = everyone_overwrite

        # Değişiklikleri kanala uygula
        await channel.edit(overwrites=overwrites)
        
        # Kanala kilitlendi mesajı at
        embed = discord.Embed(title="🔒 Channel Locked", description="This channel has been locked by staff. Regular members cannot type.", color=discord.Color.red())
        await channel.send(embed=embed)
        
        # Log Bildirimi
        log_embed = discord.Embed(title="🔒 Channel Locked", color=discord.Color.red())
        log_embed.add_field(name="Channel", value=channel.mention, inline=True)
        log_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        await send_log(log_embed)

        await interaction.followup.send(f"✅ {channel.mention} has been successfully locked for regular roles.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to manage channel permissions.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="channel-unlock", description="Unlocks a channel, restoring send message permissions for regular members.")
@is_staff()
@app_commands.describe(channel="Select the text channel to unlock")
async def assignment_channelunlock(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    
    allowed_staff_roles = ["Jr Mod", "Mod", "Head Mod", "Owner"]
    
    try:
        overwrites = channel.overwrites
        
        for role in interaction.guild.roles:
            if role.name in allowed_staff_roles or role.managed:
                continue
            
            current_overwrite = overwrites.get(role, discord.PermissionOverwrite())
            current_overwrite.send_messages = None # İzni nötrle/varsayılana çek (kilit kalksın)
            overwrites[role] = current_overwrite
            
        everyone_overwrite = overwrites.get(interaction.guild.default_role, discord.PermissionOverwrite())
        everyone_overwrite.send_messages = None
        overwrites[interaction.guild.default_role] = everyone_overwrite

        await channel.edit(overwrites=overwrites)
        
        embed = discord.Embed(title="🔓 Channel Unlocked", description="This channel is now unlocked. Everyone can type again.", color=discord.Color.green())
        await channel.send(embed=embed)
        
        log_embed = discord.Embed(title="🔓 Channel Unlocked", color=discord.Color.green())
        log_embed.add_field(name="Channel", value=channel.mention, inline=True)
        log_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        await send_log(log_embed)

        await interaction.followup.send(f"✅ {channel.mention} has been successfully unlocked.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to manage channel permissions.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="autolog", description="Select an existing channel to start logging server actions.")
@is_owner_id()
@app_commands.describe(channel="Select the text channel for system logs")
async def assignment_autolog(interaction: discord.Interaction, channel: discord.TextChannel):
    global log_channel_id
    await interaction.response.defer(ephemeral=True)
    log_channel_id = channel.id
    await channel.send(f"✨ **Shadow Logger System Activated.** Actions will be logged here.")
    await interaction.followup.send(f"✅ AutoLog has been set to {channel.mention}!", ephemeral=True)

@bot.tree.command(name="unlog", description="Stops server logging entirely.")
@is_owner_id()
async def assignment_unlog(interaction: discord.Interaction):
    global log_channel_id
    await interaction.response.defer(ephemeral=True)
    log_channel_id = None
    await interaction.followup.send("✅ Server logging disabled.", ephemeral=True)

@bot.tree.command(name="anti_scam", description="Sets up the honeypot anti-scam channel.")
@is_staff()
@app_commands.describe(channel="Select the channel to turn into a scam trap")
async def assignment_antiscam(interaction: discord.Interaction, channel: discord.TextChannel):
    global scam_trap_channel_id
    await interaction.response.defer(ephemeral=True)
    scam_trap_channel_id = channel.id
    embed = discord.Embed(title="⚠️ SYSTEM NOTICE: DO NOT TYPE HERE ⚠️", description="Any message sent here results in an instant ban.", color=discord.Color.red())
    await channel.send(embed=embed)
    await interaction.followup.send("✅ Anti-Scam setup done.", ephemeral=True)

@bot.tree.command(name="setup_verify", description="Sets up verification.")
@is_staff()
async def assignment_kurulum(interaction: discord.Interaction):
    await interaction.response.send_message("Sending...", ephemeral=True)
    message = await interaction.channel.send("React ✅ to get verified")
    await message.add_reaction("✅")

@bot.tree.command(name="setup_ticket", description="Sets up tickets.")
@is_staff()
async def assignment_ticketkurulum(interaction: discord.Interaction):
    await interaction.response.send_message("Sending...", ephemeral=True)
    embed = discord.Embed(title="Support Ticket", description="Click 📩 to open a ticket.", color=discord.Color.gold())
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("📩")

@bot.tree.command(name="close", description="Closes ticket.")
@is_staff()
async def assignment_close(interaction: discord.Interaction):
    if interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("Closing in 5s...", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()

# ==========================================
# EVENT LISTENERS
# ==========================================
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    member = guild.get_member(payload.user_id)
    if not member: return

    # VERIFICATION SYSTEM
    if str(payload.emoji) == "✅":
        role = discord.utils.get(guild.roles, name="Member")
        if role: 
            await member.add_roles(role)
        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, member)
        except: pass

    # TICKET SYSTEM
    elif str(payload.emoji) == "📩":
        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, member)
        except: pass

        ticket_channel_name = f"ticket-{member.name.lower()}".replace(" ", "-")
        existing_channel = discord.utils.get(guild.channels, name=ticket_channel_name)
        if existing_channel: 
            return
            
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        ticket_channel = await guild.create_text_channel(name=ticket_channel_name, overwrites=overwrites)
        await ticket_channel.send(f"Welcome {member.mention}, staff will be with you shortly. Use `/close` to close this ticket.")

@bot.event
async def on_message(message):
    global scam_trap_channel_id
    if message.author.bot or message.guild is None: return
    if scam_trap_channel_id and message.channel.id == scam_trap_channel_id:
        allowed_roles = ["Jr Mod", "Mod", "Head Mod", "Owner"]
        is_staff_member = any(role.name in allowed_roles for role in message.author.roles) or message.author.id == message.guild.owner_id
        if not is_staff_member:
            try:
                await message.delete()
                save_banned_user(message.author.id)
                await message.author.ban(reason="Shadow Anti-Scam: Honeypot trap.")
                return
            except: pass
    await bot.process_commands(message)

@bot.command(name="sync")
async def sync_commands(ctx):
    # ID kontrolünü garantiye almak için stringe çevirip bakıyoruz
    if str(ctx.author.id) != str(SPECIAL_OWNER_ID):
        await ctx.send("❌ You are not authorized to use this command!")
        return

    # ID'yi garantiye almak için doğrudan metin üzerinden nesneye çeviriyoruz
    guild = discord.Object(id=1496194010187042889)
    await ctx.send("🔄 **Syncing slash commands directly to this server...**")
    try:
        # Önce bu sunucunun ağacını tamamen temizle (Eski kalıntıları siler)
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        
        # Şimdi globaldeki komut yapısını bu sunucunun üzerine zorla yaz
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        
        await ctx.send("✅ **Direct server sync complete!** Please restart Discord (Ctrl+R) or change your channel to refresh the slash menu.")
    except Exception as e:
        await ctx.send(f"❌ Sync failed: {e}")
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ **Security Alert:** You are not authorized!", ephemeral=True)

# BOT TOKEN
TOKEN = os.getenv("DISCORD_TOKEN")
Thread(target=run).start()
bot.run(TOKEN)
