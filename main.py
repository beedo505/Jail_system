import discord
from discord.ext import commands
from discord.ui import Button, View
from pymongo import MongoClient
import pymongo
import logging
import asyncio
import dns.resolver
import re
import requests
from typing import Union
import json
import os
from collections import defaultdict
import time
from datetime import datetime, timedelta, timezone
TOKEN = os.getenv('B')

# print(discord.__version__)
# def get_current_ip():
#     response = requests.get('https://api.ipify.org')
#     return response.text
# print(get_current_ip())

uri = "mongodb+srv://Bedo:L36dXXAVTYyDgvL6@cluster0.zriaf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(uri, tlsAllowInvalidCertificates=True)
db = client["Prison"]
collection = db["user"]
exceptions_collection = db['exceptions']
guilds_collection = db["guilds"]
words_collection = db['banned_words']

try:
    client.admin.command('ping')
    print("You successfully connected to MongoDB!")
except Exception as e:
    print(e)


class ExceptionManager:
    def __init__(self, db):
        self.db = db
        self.collection = self.db["guilds"]

    def get_exceptions(self, guild_id):
        server_data = self.collection.find_one({"guild_id": guild_id})
        return server_data.get("exception_channels", []) if server_data else []

    def add_exception(self, guild_id, channel_id):
        exceptions = self.get_exceptions(guild_id)
        if channel_id in exceptions:  # ✅ التحقق قبل الإضافة
            return False  # القناة موجودة بالفعل
        
        exceptions.append(channel_id)
        self.collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"exception_channels": exceptions}},
            upsert=True
        )
        return True  # تم إضافة القناة

    def remove_exception(self, guild_id, channel_id):
        exceptions = self.get_exceptions(guild_id)
        if channel_id not in exceptions:
            return False  # القناة غير موجودة في القائمة

        exceptions.remove(channel_id)
        self.collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"exception_channels": exceptions}}
        )
        return True  # تم حذف القناة

    def is_exception(self, guild_id, channel_id):
        return channel_id in self.get_exceptions(guild_id)



exception_manager = ExceptionManager(db)
        
# تفعيل صلاحيات البوت المطلوبة
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.guilds = True
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)

# تخزين رتب الأعضاء المسجونين
prison_data = {}

SPAM_THRESHOLD = 5  # عدد الرسائل المسموح بها
SPAM_TIME_FRAME = 10  # إطار زمني بالثواني
TIMEOUT_DURATION_MINUTES = 10  # None تعني تايم أوت دائم

user_messages = defaultdict(list)

@bot.event
async def on_ready():
    print(f"✅ Bot is ready! Logged in as {bot.user.name}")
    exception_manager = ExceptionManager(db)

    for guild in bot.guilds:
        guild_id = str(guild.id)

        # التحقق مما إذا كان السيرفر موجودًا في قاعدة البيانات، وإضافته إن لم يكن موجودًا
        server_data = guilds_collection.find_one({"guild_id": guild_id})
        if not server_data:
            guilds_collection.insert_one({"guild_id": guild_id, "exception_channels": [], "prisoner_role_id": None})
            print(f"Initialized database entry for guild {guild.name} (ID: {guild.id}).")
            continue  # لا يوجد رتبة محددة، ننتقل إلى السيرفر التالي

        # الحصول على ID الرتبة التي حددها المستخدم
        prisoner_role_id = server_data.get("prisoner_role_id")
        if not prisoner_role_id:
            print(f"No prisoner role set for {guild.name}. Skipping role permissions setup.")
            continue  # لا يوجد رتبة محددة، ننتقل إلى السيرفر التالي

        # الحصول على كائن الرتبة من ID المحفوظ
        prisoner_role = guild.get_role(int(prisoner_role_id))
        if not prisoner_role:
            print(f"Saved prisoner role ID is invalid or deleted in {guild.name}. Skipping role permissions setup.")
            continue  # الرتبة غير موجودة، ننتقل إلى السيرفر التالي

        # استرجاع القنوات المستثناة من قاعدة البيانات
        exception_channels = exception_manager.get_exceptions(guild_id)

        # تحديث صلاحيات القنوات بناءً على الاستثناءات
        for channel in guild.channels:
            if str(channel.id) in exception_channels:
                if isinstance(channel, discord.TextChannel):
                    await channel.set_permissions(prisoner_role, view_channel=True, read_messages=True, send_messages=True)
                    print(f"Restored exception permissions for text channel: {channel.name} in {guild.name}.")
                elif isinstance(channel, discord.VoiceChannel):
                    await channel.set_permissions(prisoner_role, view_channel=True, connect=True, speak=True)
                    print(f"Restored exception permissions for voice channel: {channel.name} in {guild.name}.")
            else:
                await channel.set_permissions(prisoner_role, view_channel=False, read_messages=False, send_messages=False, connect=False, speak=False)
                print(f"Applied restricted permissions for channel: {channel.name} in {guild.name}.")

    print("✅ All exceptions have been restored successfully!")

