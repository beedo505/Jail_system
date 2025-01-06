import discord
from discord.ext import commands
import logging
import asyncio
import re
import json
import os
from collections import defaultdict
import time
from datetime import timedelta, datetime
TOKEN = os.getenv('B')

def load_exceptions():
    if os.path.exists('channel_exceptions.json'):
        with open('channel_exceptions.json', 'r') as f:
            return json.load(f)
    return {}

def save_exceptions(data):
    with open('channel_exceptions.json', 'w') as f:
        json.dump(data, f, indent=4)

# تفعيل صلاحيات البوت
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.guilds = True
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

# إعداد سجل الأخطاء
logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)  # تحديد البادئة "-"
exceptions_data = load_exceptions()

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
@commands.has_permissions(administrator=true)
async def add_exp(ctx, channel_id: str = None):
    """Add channel to exceptions using ID or current channel"""
    try:
        # If no ID provided, use current channel
        if channel_id is None:
            channel = ctx.channel
        else:
            # Try to get channel by ID
            channel = await bot.fetch_channel(int(channel_id))
            if channel.guild.id != ctx.guild.id:
                await ctx.message.reply("This channel doesn't belong to this server! ⚠️")
                return
    except (ValueError, discord.NotFound):
        await ctx.message.reply("Invalid channel ID! ⚠️")
        return
    except discord.Forbidden:
        await ctx.message.reply("I don't have access to that channel! ⚠️")
        return

    if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
        await ctx.message.reply("Please provide a valid text or voice channel! ⚠️")
        return

    guild_id = str(ctx.guild.id)
    if guild_id not in exceptions_data:
        exceptions_data[guild_id] = []

    if str(channel.id) not in exceptions_data[guild_id]:
        exceptions_data[guild_id].append(str(channel.id))
        save_exceptions(exceptions_data)

        prisoner_role = discord.utils.get(ctx.guild.roles, name="Prisoner")
        if prisoner_role:
            if isinstance(channel, discord.VoiceChannel):
                await channel.set_permissions(prisoner_role, view_channel=True, connect=True)
            else:
                await channel.set_permissions(prisoner_role, view_channel=True)

        channel_type = "voice" if isinstance(channel, discord.VoiceChannel) else "text"
        await ctx.message.reply(f"{channel.mention} ({channel_type} channel) has been added to exceptions! ✅")
    else:
        await ctx.message.reply("This channel is already in exceptions! ⚠️")

@bot.command()
@commands.has_permissions(administrator=true)
async def remove_exp(ctx, channel_id: str = None):
    """Remove channel from exceptions using ID or current channel"""
    try:
        # If no ID provided, use current channel
        if channel_id is None:
            channel = ctx.channel
        else:
            # Try to get channel by ID
            channel = await bot.fetch_channel(int(channel_id))
            if channel.guild.id != ctx.guild.id:
                await ctx.message.reply("This channel doesn't belong to this server! ⚠️")
                return
    except (ValueError, discord.NotFound):
        await ctx.message.reply("Invalid channel ID! ⚠️")
        return
    except discord.Forbidden:
        await ctx.message.reply("I don't have access to that channel! ⚠️")
        return

    guild_id = str(ctx.guild.id)
    if guild_id in exceptions_data and str(channel.id) in exceptions_data[guild_id]:
        exceptions_data[guild_id].remove(str(channel.id))
        save_exceptions(exceptions_data)

        prisoner_role = discord.utils.get(ctx.guild.roles, name="Prisoner")
        if prisoner_role:
            if isinstance(channel, discord.VoiceChannel):
                await channel.set_permissions(prisoner_role, view_channel=False, connect=False)
            else:
                await channel.set_permissions(prisoner_role, view_channel=False)

        channel_type = "voice" if isinstance(channel, discord.VoiceChannel) else "text"
        await ctx.message.reply(f"{channel.mention} ({channel_type} channel) has been removed from exceptions! ✅")
    else:
        await ctx.message.reply("This channel is not in exceptions! ⚠️")

@bot.command()
async def list_exceptions(ctx):
    """Display list of excepted channels"""
    guild_id = str(ctx.guild.id)

    if guild_id in exceptions_data and exceptions_data[guild_id]:
        text_channels = []
        voice_channels = []

        for ch_id in exceptions_data[guild_id]:
            channel = ctx.guild.get_channel(int(ch_id))
            if channel:
                if isinstance(channel, discord.VoiceChannel):
                    voice_channels.append(f"{channel.mention} (Voice) `ID: {channel.id}`")
                else:
                    text_channels.append(f"{channel.mention} (Text) `ID: {channel.id}`")

        response = "📋 **Excepted Channels:**"
        if text_channels:
            response += ""

**Text Channels:**
" + "
".join(text_channels)
        if voice_channels:
            response += "

**Voice Channels:**
" + "
".join(voice_channels)

        await ctx.send(response)
    else:
        await ctx.send("No channels are excepted! ℹ️")

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
