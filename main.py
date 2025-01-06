import discord
from discord.ext import commands
import logging
import asyncio
import re
from typing import Union
import json
import os
from collections import defaultdict
import time
from datetime import timedelta, datetime
TOKEN = os.getenv('B')

global exceptions_data
exceptions_data = {}

EXCEPTIONS_FILE = 'exceptions.json'

class ExceptionManager:
    def __init__(self, file_path=None):
        if file_path is None:
            self.file_path = os.path.join(os.path.dirname(__file__), 'exceptions.json')
        else:
            self.file_path = file_path
        print(f"📂 Using file path: {self.file_path}")
        self.data = self.load()

    def load(self):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"❌ Error loading data: {e}")
            return {}

    def save(self):
        try:
            print(f"💾 Attempting to save data: {self.data}")
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            print(f"✅ Saved data successfully: {self.data}")
            return True
        except Exception as e:
            print(f"❌ Error in save(): {e}")
            return False
    

    def add_channel(self, guild_id: str, channel_id: str):
        if guild_id not in self.data:
            self.data[guild_id] = []
        if channel_id not in self.data[guild_id]:
            self.data[guild_id].append(channel_id)
            self.save()
            return True
        return False

    def remove_channel(self, guild_id: str, channel_id: str):
        if guild_id in self.data and channel_id in self.data[guild_id]:
            self.data[guild_id].remove(channel_id)
            if not self.data[guild_id]:
                del self.data[guild_id]
            self.save()
            return True
        return False
        

    def get_exceptions(self, guild_id: str):
        return self.data.get(guild_id, [])

exception_manager = ExceptionManager()
        
# تفعيل صلاحيات البوت المطلوبة
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.guilds = True
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

# إعداد سجل الأخطاء
logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)  # تحديد البادئة '-'

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
    print(f"✅ Bot is ready! Logged in as {bot.user.name}")
    print(f"✅ Current exceptions: {exception_manager.data}")
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

    # إذا تجاوز المستخدم الحد المسموح به من الرسائل يلقم زوط
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
@commands.has_permissions(administrator=True)
async def add_exp(ctx, channel_id: str = None):
    try:
        if channel_id is None:
            channel = ctx.channel
        else:
            channel_id = channel_id.replace('<#', '').replace('>', '')
            channel = bot.get_channel(int(channel_id))
            if not channel:
                raise ValueError("Channel not found!")

        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)

        if exception_manager.add_channel(guild_id, channel_id):
            channel_type = "Voice" if isinstance(channel, discord.VoiceChannel) else "Text"
            await ctx.message.reply(f"✅ {channel_type} channel {channel.mention} (`{channel_id}`) added to exceptions!")
        else:
            await ctx.message.reply(f"❌ Channel {channel.mention} is already excepted!")

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_exp(ctx, channel_id: str = None):
    try:
        if channel_id is None:
            channel = ctx.channel
        else:
            channel_id = channel_id.replace('<#', '').replace('>', '')
            channel = bot.get_channel(int(channel_id))
            if not channel:
                raise ValueError("Channel not found!")

        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)

        if exception_manager.remove_channel(guild_id, channel_id):
            channel_type = "Voice" if isinstance(channel, discord.VoiceChannel) else "Text"
            await ctx.message.reply(f"✅ {channel_type} channel {channel.mention} (`{channel_id}`) removed from exceptions!")
        else:
            await ctx.message.reply(f"❌ Channel {channel.mention} is not in exceptions list!")

    except Exception as e:
        await ctx.message.reply(f"❌ Error: {str(e)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def list_exp(ctx):
    guild_id = str(ctx.guild.id)
    exceptions = exception_manager.data.get(guild_id, [])

    if exceptions:
        text_channels = []
        voice_channels = []
        
        print(f"🔍 Found exceptions for guild {guild_id}: {exceptions}")

        for ch_id in exceptions:
            try:
                channel = bot.get_channel(int(ch_id))
                if channel:
                    if isinstance(channel, discord.VoiceChannel):
                        voice_channels.append(f"{channel.mention} (Voice)")
                    else:
                        text_channels.append(f"{channel.mention} (Text)")
            except Exception as e:
                print(f"Error processing channel {ch_id}: {e}")

        if text_channels or voice_channels:
            embed = discord.Embed(title="📋 Excepted Channels", color=0x2f3136)
            
            if text_channels:
                embed.add_field(name="Text Channels", value="".join(text_channels), inline=False)
            if voice_channels:
                embed.add_field(name="Voice Channels", value="".join(voice_channels), inline=False)

            await ctx.message.reply(embed=embed)
        else:
            await ctx.message.reply("❌ No valid channels found in exceptions list.")
    else:
        await ctx.message.reply("ℹ️ No channels are excepted!")

# امر السجن
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

# امر العفو
@bot.command(aliases = ['اعفاء' , 'اخراج', 'مسامحة' , 'سامح' , 'اخرج' , 'اطلع'])
@commands.has_permissions(administrator=True)
async def عفو(ctx, member: discord.Member):
    await release_member(ctx, member)

# Function to release a member from jail
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