data = guilds_collection.find_one({"guild_id": 1049390476479963138})
print(data)

# on message
@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    # جلب الكلمات المحظورة من قاعدة البيانات
    banned_words = [word['word'] for word in words_collection.find()]

    # تحقق إذا كانت الرسالة تحتوي على كلمة محظورة
    for word in banned_words:
        if word in message.content.lower():
            try:
                # حظر العضو
                await message.author.ban(reason=f"Used a banned word: {word}")
                await message.channel.send(f"❌ {message.author.mention} has been banned for using a banned word: {word}.")
                break  # إيقاف عملية الفحص بعد الحظر
            except discord.Forbidden:
                await message.channel.send(f"❌ I do not have permission to ban {message.author.mention}.")
            except discord.HTTPException as e:
                await message.channel.send(f"❌ Error occurred while banning {message.author.mention}: {e}")
            break  # إيقاف التحقق بعد الحظر
            
    # تأكد من إرسال الرسائل التي لا تحتوي على كلمات محظورة
    # await bot.process_commands(message)


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
            if TIMEOUT_DURATION_MINUTES is None:
                raise ValueError("TIMEOUT_DURATION_MINUTES is not defined")

            # Convert min to sec
            timeout_duration_seconds = TIMEOUT_DURATION_MINUTES * 60

            timeout_until = message.created_at + timedelta(seconds=timeout_duration_seconds)
            await message.author.timeout(timeout_until, reason="Spam detected")
            await message.channel.send(f"🚫 {message.author.mention} has been timed out for spamming")
            # Clear the user's message log after punishment
            user_messages[user_id] = []
        except discord.Forbidden:
            await message.channel.send(f"❌ I don't have permission to timeout {message.author.mention}")
        except ValueError as ve:
            print(f"Error: {ve}")
            await message.channel.send(f"❌ Error: {ve}")
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send("❌ An unexpected error occurred")

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
async def set(ctx, role: discord.Role = None):
    guild_id = str(ctx.guild.id)

    if role is None:
        await ctx.message.reply("You must mention a role!")
        return

    if not role:
        await ctx.message.reply("❌ You must mention a role or provide a valid role ID.")
        return

    # استرجاع الرتبة المخزنة من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": guild_id})
    current_role_id = server_data.get("prisoner_role_id") if server_data else None

    # إذا كانت نفس الرتبة المخزنة، لا داعي للحفظ مرة أخرى
    if current_role_id == str(role.id):
        await ctx.message.reply(f"⚠️ The prisoner role is already set to: **{role.name}**.")
        return

    # حفظ الرتبة الجديدة في قاعدة البيانات
    guilds_collection.update_one(
        {"guild_id": guild_id},
        {"$set": {"prisoner_role_id": str(role.id)}},
        upsert=True
    )

    await ctx.message.reply(f"✅ The prisoner role has been set to: **{role.name}**.")

