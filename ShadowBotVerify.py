import discord
import datetime
import re
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

# Render Kalıcı Disk (Persistent Disk) için dosya yolu güncellendi
BAN_FILE = "/data/banned_users.txt"

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
# BUTTON VE PANEL GÖRÜNÜMLERİ (VIEWS)
# ==========================================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green, custom_id="persistent_verify_button", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Member")
        if not role:
            await interaction.response.send_message("❌ 'Member' role could not be found! Please notify the administration.", ephemeral=True)
            return
        
        if role in interaction.user.roles:
            await interaction.response.send_message("⚠️ You are already verified!", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Verification successful! Welcome to the server.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ The bot lacks permission to assign roles. Check the role hierarchy.", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="persistent_ticket_close", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("🔒 This ticket will be closed and deleted in 5 seconds...", ephemeral=False)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ This command can only be executed within a ticket channel.", ephemeral=True)

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_ticket_open", emoji="📩")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        ticket_channel_name = f"ticket-{member.name.lower()}".replace(" ", "-")
        existing_channel = discord.utils.get(guild.channels, name=ticket_channel_name)
        
        if existing_channel: 
            await interaction.response.send_message(f"⚠️ You already have an open support ticket: {existing_channel.mention}", ephemeral=True)
            return
            
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        try:
            ticket_channel = await guild.create_text_channel(name=ticket_channel_name, overwrites=overwrites)
            
            embed = discord.Embed(
                title="✨ Support Ticket Created", 
                description=f"Welcome {member.mention}, our support team will be with you shortly.\n\nIf you want to close this ticket, click the red button below.", 
                color=discord.Color.green()
            )
            await ticket_channel.send(embed=embed, view=TicketCloseView())
            await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to create ticket channel: {e}", ephemeral=True)

# Boş görünüm (DM bildirimlerinde buton hatası oluşmaması için gerekli)
class AntiNukeBotActionView(discord.ui.View):
    def __init__(self, guild_id, bot_id):
        super().__init__(timeout=None)

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
scam_panel_message_id = None  
log_channel_id = None  

@bot.event
async def on_ready():
    print(f"Bot successfully logged in as: {bot.user.name}")
    print("--------------------------------------------")

def is_staff():
    def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = ["Mod", "Owner"]
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in user_roles for role in allowed_roles) or interaction.user.id == interaction.guild.owner_id or interaction.user.id == SPECIAL_OWNER_ID:
            return True
        return False
    return app_commands.check(predicate)
    
async def send_log(embed):
    global log_channel_id
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=embed)

