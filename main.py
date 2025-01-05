import discord
from discord.ext import commands
import logging
import asyncio
import sqlite3
import re
import os
from collections import defaultdict
import time
from datetime import timedelta, datetime
TOKEN = os.getenv('B')

# الاتصال بقاعدة البيانات (ستنشأ إذا لم تكن موجودة)
conn = sqlite3.connect('excluded_channels.db')
cursor = conn.cursor()

# إنشاء جدول لتخزين القنوات المستثناة
cursor.execute('''CREATE TABLE IF NOT EXISTS excluded_channels (channel_id INTEGER PRIMARY KEY)''')
conn.commit()

# دالة لإضافة قناة إلى الاستثناءات
def add_to_excluded(channel_id):
    cursor.execute("INSERT OR IGNORE INTO excluded_channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()

# دالة لتحميل القنوات المستثناة من قاعدة البيانات
def load_excluded_channels():
    cursor.execute("SELECT channel_id FROM excluded_channels")
    return [row[0] for row in cursor.fetchall()]

# دالة لتحديث أذونات القنوات
async def update_channel_permissions(guild, prisoner_role):
    excluded_channels = load_excluded_channels()  # تحميل القنوات المستثناة من قاعدة البيانات
    # تحديث أذونات القنوات النصية
    for channel in guild.text_channels:
        if channel.id not in excluded_channels:  # إذا لم تكن القناة مستثناة
            await channel.set_permissions(prisoner_role, overwrite=discord.PermissionOverwrite(view_channel=False))
        else:
            print(f"Text Channel {channel.name} is excluded from permission updates.")
    
    # إضافة دعم للرومات الصوتية
    for channel in guild.voice_channels:
        if channel.id not in excluded_channels:  # إذا لم تكن القناة الصوتية مستثناة
            await channel.set_permissions(prisoner_role, overwrite=discord.PermissionOverwrite(view_channel=False))
        else:
            print(f"Voice Channel {channel.name} is excluded from permission updates.")

# تفعيل صلاحيات البوت
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.guilds = True
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

# إعداد سجل الأخطاء
logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)  # تحديد البادئة "-"

# تخزين رتب الأعضاء المسجونين
prison_data = {}

async def update_channel_permissions(guild, prisoner_role):
    for channel in guild.channels:
        # Get the current permissions for the "Prisoner" role
        overwrite = channel.overwrites_for(prisoner_role)

        # Deny "View Channel" permission for the "Prisoner" role
        overwrite.view_channel = False

        # Apply the updated permissions
        await channel.set_permissions(prisoner_role, overwrite=overwrite)

MESSAGE_LIMIT = 5  # عدد الرسائل قبل اعتبارها سبام
TIME_LIMIT = 10  # الوقت (بالثواني) الذي يتم فيه احتساب عدد الرسائل
spam_records = defaultdict(list)  # لتتبع الرسائل لكل مستخدم

user_messages = defaultdict(list)

# الحدث عندما يصبح البوت جاهزًا
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # طباعة اسم البوت في التيرمينال عندما يصبح جاهزًا
    for guild in bot.guilds:
        # Check if the "Prisoner" role exists
        prisoner_role = discord.utils.get(guild.roles, name="Prisoner")
        if not prisoner_role:
            # Create "Prisoner" role if it doesn't exist
            prisoner_role = await guild.create_role(
                name="Prisoner",
                permissions=discord.Permissions.none(),  # No permissions for the "Prisoner"
                color=discord.Color.dark_gray()
            )
            print(f"Created 'Prisoner' role in {guild.name}.")
        
        # Update permissions for all channels to hide them for "Prisoner"
        await update_channel_permissions(guild, prisoner_role)