# Add command
# Add channel to exceptions
@bot.command()
@commands.has_permissions(administrator=True)
async def add(ctx, *, channel=None):
    guild_id = str(ctx.guild.id)
    channel_to_add = None

    # Retrieve prisoner role from database
    guild_data = guilds_collection.find_one({"guild_id": guild_id})
    prisoner_role_id = guild_data.get("prisoner_role_id") if guild_data else None
    prisoner_role = ctx.guild.get_role(int(prisoner_role_id)) if prisoner_role_id else None

    if not prisoner_role:
        await ctx.message.reply("❌ No prisoner role set for this server. Use the command to set it.")
        return

    # Check if a channel was mentioned (ID or mention)
    if channel:
        if channel.isdigit():
            channel_to_add = ctx.guild.get_channel(int(channel))
        else:
            channel_to_add = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None

        if not channel_to_add:
            await ctx.message.reply("❌ Invalid channel ID or mention!")
            return
    else:
        channel_to_add = ctx.channel  # Use the current channel if none was specified

    # Add the channel to exceptions
    exception_manager = ExceptionManager(db)
    if not exception_manager.add_exception(guild_id, str(channel_to_add.id)):  
        await ctx.message.reply(f"⚠ Channel {channel_to_add.name} is already in the exception list!")
        return

    # Update permissions
    if isinstance(channel_to_add, discord.VoiceChannel):
        await channel_to_add.set_permissions(prisoner_role, view_channel=True, speak=True, connect=True)
    elif isinstance(channel_to_add, discord.TextChannel):
        await channel_to_add.set_permissions(prisoner_role, read_messages=True, send_messages=True)

    await ctx.message.reply(f"✅ Channel {channel_to_add.name} has been added to exceptions.")


# Remove channel from exceptions
@bot.command()
@commands.has_permissions(administrator=True)
async def rem(ctx, *, channel=None):
    guild_id = str(ctx.guild.id)
    channel_to_remove = None

    # Retrieve prisoner role from database
    guild_data = guilds_collection.find_one({"guild_id": guild_id})
    prisoner_role_id = guild_data.get("prisoner_role_id") if guild_data else None
    prisoner_role = ctx.guild.get_role(int(prisoner_role_id)) if prisoner_role_id else None

    if not prisoner_role:
        await ctx.message.reply("❌ No prisoner role has been set for this server. Use `!set_prisoner_role` first.")
        return

    # Check if channel is provided (ID or mention)
    if channel:
        if channel.isdigit():
            channel_to_remove = ctx.guild.get_channel(int(channel))
        else:
            channel_to_remove = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None

        if not channel_to_remove:
            await ctx.message.reply("❌ Invalid channel! Provide a valid ID or mention a channel.")
            return
    else:
        channel_to_remove = ctx.channel

    # Check if the channel is in exceptions
    exception_manager = ExceptionManager(db)
    if not exception_manager.is_exception(guild_id, str(channel_to_remove.id)):
        await ctx.message.reply(f"⚠ Channel {channel_to_remove.mention} is not in the exception list.")
        return

    # Remove channel from exceptions
    exception_manager.remove_exception(guild_id, str(channel_to_remove.id))

    # Update channel permissions
    if isinstance(channel_to_remove, discord.VoiceChannel):
        await channel_to_remove.set_permissions(prisoner_role, speak=False, connect=False)
    elif isinstance(channel_to_remove, discord.TextChannel):
        await channel_to_remove.set_permissions(prisoner_role, read_messages=False, send_messages=False)

    await ctx.message.reply(f"✅ Channel {channel_to_remove.mention} has been removed from exceptions.")


# List all exception channels
@bot.command(aliases=['show_exp'])
@commands.has_permissions(administrator=True)
async def list(ctx):
    guild_id = str(ctx.guild.id)
    exception_manager = ExceptionManager(db)
    exceptions = exception_manager.get_exceptions(guild_id)

    if exceptions:
        exception_channels = []
        for channel_id in exceptions:
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                channel_type = '🔊 Voice' if isinstance(channel, discord.VoiceChannel) else '💬 Text'
                exception_channels.append(f"**{channel.mention}** ({channel_type})")

        if exception_channels:
            embed = discord.Embed(title="📌 Exception Channels", color=0x2f3136)
            embed.add_field(name="📝 Channels:", value="\n".join(exception_channels), inline=False)
            await ctx.message.reply(embed=embed)
        else:
            await ctx.message.reply("⚠ No valid exception channels found.")
    else:
        await ctx.message.reply("⚠ No exception channels found in this server.")
        