# ==========================================
# 🚨 Gelişmiş Anti-Nuke Tetikleyicileri
# ==========================================
async def nuke_punish(guild, user_id, action_type):
    try:
        member = await guild.fetch_member(user_id)
        if member.id == guild.owner_id or member.id == SPECIAL_OWNER_ID or member.id == bot.user.id:
            return 
        
        try:
            await member.edit(roles=[])
        except:
            pass
        
        save_banned_user(member.id)
        await member.ban(reason=f"Shadow Anti-Nuke: Toplu {action_type} limiti aşıldı!")
        
        embed = discord.Embed(title="🚨 ANTI-NUKE SİSTEMİ DEVREDE", color=discord.Color.dark_red())
        embed.description = f"**Zararlı Yetkili Cezalandırıldı!**\n\n**Kullanıcı:** {member.mention} (`{member.id}`)\n**Sebep:** Kısa sürede toplu veya agresif `{action_type}` işlemi gerçekleştirdi.\n**İşlem:** Tüm rolleri alındı ve kalıcı olarak banlandı."
        await send_log(embed)
    except Exception as e:
        print(f"Anti-nuke cezalandırma hatası: {e}")

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
            return
        except Exception as e:
            print(f"[ShadowBot] Failed to auto-reban {member.id}: {e}")

    if member.bot and bot.anti_nuke_status:
        owner = await bot.fetch_user(SPECIAL_OWNER_ID)
        if owner:
            try:
                embed = discord.Embed(
                    title="⚠️ Anti-Nuke: Yeni Bot Tespit Edildi!",
                    description=f"**{member.guild.name}** Added New Bot\n\n**Bot İsmi:** {member.mention}\n**Bot ID:** `{member.id}`",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                await owner.send(embed=embed, view=AntiNukeBotActionView(guild_id=member.guild.id, bot_id=member.id))
            except Exception as e:
                print(f"Özel yetkiliye DM gönderilemedi: {e}")

@bot.event
async def on_guild_channel_delete(channel):
    if not bot.anti_nuke_status or channel.guild is None:
        return
    
    async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        user_id = entry.user.id
        current_time = time.time()
        
        if user_id not in bot.channel_deletions:
            bot.channel_deletions[user_id] = []
            
        bot.channel_deletions[user_id].append(current_time)
        bot.channel_deletions[user_id] = [t for t in bot.channel_deletions[user_id] if current_time - t <= 10]
        
        if len(bot.channel_deletions[user_id]) >= 2:
            await nuke_punish(channel.guild, user_id, "Kanal Silme")

@bot.event
async def on_guild_role_delete(role):
    if not bot.anti_nuke_status or role.guild is None:
        return
    
    async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        user_id = entry.user.id
        current_time = time.time()
        
        if user_id not in bot.role_deletions:
            bot.role_deletions[user_id] = []
            
        bot.role_deletions[user_id].append(current_time)
        bot.role_deletions[user_id] = [t for t in bot.role_deletions[user_id] if current_time - t <= 10]
        
        if len(bot.role_deletions[user_id]) >= 2:
            await nuke_punish(role.guild, user_id, "Rol Silme")

@bot.event
async def on_member_ban(guild, user):
    if not bot.anti_nuke_status:
        return
    
    async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
        user_id = entry.user.id
        if user_id == bot.user.id:
            return
            
        current_time = time.time()
        
        if user_id not in bot.member_bans:
            bot.member_bans[user_id] = []
            
        bot.member_bans[user_id].append(current_time)
        bot.member_bans[user_id] = [t for t in bot.member_bans[user_id] if current_time - t <= 10]
        
        if len(bot.member_bans[user_id]) >= 2:
            await nuke_punish(guild, user_id, "Sağ Tık Sağır Banlama")

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
# MESAJ KONTROLLERİ
# ==========================================
@bot.event
async def on_message(message):
    global scam_trap_channel_id, scam_panel_message_id
    if message.author.bot or message.guild is None: return

    allowed_roles = ["Mod", "Owner"]
    is_staff_member = any(role.name in allowed_roles for role in message.author.roles) or message.author.id == message.guild.owner_id or message.author.id == SPECIAL_OWNER_ID

    if scam_trap_channel_id and message.channel.id == scam_trap_channel_id:
        if not is_staff_member:
            try:
                await message.delete()
                save_banned_user(message.author.id)
                await message.author.ban(reason="Shadow Anti-Scam: Honeypot trap.")
                
                if scam_panel_message_id:
                    try:
                        panel_msg = await message.channel.fetch_message(scam_panel_message_id)
                        updated_embed = discord.Embed(
                            title="⚠️ SYSTEM NOTICE: DO NOT TYPE HERE ⚠️",
                            description="Any message sent here results in an instant ban.",
                            color=discord.Color.red()
                        )
                        updated_embed.add_field(name="📊 Kicks", value=f"`{get_total_bans()}`", inline=False)
                        await panel_msg.edit(embed=updated_embed)
                    except discord.NotFound:
                        new_embed = discord.Embed(
                            title="⚠️ SYSTEM NOTICE: DO NOT TYPE HERE ⚠️",
                            description="Any message sent here results in an instant ban.",
                            color=discord.Color.red()
                        )
                        new_embed.add_field(name="📊 Kicks", value=f"`{get_total_bans()}`", inline=False)
                        fallback_msg = await message.channel.send(embed=new_embed)
                        scam_panel_message_id = fallback_msg.id
                return
            except Exception as e:
                print(f"[ShadowBot] Honeypot hata: {e}")

    if not is_staff_member:
        link_match = re.search(r'(https?://[^\s]+)|(discord\.gg/[^\s]+)', message.content.lower())
        if link_match:
            try:
                await message.delete()
                warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, sharing links is strictly prohibited in this server!")
                
                embed = discord.Embed(title="🛡️ Link Blocked", color=discord.Color.orange())
                embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})", inline=True)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.add_field(name="Content", value=f"||{message.content}||", inline=False)
                await send_log(embed)
                
                await asyncio.sleep(5)
                await warn_msg.delete()
                return
            except: pass

    await bot.process_commands(message)

