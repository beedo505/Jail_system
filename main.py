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

# الاتصال بقاعدة البيانات (ستنشأ إذا لم تكن موجودة حنكة وكذا)
conn = sqlite3.connect('excluded_channels.db')
cursor = conn.cursor()

# إنشاء جدول لتخزين القنوات المستثناه
cursor.execute('''
CREATE TABLE IF NOT EXISTS excluded_channels (
    channel_id INTEGER PRIMARY KEY,
    can_view BOOLEAN,
    can_send_messages BOOLEAN,
    can_connect BOOLEAN,
    can_speak BOOLEAN
);
''')
conn.commit()

# دالة لإضافة قناة إلى الاستثناءات
def add_to_excluded(channel_id: int, can_view: bool, can_send_messages: bool, can_connect: bool, can_speak: bool):
    cursor.execute('''
    INSERT OR REPLACE INTO excluded_channels 
    (channel_id, can_view, can_send_messages, can_connect, can_speak) 
    VALUES (?, ?, ?, ?, ?)
    ''', (channel_id, can_view, can_send_messages, can_connect, can_speak))
    conn.commit()

    # إذا كانت القناة مستثناة، نقوم بإضافة القيم
    if is_excluded:
        cursor.execute('''INSERT OR REPLACE INTO excluded_channels_new 
                          (channel_id, can_view, can_send_messages, can_connect, can_speak)
                          VALUES (?, ?, ?, ?, ?)''', 
                       (channel_id, can_view, can_send_messages, can_connect, can_speak))
    else:
        cursor.execute('''DELETE FROM excluded_channels_new WHERE channel_id = ?''', (channel_id,))

    # تحديث قاعدة البيانات
    cursor.execute('''PRAGMA foreign_keys=on;''')  # إعادة تمكين قيود المفتاح الخارجي
    conn.commit()

    # الآن يمكن استخدام جدول excluded_channels الجديد مع الأعمدة المضافة
    # إذا تم تحديث قاعدة البيانات بنجاح
    cursor.execute('''DROP TABLE IF EXISTS excluded_channels;''')
    cursor.execute('''ALTER TABLE excluded_channels_new RENAME TO excluded_channels;''')
    conn.commit()

def remove_from_excluded(channel_id: int):
    cursor.execute("DELETE FROM excluded_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()

def load_excluded_channels():
    # تحميل القنوات المستثناة من قاعدة البيانات
    cursor.execute("SELECT channel_id FROM excluded_channels WHERE is_excluded = 1")
    return cursor.fetchall()

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

MESSAGE_LIMIT = 5  # عدد الرسائل قبل اعتبارها سبام
TIME_LIMIT = 10  # الوقت (بالثواني) الذي يتم فيه احتساب عدد الرسائل
spam_records = defaultdict(list)  # لتتبع الرسائل لكل مستخدم

user_messages = defaultdict(list)

# الحدث عندما يصبح البوت جاهزًا
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # طباعة اسم البوت في التيرمينال عندما يصبح جاهزًا
    
    for guild in bot.guilds:
        prisoner_role = discord.utils.get(guild.roles, name="Prisoner")
        if not prisoner_role:
            prisoner_role = await guild.create_role(
                name="Prisoner",
                permissions=discord.Permissions.none(),
                color=discord.Color.dark_gray()
            )
            print(f"Created 'Prisoner' role in {guild.name}.")
        
        # استرجاع القنوات المستثناة والأذونات الخاصة بها
        cursor.execute("SELECT channel_id, can_view, can_send_messages, can_connect, can_speak FROM excluded_channels")
        excluded_channels = cursor.fetchall()

        for channel_id, can_view, can_send_messages, can_connect, can_speak in excluded_channels:
            channel = guild.get_channel(channel_id)
            if channel:
                if isinstance(channel, discord.VoiceChannel):
                    await channel.set_permissions(prisoner_role, connect=can_connect, speak=can_speak, view_channel=can_view)
                elif isinstance(channel, discord.TextChannel):
                    await channel.set_permissions(prisoner_role, send_messages=can_send_messages, view_channel=can_view)

    print("Permissions updated successfully.")

async def update_channel_permissions(guild, prisoner_role):
    # إخفاء جميع القنوات عن "Prisoner" بشكل افتراضي
    for channel in guild.channels:
        if isinstance(channel, discord.VoiceChannel):
            # إخفاء قنوات الصوتية
            await channel.set_permissions(prisoner_role, connect=False, speak=False, view_channel=False)
        elif isinstance(channel, discord.TextChannel):
            # إخفاء القنوات النصية
            await channel.set_permissions(prisoner_role, send_messages=False, view_channel=False)


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
async def exclude(ctx, channel_id: int = None):
    if channel_id is None:
        channel_id = ctx.channel.id  # إذا لم يتم تحديد المعرف، نستخدم القناة التي أرسل منها الأمر
    
    channel = ctx.guild.get_channel(channel_id)
    if not channel:
        await ctx.message.reply("Channel not found!")
        return
    
    # الحصول على الأذونات الحالية للقناة
    can_view = channel.permissions_for(ctx.guild.get_member(ctx.author.id)).view_channel
    can_send_messages = channel.permissions_for(ctx.guild.get_member(ctx.author.id)).send_messages
    can_connect = False
    can_speak = False

    if isinstance(channel, discord.VoiceChannel):
        can_connect = channel.permissions_for(ctx.guild.get_member(ctx.author.id)).connect
        can_speak = channel.permissions_for(ctx.guild.get_member(ctx.author.id)).speak
    
    # تخزين الأذونات في قاعدة البيانات
    add_to_excluded(channel_id, can_view, can_send_messages, can_connect, can_speak)
    
    # تحديث الأذونات للقناة بإخفائها عن "Prisoner"
    prisoner_role = discord.utils.get(ctx.guild.roles, name="Prisoner")
    if prisoner_role:
        if isinstance(channel, discord.VoiceChannel):
            await channel.set_permissions(prisoner_role, connect=False, speak=False, view_channel=False)
        elif isinstance(channel, discord.TextChannel):
            await channel.set_permissions(prisoner_role, send_messages=False, view_channel=False)

    await ctx.message.reply(f"Channel {channel.name} has been excluded and hidden from 'Prisoner'.")

# أمر لإزالة القناة من الاستثناءات
@bot.command()
async def include(ctx, channel_id: int = None):
    if channel_id is None:
        channel_id = ctx.channel.id  # استخدام القناة الحالية إذا لم يتم تحديدها
    
    # التحقق إذا كانت القناة مستثناة
    cursor.execute("SELECT * FROM excluded_channels WHERE channel_id = ?", (channel_id,))
    existing_channel = cursor.fetchone()
    
    if not existing_channel:
        await ctx.message.reply(f"Channel {ctx.guild.get_channel(channel_id).name} is not excluded.")
        return

    # إزالة القناة من قاعدة البيانات
    cursor.execute("DELETE FROM excluded_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()

    # استرجاع الأذونات للقناة بعد إزالتها من الاستثناء
    prisoner_role = discord.utils.get(ctx.guild.roles, name="Prisoner")
    if prisoner_role:
        channel = ctx.guild.get_channel(channel_id)
        if isinstance(channel, discord.VoiceChannel):
            await channel.set_permissions(prisoner_role, connect=False, speak=False, view_channel=False)
        elif isinstance(channel, discord.TextChannel):
            await channel.set_permissions(prisoner_role, send_messages=False, view_channel=False)
    
    await ctx.message.reply(f"Channel {ctx.guild.get_channel(channel_id).name} has been included back to the normal permissions.")
    
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