# Ban command
@bot.command(aliases = ['افتح', 'اغرق', 'برا', 'افتحك', 'اشخطك', 'انهي'])
@commands.has_permissions(ban_members=True)
async def زوطلي(ctx, user: discord.User = None, *, reason = "No reason"):

    if user is None:
        embed = discord.Embed(title="📝 أمر البان", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -زوطلي \n",
            "•  الوظيفة        :  باند للعضو \n",
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
        await ctx.message.reply("You cannot ban yourself!")
        return

    # if user.top_role >= ctx.guild.me.top_role:
    #     await ctx.message.reply("❌ | I cannot jail this member because their role is equal to or higher than mine.")
    #     return

    try:
        if user:
            user_id = user.id

        # محاولة الحصول على المستخدم من السيرفر
        member = ctx.guild.get_member(user_id)

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
        await ctx.message.reply("Please mention the user or their ID to unban")
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
        
# Jail command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['كوي', 'عدس', 'ارمي', 'اشخط', 'احبس', 'حبس'])
async def سجن(ctx, member: discord.Member = None, duration: str = None):
    guild = ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        await ctx.message.reply("The bot is not properly set up for this server.")
        return

    prisoner_role_id = server_data.get('prisoner_role_id')
    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role is not set.")
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        await ctx.message.reply("The 'Prisoner' role no longer exists.")
        return

    if prisoner_role in member.roles:
        await ctx.message.reply(f"❌ | {member.mention} is already in prison.")
        return

    if member is None:
        embed = discord.Embed(title="📝 أمر السجن", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -سجن \n",
            "•  الوظيفة        :  سجن العضو \n"
        ]

        aliases_lines = [
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

    if isinstance(member, discord.Member):
        member = member
    else:
        try:
            member = guild.get_member(int(member))
            if not member:
                member = await bot.fetch_user(int(member))
            if not member:
                raise ValueError("Member not found.")
        except (ValueError, discord.NotFound):
            await ctx.message.reply("Member not found. Please provide a valid ID or mention.")
            return

    if member == ctx.author:
        await ctx.message.reply("You cannot jail yourself.")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.message.reply("I cannot jail this member because their role is equal to or higher than mine.")
        return

    if duration is None:
        duration = "8h"

    if duration[-1] not in ["m", "h", "d"]:
        await ctx.message.reply("Please specify a valid duration, like: (30m, 1h, 1d).")
        return

    time_units = {"m": "minutes", "h": "hours", "d": "days"}
    try:
        time_value = int(duration[:-1])
    except ValueError:
        await ctx.message.reply("Invalid duration. Use numbers followed by m, h, or d.")
        return

    delta = timedelta(**{time_units[duration[-1]]: time_value})
    release_time = datetime.now(timezone.utc) + delta
    
    # Save member's roles and jail them
    previous_roles = [role.id for role in member.roles if role != guild.default_role]
    await member.edit(roles=[prisoner_role])

    # Save roles to MongoDB
    collection.update_one(
        {"user_id": member.id, "guild_id": ctx.guild.id},
        {"$set": {"roles": previous_roles, "release_time": release_time}},
        upsert=True
    )

    await ctx.message.reply(f"{member.mention} has been jailed for {duration}.")

    if duration:
        await asyncio.sleep(delta.total_seconds())
        await release_member(ctx, member)

async def release_member(ctx, member: discord.Member):
    guild = ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        return

    prisoner_role_id = server_data.get('prisoner_role_id')
    if not prisoner_role_id:
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))

    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})
    if not data:
        return

    if prisoner_role and prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    previous_roles = [guild.get_role(role_id) for role_id in data.get("roles", []) if guild.get_role(role_id)]
    if previous_roles:
        await member.edit(roles=previous_roles)
    else:
        await member.edit(roles=[guild.default_role])

    collection.delete_one({"user_id": member.id, "guild_id": guild.id})

    await ctx.send(f"{member.mention} has been released from jail.")