# ==========================================
# MODERASYON & SİSTEM KOMUTLARI
# ==========================================
@bot.tree.command(name="anti_nuke", description="Gelişmiş nuke koruma modülünü açar veya kapatır.")
@is_staff()
@app_commands.describe(durum="Sistem aktif edilsin mi? (True = Açık, False = Kapalı)")
async def assignment_antinuke(interaction: discord.Interaction, durum: bool):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != SPECIAL_OWNER_ID and interaction.user.id != interaction.guild.owner_id:
        await interaction.followup.send("❌ Bu komut kritik bir sistem ayarı olduğu için sadece kurucu tarafından kullanılabilir!", ephemeral=True)
        return
        
    bot.anti_nuke_status = durum
    metin = "🟢 **AKTİF**" if durum else "🔴 **DEVRE DIŞI**"
    await interaction.followup.send(f"🛡️ Anti-Nuke güvenlik duvarı başarıyla {metin} konumuna getirildi.", ephemeral=True)

@bot.tree.command(name="copyserver", description="Target sunucudaki kanalları kopyalayıp Main sunucuya aktarır (ÖNCE MAİN'DEKİLERİ SİLER).")
@is_staff()
@app_commands.describe(main_server_id="Kanalların sıfırlanıp OLUŞTURULACAĞI sunucu ID'si", target_server_id="Kanalların KOPYALANACAĞI kaynak sunucu ID'si")
async def assignment_copyserver(interaction: discord.Interaction, main_server_id: str, target_server_id: str):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != SPECIAL_OWNER_ID and interaction.user.id != interaction.guild.owner_id:
        await interaction.followup.send("❌ Bu komut çok tehlikeli olduğu için sadece kurucu tarafından kullanılabilir!", ephemeral=True)
        return

    if not main_server_id.isdigit() or not target_server_id.isdigit():
        await interaction.followup.send("❌ Lütfen geçerli sayısal ID'ler girin.", ephemeral=True)
        return

    main_guild = bot.get_guild(int(main_server_id))
    target_guild = bot.get_guild(int(target_server_id))

    if not main_guild:
        await interaction.followup.send("❌ **Main Server** bulunamadı! Botun o sunucuda olduğundan emin olun.", ephemeral=True)
        return
    if not target_guild:
        await interaction.followup.send("❌ **Target Server** bulunamadı! Botun o sunucuda olduğundan emin olun.", ephemeral=True)
        return

    await interaction.followup.send(f"⚠️ Klonlama işlemi başladı!\n**Main Server:** {main_guild.name}\n**Target Server:** {target_guild.name}\n\n*Önce Main Server'daki eski kanallar temizleniyor...*", ephemeral=True)

    for channel in main_guild.channels:
        try:
            await channel.delete(reason="Server Copy: Eski kanalların temizlenmesi.")
        except discord.Forbidden:
            print(f"[{main_guild.name}] {channel.name} silinemedi (Yetki yetersiz).")
        except Exception as e:
            print(f"Hata: {e}")

    await asyncio.sleep(2)
    category_mapping = {}

    for category in sorted(target_guild.categories, key=lambda c: c.position):
        try:
            new_category = await main_guild.create_category(name=category.name, position=category.position)
            category_mapping[category.id] = new_category
        except Exception as e:
            print(f"Kategori oluşturulamadı ({category.name}): {e}")

    for channel in sorted(target_guild.channels, key=lambda c: c.position):
        if isinstance(channel, discord.CategoryChannel):
            continue 

        target_category = category_mapping.get(channel.category_id) if channel.category else None
        try:
            if isinstance(channel, discord.TextChannel):
                await main_guild.create_text_channel(name=channel.name, topic=channel.topic, nsfw=channel.nsfw, position=channel.position, category=target_category)
            elif isinstance(channel, discord.VoiceChannel):
                await main_guild.create_voice_channel(name=channel.name, user_limit=channel.user_limit, position=channel.position, category=target_category)
        except Exception as e:
            print(f"Kanal oluşturulamadı ({channel.name}): {e}")

    await interaction.followup.send(f"✅ **Klonlama Başarıyla Tamamlandı!**\n`{target_guild.name}` sunucusunun kanal yapısı `{main_guild.name}` sunucusuna tamamen aktarıldı.", ephemeral=True)

