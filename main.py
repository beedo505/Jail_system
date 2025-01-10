import discord
from discord.ext import commands
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import pymongo
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
print(discord.__version__)

uri = "mongodb+srv://banmark100:N7CPbKeIqniC9qUk@cluster0.zriaf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(uri, server_api=ServerApi('1'))
    # db = client["Prison_bot"]
    # collection = db["jailed_users"]

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    

DATA_FILE = "exceptions.json"
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
data_manager = ExceptionManager("/app/data/exceptions.json")
data_manager.load()
data_manager.data["example_channel"] = {"permissions"}
        
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

SPAM_THRESHOLD = 5  # عدد الرسائل المسموح بها
SPAM_TIME_FRAME = 10  # إطار زمني بالثواني
TIMEOUT_DURATION_MINUTES = 30  # None تعني تايم أوت دائم

user_messages = defaultdict(list)


# الحدث عندما يصبح البوت جاهزًا
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # طباعة اسم البوت في التيرمينال عندما يصبح جاهزًا
    print(f'Bot is connected to the following servers:')
    for guild in bot.guilds:
        print(f'{guild.name} (ID: {guild.id})')
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

    # Log user messages
    user_id = message.author.id
    current_time = message.created_at.timestamp()
    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id].append(current_time)

    # Remove messages outside the time frame
    user_messages[user_id] = [
        msg_time for msg_time in user_messages[user_id] 
        if current_time - msg_time <= SPAM_TIME_FRAME
    ]

    # Check for spam
    if len(user_messages[user_id]) == SPAM_THRESHOLD:
        try:
            # تأكد من أن TIMEOUT_DURATION_MINUTES محددة
            if TIMEOUT_DURATION_MINUTES is None:
                raise ValueError("TIMEOUT_DURATION_MINUTES is not defined")

            # تحويل الدقائق إلى ثواني
            timeout_duration_seconds = TIMEOUT_DURATION_MINUTES * 60

            # Apply timeout (استخدم `until` بدلاً من `duration`)
            timeout_until = message.created_at + timedelta(seconds=timeout_duration_seconds)
            await message.author.timeout(timeout_until, reason="Spam detected")
            await message.channel.send(f"🚫 {message.author.mention} has been timed out for spamming")
            # Clear the user's message log after punishment
            user_messages[user_id] = []
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to timeout this user")
        except ValueError as ve:
            print(f"Error: {ve}")
            await message.channel.send(f"❌ Error: {ve}")
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send("❌ An unexpected error occurred")

    # *** التحقق من الأوامر ***
    if message.content.startswith("-"):
        command_name = message.content.split(" ")[0][1:]  # استخراج اسم الأمر
        if not bot.get_command(command_name) and not any(command_name in cmd.aliases for cmd in bot.commands):
            return  # تجاهل الأوامر غير الموجودة

    # متابعة معالجة الأوامر الأخرى
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    print(f"Error: {error}")
    if isinstance(error, commands.BadArgument):
        await ctx.message.reply("❌ | The mention is incorrect. Please mention a valid member")
        return
    elif isinstance(error, commands.MemberNotFound):
        await ctx.message.reply("❌ | The mentioned member is not in the server")
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.message.reply("❌ | You do not have the required permissions to use this command")
        return
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.message.reply(f"❌ | An error occurred: {error.original}")
        return
    elif isinstance(error, commands.CommandNotFound):
        await ctx.message.reply("❌ | This command does not exist")
        return
        
    """else:
        await ctx.message.reply(f"❌ | An error occurred: {str(error)}")"""



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
        await ctx.message.send(f"❌ Error: {str(e)}")

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