# Pardon command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['اعفاء', 'اخراج', 'طلع', 'سامح', 'اخرج', 'اطلع', 'اعفي'])
async def عفو(ctx, member: discord.Member = None):
    guild = ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        await ctx.message.reply("⚠️ The bot is not properly set up for this server.")
        return

    prisoner_role_id = server_data.get("prisoner_role_id") if server_data else None
    if not prisoner_role_id:
        await ctx.message.reply("⚠️ The 'Prisoner' role is not set.")
        return

    prisoner_role = guild.get_role(int(prisoner_role_id)) if prisoner_role_id else None
    if not prisoner_role:
        await ctx.message.reply("⚠️ The saved prisoner role does not exist anymore.")
        return

    if member is None:
        await ctx.message.reply("⚠️ You must mention a member to pardon!")
        return

    if isinstance(member, str):
        member = guild.get_member(int(member))
        if not member:
            await ctx.message.reply("❌ Member not found. Please provide a valid ID or mention.")
            return

    if member == ctx.author:
        await ctx.message.reply("❌ You cannot pardon yourself!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.message.reply("❌ I cannot pardon this member because their role is equal to or higher than mine.")
        return

    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})

    if not data:
        if prisoner_role in member.roles:
            await ctx.message.reply(f"⚠️ {member.mention} has the prisoner role but is not found in the database! Fixing...")
            collection.insert_one({"user_id": member.id, "guild_id": guild.id, "roles": []})  # إصلاح المشكلة
        else:
            await ctx.message.reply(f"❌ {member.mention} is not in jail.")
            return

    if prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    previous_roles = [guild.get_role(role_id) for role_id in (data.get("roles") or []) if guild.get_role(role_id)]
    if previous_roles:
        await member.edit(roles=previous_roles)
    else:
        await member.edit(roles=[guild.default_role])

    collection.delete_one({"user_id": member.id, "guild_id": guild.id})

    await ctx.message.reply(f"✅ {member.mention} has been pardoned!")

@bot.command()
@commands.has_permissions(administrator=True)
async def words(ctx):
    # جلب الكلمات المحظورة من قاعدة البيانات
    banned_words = [word['word'] for word in words_collection.find()]
    
    embed = discord.Embed(title="📋 Manage Banned Words", description="Here you can manage the banned words in the server.", color=0xFF5733)

    # إذا كانت هناك كلمات محظورة، اعرضها
    if banned_words:
        embed.add_field(name="Banned Words", value="\n".join(banned_words), inline=False)
    else:
        embed.add_field(name="Banned Words", value="No words have been banned yet.", inline=False)

    # أزرار للتفاعل
    add_button = Button(label="Add Banned Word", style=discord.ButtonStyle.green)
    list_button = Button(label="List Banned Words", style=discord.ButtonStyle.blurple)
    remove_button = Button(label="Remove Banned Word", style=discord.ButtonStyle.red)

    # إنشاء الواجهة التي تحتوي على الأزرار
    view = View()
    view.add_item(add_button)
    view.add_item(list_button)
    view.add_item(remove_button)

    # عند الضغط على زر "Add Banned Word"
    async def add_word_callback(interaction):
        await interaction.response.send_message("📝 Please type the word you want to add to the banned list.", ephemeral=True)
        try:
            message = await bot.wait_for('message', check=lambda m: m.author == interaction.user, timeout=60.0)
            word = message.content.lower()

            # تأكد إذا الكلمة موجودة مسبقاً
            if words_collection.find_one({"word": word}):
                await interaction.followup.send(f"❌ The word '{word}' is already banned.")
            else:
                words_collection.insert_one({"word": word})
                await interaction.followup.send(f"✅ The word '{word}' has been successfully added to the banned list.")
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ You took too long to provide a word. Try again.")

    add_button.callback = add_word_callback

    # عند الضغط على زر "List Banned Words"
    async def list_words_callback(interaction):
        banned_words = [word['word'] for word in words_collection.find()]
        if banned_words:
            await interaction.response.send_message(f"📝 Banned Words:\n{', '.join(banned_words)}")
        else:
            await interaction.response.send_message("❌ No banned words have been added yet.")

    list_button.callback = list_words_callback

    # عند الضغط على زر "Remove Banned Word"
    async def remove_word_callback(interaction):
        banned_words = [word['word'] for word in words_collection.find()]
        if not banned_words:
            await interaction.response.send_message("❌ No banned words to remove.")
            return
        
        await interaction.response.send_message("⚙️ Choose the word to remove.", ephemeral=True)
        for word in banned_words:
            await interaction.followup.send(f"🛑 **{word}** - To remove it, reply with the word.")

        try:
            message = await bot.wait_for('message', check=lambda m: m.author == interaction.user, timeout=60.0)
            word_to_remove = message.content.lower()
            result = words_collection.delete_one({"word": word_to_remove})

            if result.deleted_count == 0:
                await interaction.followup.send(f"❌ The word '{word_to_remove}' was not found.")
            else:
                await interaction.followup.send(f"✅ The word '{word_to_remove}' has been removed from the banned list.")
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ You took too long to provide a word to remove.")

    remove_button.callback = remove_word_callback

    await ctx.message.reply(embed=embed, view=view)


bot.run(os.environ['B'])