@bot.event
async def on_message(message):
    # تجاهل رسائل البوتات
    if message.author.bot:
        return

    # *** نظام التبنيد ***
    user_id = message.author.id
    now = asyncio.get_event_loop().time()

    # إضافة وقت الرسالة إلى سجل المستخدم
    spam_records[user_id].append(now)

    # تنظيف الرسائل القديمة التي تجاوزت الوقت المحدد
    spam_records[user_id] = [
        timestamp for timestamp in spam_records[user_id]
        if now - timestamp <= TIME_LIMIT
    ]

    # إذا تجاوز المستخدم الحد المسموح به من الرسائل
    if len(spam_records[user_id]) > MESSAGE_LIMIT:
        try:
            await message.guild.ban(message.author, reason="Detected spamming behavior")
            await message.channel.send(f"{message.author.mention} has been زوط for spamming.")
            print(f"User {message.author.name} banned for spamming.")
        except discord.Forbidden:
            print("لا أملك الصلاحيات لحظر المستخدم.")
            await message.channel.send("I do not have the permissions to ban this user.")
        except Exception as e:
            print(f"Error banning user: {e}")
        return  # إنهاء معالجة الرسالة بعد التبنيد

    # *** التحقق من الأوامر ***
    if message.content.startswith("-"):
        command_name = message.content.split(" ")[0][1:]  # استخراج اسم الأمر
        if not bot.get_command(command_name) and not any(command_name in cmd.aliases for cmd in bot.commands):
            return  # تجاهل الأوامر غير الموجودة

    # متابعة معالجة الأوامر الأخرى
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.message.reply("❌ | The mention is incorrect")
    else:
        await ctx.message.reply(f"❌ | An error occurred: {str(error)}")

@bot.command()
async def exclude(ctx):
    # التحقق إذا كان المستخدم لديه إذن الإدارة
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.message.reply("You do not have permission to exclude channels.")
        return
    
    channel_id = ctx.channel.id  # الحصول على معرف القناة التي تم إرسال الأمر فيها
    
    # إضافة القناة إلى قاعدة البيانات
    add_to_excluded(channel_id)
    
    # تأكيد للمستخدم
    await ctx.message.reply(f"Channel {ctx.channel.name} has been excluded from permission updates.")

# أمر لإزالة القناة من الاستثناءات
@bot.command()
async def include(ctx):
    # التحقق إذا كان المستخدم لديه إذن الإدارة
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.message.reply("You do not have permission to include channels back.")
        return
    
    channel_id = ctx.channel.id  # الحصول على معرف القناة التي تم إرسال الأمر فيها
    
    # إزالة القناة من قاعدة البيانات
    cursor.execute("DELETE FROM excluded_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    
    # تأكيد للمستخدم
    await ctx.message.reply(f"Channel {ctx.channel.name} has been included back in permission updates.")
    
# أمر سجن: -سجن @username reason
@commands.has_permissions(administrator=True)
@bot.command(aliases = ['كوي' , 'عدس' , 'ارمي' , 'اشخط' , 'احبس'])
async def سجن(ctx, member: discord.Member, duration: str = "8h"):
    guild = ctx.guild
    prisoner_role = discord.utils.get(guild.roles, name="Prisoner")

    if not prisoner_role:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
        return

    # Calculate jail time
    time_units = {"m": "minutes", "h": "hours", "d": "days"}
    unit = duration[-1]
    if unit not in time_units:
        await ctx.message.reply("Please specify a valid duration unit (m for minutes, h for hours, d for days).")
        return

    try:
        time_value = int(duration[:-1])
    except ValueError as e:
        await ctx.message.reply("Invalid jail duration. Example: 1h, 30m. Error: {e}")
        return

    delta = timedelta(**{time_units[unit]: time_value})
    release_time = datetime.utcnow() + delta

    # Save the member's current roles
    previous_roles = [role for role in member.roles if role != guild.default_role]
    await member.edit(roles=[prisoner_role])

    # Store jail data
    prison_data[member.id] = {"roles": previous_roles, "release_time": release_time}

    await ctx.message.reply(f"{member.mention} has been jailed for {duration}.")
    
    # Automatic release after the specified time
    await asyncio.sleep(delta.total_seconds())
    await release_member(ctx, member)

# Pardon command
@bot.command(aliases = ['اعفاء' , 'اخراج', 'مسامحة' , 'سامح' , 'اخرج' , 'اطلع'])
@commands.has_permissions(administrator=True)
async def عفو(ctx, member: discord.Member):
    await release_member(ctx, member)

# Function to release a member
async def release_member(ctx, member):
    if member.id not in prison_data:
        await ctx.message.reply(f"{member.mention} is not in jail.")
        return

    guild = ctx.guild
    prisoner_role = discord.utils.get(guild.roles, name="Prisoner")
    if prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    previous_roles = prison_data[member.id]["roles"]
    await member.edit(roles=previous_roles)
    del prison_data[member.id]

    await ctx.message.reply(f"{member.mention} has been released from jail.")


bot.run(os.environ['B'])