# Ban command
@bot.command(aliases = ['افتح', 'اغرق', 'برا', 'افتحك', 'اشخطك', 'انهي'])
@commands.has_permissions(ban_members=True)
async def زوطلي(ctx, user: discord.User = None, *, reason = "No reason"):

    if user is None:
        embed = discord.Embed(title="📝 أمر البان", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -زوطلي \n",
            "•  الوظيفة        :  باند للعضو \n",
            "•  الاستخدام    :  -زوطلي [@شخص]",
        ]

        aliases_lines = [
            "•  -افتح \n",
            "•  -اغرق \n",
            "•  -برا \n",
            "•  -افتحك \n",
            "•  -اشخطك \n",
            "•  -انهي \n",
        ]

        embed.add_field(
            name="📌 معلومات الأمر",
            value=f"{''.join(usage_lines)}",
            inline=False
        )

        embed.add_field(
            name="💡 الاختصارات المتاحة",
            value=f"{''.join(aliases_lines)}",
            inline=False
        )

        await ctx.message.reply(embed=embed)
        return

    if user == ctx.author:
        await ctx.message.reply("You cannot ban yourself")
        return

    # if user.top_role >= ctx.guild.me.top_role:
    #     await ctx.message.reply("❌ | I cannot jail this member because their role is equal to or higher than mine.")
    #     return

    try:
        # تحقق من أن المستخدم قد أدخل منشن أو ID
        if user:
            user_id = user.id  # مباشرة استخدم ID من الكائن user

        # محاولة الحصول على المستخدم من السيرفر
        member = ctx.guild.get_member(user_id)

        # if member.top_role >= ctx.guild.me.top_role:
        #     await ctx.message.reply("❌ | I cannot ban this member because their role is equal to or higher than mine.")
        #     return

        if member:
            await member.ban(reason=reason)
            await ctx.message.reply(f"{member.mention} has been banned. Reason: {reason}")
        else:
            # إذا كان العضو غير موجود في السيرفر
            await ctx.message.reply(f"User with ID `{user_id}` is not in the server, so the ban cannot be applied.")

    except discord.HTTPException as e:
        # إذا حدث خطأ في واجهة Discord API
        await ctx.message.reply(f"An error occurred while trying to ban the user: {e}")


# Unban command
@bot.command(aliases=['unban', 'un'])
@commands.has_permissions(ban_members=True)
async def فك(ctx, *, user_input=None):
    if user_input is None:
        await ctx.message.reply("Please mention the user or their ID to unban.")
        return

    if user_input == ctx.author:
        await ctx.message.reply("You cannot unban yourself")
        return

    try:
        # تحقق إذا كان المدخل هو منشن أو ID
        if user_input.startswith("<@") and user_input.endswith(">"):
            user_id = int(user_input[2:-1].replace("!", ""))  # استخراج ID من المنشن
        else:
            user_id = int(user_input)  # استخدام ID مباشرةً

        # محاولة الحصول على قائمة الباندات باستخدام async for
        async for ban_entry in ctx.guild.bans():
            if ban_entry.user.id == user_id:
                # إذا كان العضو محظورًا
                await ctx.guild.unban(ban_entry.user)  # إلغاء الحظر باستخدام كائن user من BanEntry
                await ctx.message.reply(f"User with ID `{user_id}` has been unbanned.")
                return

        # إذا لم يكن العضو متبندًا
        await ctx.message.reply(f"User with ID `{user_id}` is not banned.")

    except ValueError:
        # إذا لم يكن المدخل صالحًا (ليس ID أو منشن صحيح)
        await ctx.message.reply("Invalid input. Please mention a user (`@username`) or their ID.")
    except discord.HTTPException as e:
        # إذا حدث خطأ آخر في واجهة Discord API
        await ctx.message.reply(f"An error occurred while trying to unban the user: {e}")
        