@bot.tree.command(name="check-ban-file", description="Banned users dosyasının içeriğini gösterir.")
@is_staff() 
async def assignment_checkbanfile(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not os.path.exists(BAN_FILE):
        await interaction.followup.send("❌ Dosya henüz oluşturulmamış (Henüz kimse banlanmadı).", ephemeral=True)
        return
        
    with open(BAN_FILE, "r") as f:
        content = f.read()
        
    if not content.strip():
        await interaction.followup.send("📂 Dosya mevcut ama içi tamamen boş.", ephemeral=True)
        return
        
    with open("temp_show.txt", "w") as tf:
        tf.write(content)
        
    await interaction.followup.send("📂 Güncel ban dosyası ektedir:", file=discord.File("temp_show.txt"), ephemeral=True)
    os.remove("temp_show.txt")

@bot.tree.command(name="timeout", description="Mutes a member for a specified duration using Discord Timeout.")
@is_staff()
@app_commands.describe(user="The member to mute", minutes="Duration in minutes", reason="Reason for the timeout")
async def assignment_timeout(interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    if user.id == interaction.user.id:
        await interaction.followup.send("❌ You cannot timeout yourself.", ephemeral=True)
        return

    if minutes < 1 or minutes > 40320:
        await interaction.followup.send("❌ Please enter a duration between 1 minute and 28 days (40320 minutes).", ephemeral=True)
        return

    duration = datetime.timedelta(minutes=minutes)
    try:
        await user.timeout(duration, reason=f"Moderator: {interaction.user.name} | Reason: {reason}")
        embed = discord.Embed(title="🤫 User Timed Out", color=discord.Color.orange())
        embed.add_field(name="Target User", value=f"{user.mention} ({user.id})", inline=True)
        embed.add_field(name="Duration", value=f"`{minutes} Minutes`", inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        await send_log(embed)
        await interaction.followup.send(f"✅ **{user.name}** has been successfully timed out for `{minutes}` minutes.", ephemeral=False)
    except discord.Forbidden:
        await interaction.followup.send("❌ The bot lacks permission to timeout this member (Role hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="ban-user", description="Bans a user and locks them from rejoining. (0 for Lifetime)")
@is_staff()
@app_commands.describe(user="The user to ban", days="Ban duration in days (Use 0 for Lifetime)", reason="Reason for the ban")
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
        
        global scam_trap_channel_id, scam_panel_message_id
        if scam_trap_channel_id and scam_panel_message_id:
            try:
                chan = bot.get_channel(scam_trap_channel_id)
                msg = await chan.fetch_message(scam_panel_message_id)
                up_embed = discord.Embed(title="⚠️ SYSTEM NOTICE: DO NOT TYPE HERE ⚠️", description="Any message sent here results in an instant ban.", color=discord.Color.red())
                up_embed.add_field(name="📊 Kicks", value=f"`{get_total_bans()}`", inline=False)
                await msg.edit(embed=up_embed)
            except: pass
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
        
        global scam_trap_channel_id, scam_panel_message_id
        if scam_trap_channel_id and scam_panel_message_id:
            try:
                chan = bot.get_channel(scam_trap_channel_id)
                msg = await chan.fetch_message(scam_panel_message_id)
                up_embed = discord.Embed(title="⚠️ SYSTEM NOTICE: DO NOT TYPE HERE ⚠️", description="Any message sent here results in an instant ban.", color=discord.Color.red())
                up_embed.add_field(name="📊 Kicks", value=f"`{get_total_bans()}`", inline=False)
                await msg.edit(embed=up_embed)
            except: pass
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
    allowed_staff_roles = ["Mod", "Owner"]
    try:
        overwrites = channel.overwrites
        for role in interaction.guild.roles:
            if role.name in allowed_staff_roles or role.managed:
                continue
            overwrites[role] = discord.PermissionOverwrite(send_messages=False)
        await channel.edit(overwrites=overwrites)
        await interaction.followup.send(f"🔒 {channel.mention} has been locked for members.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to lock channel: {e}", ephemeral=True)

@bot.command(name="sync")
async def sync_commands(ctx):
    user_roles = [role.name for role in ctx.author.roles]
    is_server_owner = ctx.author.id == ctx.guild.owner_id
    if ctx.author.id != SPECIAL_OWNER_ID and not is_server_owner and "Owner" not in user_roles and "Mod" not in user_roles:
        await ctx.send("❌ You are not authorized to use this command!")
        return

    await ctx.send("🔄 **Global Syncing slash commands... Please wait.**")
    try:
        await bot.tree.sync()
        await ctx.send("✅ **Global Sync complete!** It might take a few minutes to update everywhere.")
    except Exception as e:
        await ctx.send(f"❌ Sync failed: {e}")

# Flask Sunucusunu Ayrı Thread'de Başlatma
def run_flask():
    run()

if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.start()
    
    # Token buraya gelecek (Çevresel değişken veya string)
    # bot.run(os.getenv("DISCORD_TOKEN"))
    bot.run("TOKEN_BURAYA")