# امر السجن
@commands.has_permissions(administrator=True)
@bot.command(aliases = ['كوي' , 'عدس' , 'ارمي' , 'اشخط' , 'احبس' , 'حبس'])
async def سجن(ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
    guild = ctx.guild
    prisoner_role = discord.utils.get(guild.roles, name="Prisoner")

    if not prisoner_role:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
        return

    if duration is None or not any(unit in duration for unit in ["m", "h", "d"]):
        if reason and not duration:
            duration = "8h"  # Set default duration
        else:
            duration = "8h"  # Default duration if no duration and reason is missing

    if member is None:
        embed = discord.Embed(title="📝 أمر السجن", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -سجن \n",
            "•  الوصف       :  سجن شخص معين \n",
            "•  الاستخدام    :  -سجن [@شخص]",
        ]

        aliases_lines = [
            "•  -سجن \n",
            "•  -حبس \n",
            "•  -احبس \n",
            "•  -اشخط \n",
            "•  -ارمي \n",
            "•  -عدس \n",
            "•  -كوي \n",
        ]

        embed.add_field(
            name="📌 معلومات الأمر",
            value=f"{''.join(usage_lines)}",
            inline=False
        )

        embed.add_field(
            name="💡 الاختصارات المتاحة",
            value=f"{''.join(aliases_lines)}",
            inline=False
        )

        await ctx.message.reply(embed=embed)
        return

    if member == ctx.author:
        await ctx.message.reply("You cannot jail yourself.")
        return

    if member not in ctx.guild.members:
        await ctx.message.reply("This member is not in the server.")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.message.reply("I cannot jail this member because their role is equal to or higher than mine.")
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
        await ctx.message.reply(f"Invalid jail duration. Example: 1h, 30m. Error: {e}")
        return

    delta = timedelta(**{time_units[unit]: time_value})
    release_time = datetime.utcnow() + delta

    # Save member's roles and jail them
    previous_roles = [role.id for role in member.roles if role != guild.default_role]
    await member.edit(roles=[prisoner_role])

    # Save roles to MongoDB
    collection.update_one(
        {"user_id": member.id, "guild_id": ctx.guild.id},
        {"$set": {"roles": previous_roles, "release_time": release_time, "reason": reason}},
        upsert=True
    )

    await ctx.message.reply(f"{member.mention} has been jailed for {duration}. Reason: {reason}")

    # Automatic release
    await asyncio.sleep(delta.total_seconds())
    await release_member(ctx, member)

# امر العفو
@bot.command(aliases = ['اعفاء' , 'اخراج', 'طلع' , 'سامح' , 'اخرج' , 'اطلع' , 'اعفي'])
@commands.has_permissions(administrator=True)
async def عفو(ctx, member: discord.Member = None):

    if member is None:
        embed = discord.Embed(title="📝 أمر العفو", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -عفو \n",
            "•  الوصف       :  للعفو عن شخص مسجون \n",
            "•  الاستخدام    :  -عفو [@شخص]",
        ]

        aliases_lines = [
            "•  -عفو \n",
            "•  -اعفي \n",
            "•  -اطلع \n",
            "•  -اخرج \n",
            "•  -سامح \n",
            "•  -طلع \n",
            "•  -اخراج \n",
            "•  -اعفاء \n",
        ]

        embed.add_field(
            name="📌 معلومات الأمر",
            value=f"{''.join(usage_lines)}",
            inline=False
        )

        embed.add_field(
            name="💡 الاختصارات المتاحة",
            value=f"{''.join(aliases_lines)}",
            inline=False
        )

        await ctx.message.reply(embed=embed)
        return

    if member == ctx.author:
        await ctx.message.reply("You cannot jail yourself.")
        return

    if member not in ctx.guild.members:
        await ctx.message.reply("This member is not in the server.")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.message.reply("I cannot jail this member because their role is equal to or higher than mine.")
        return

    await release_member(ctx, member)

# Function to release a member from jail
async def release_member(ctx, member):
    guild = ctx.guild
    prisoner_role = discord.utils.get(guild.roles, name="Prisoner")
    
    # Fetch member data from MongoDB
    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})
    if not data:
        await ctx.message.reply(f"{member.mention} is not in jail.")
        return

    # Remove the "Prisoner" role if they have it
    if prisoner_role and prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    # Restore the member's previous roles
    previous_roles = [guild.get_role(role_id) for role_id in data.get("roles", []) if guild.get_role(role_id)]
    if previous_roles:
        await member.edit(roles=previous_roles)
    else:
        await member.edit(roles=[guild.default_role])  # Assign default role if no previous roles exist

    # Remove the member's jail data from the database
    collection.delete_one({"user_id": member.id, "guild_id": guild.id})

    await ctx.message.reply(f"{member.mention} has been pardoned")


bot.run(os.environ['B'])
