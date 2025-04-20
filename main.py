import discord
from discord.ext import commands
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
from zoneinfo import ZoneInfo
TOKEN = os.getenv('B')

# print(discord.__version__)
# def get_current_ip():
#     response = requests.get('https://api.ipify.org')
#     return response.text
# print(get_current_ip()

uri = "mongodb+srv://user_b:kzsF5rOLS61wHqYU@cluster0.zriaf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(uri, tlsAllowInvalidCertificates=True)
db = client["Prison"]
collection = db["user"]
exceptions_collection = db['exceptions']
guilds_collection = db["guilds"]
offensive_words_collection = db["offensive_words"]

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

class BadWordsView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="Add Bad Words", style=discord.ButtonStyle.primary)
    async def add_words(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Use `-abad word1, word2, word3` to add bad words.", ephemeral=True)

    @discord.ui.button(label="Remove Bad Words", style=discord.ButtonStyle.danger)
    async def remove_words(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Use `-rbad word` to remove a bad word.", ephemeral=True)

    @discord.ui.button(label="List Bad Words", style=discord.ButtonStyle.secondary)
    async def list_words(self, interaction: discord.Interaction, button: discord.ui.Button):
        words = [word["word"] for word in offensive_words_collection.find({}, {"_id": 0, "word": 1})]
        if words:
            await interaction.response.send_message(f"📝 Offensive Words: {', '.join(words)}", ephemeral=True)
        else:
            await interaction.response.send_message("✅ No offensive words in the database!", ephemeral=True)

# تفعيل صلاحيات البوت المطلوبة
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.guilds = True
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)

prison_data = {}  # تخزين رتب الأعضاء المسجونين
SPAM_THRESHOLD = 20  # عدد الرسائل المسموح بها
SPAM_TIME_FRAME = 5  # إطار زمني بالثواني
TIMEOUT_DURATION_MINUTES = 10  # None ستعني تايم أوت دائم

user_messages = defaultdict(list)
user_messages = {}
user_spam_messages = {}

async def check_prisoners_loop():
    await bot.wait_until_ready()  # انتظر حتى يشتغل البوت بالكامل

    while not bot.is_closed():
        now = datetime.now(timezone.utc)  # وقت UTC الحالي

        for guild in bot.guilds:
            guild_id = str(guild.id)
            prisoners_data = collection.find({"guild_id": guild_id})

            for prisoner in prisoners_data:
                release_time = prisoner.get("release_time")
                
                if release_time:
                    # إذا كان release_time سلسلة نصية، نرجعها إلى كائن datetime
                    if isinstance(release_time, str):
                        release_time = datetime.fromisoformat(release_time)

                    # إذا حان وقت الإفراج
                    if release_time <= now:
                        member = guild.get_member(prisoner["user_id"])
                        
                        if member:
                            await release_member(None, member, silent=True)
                            collection.delete_one({"user_id": prisoner["user_id"], "guild_id": guild_id})
        
        # النوم لمدة 60 ثانية قبل التحقق مرة أخرى
        await asyncio.sleep(60)

async def check_prisoners_once():
    now = datetime.now(timezone.utc)

    for guild in bot.guilds:
        guild_id = str(guild.id)
        prisoners_data = collection.find({"guild_id": guild_id})

        for prisoner in prisoners_data:
            release_time = prisoner.get("release_time")
            print(f"Checking prisoner {prisoner['user_id']} in guild {guild_id} | Release Time: {release_time}")

            if release_time:
                if isinstance(release_time, str):
                    release_time = datetime.fromisoformat(release_time)

                print(f"Current UTC: {now} | Scheduled Release: {release_time}")

                if release_time <= now:
                    member = guild.get_member(prisoner["user_id"])
                    if member:
                        await release_member(None, member, silent=True)
                        collection.delete_one({"user_id": prisoner["user_id"], "guild_id": guild_id})
                        print(f"✅ Released prisoner {prisoner['user_id']} from guild {guild_id}")
                    else:
                        collection.delete_one({"user_id": prisoner["user_id"], "guild_id": guild_id})
                        print(f"⚠️ Member {prisoner['user_id']} not found in guild {guild_id}, entry deleted.")
                        
@bot.event
async def on_ready():
    print(f"✅ Bot is ready! Logged in as {bot.user.name}")
    exception_manager = ExceptionManager(db)

    # Call check_prisoners once at startup
    await check_prisoners_once()

    # Start checking for released prisoners every minute after the bot is ready
    bot.loop.create_task(check_prisoners_loop())

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

        restricted_channels = []

        # إخفاء جميع القنوات عن الرتبة
        for channel in guild.channels:
            if str(channel.id) not in exception_channels:
                await channel.set_permissions(prisoner_role, view_channel=False, read_messages=False, send_messages=False, connect=False, speak=False)
                restricted_channels.append(channel.name)
                
        if restricted_channels:
            print(f"Restricted access to {len(restricted_channels)} channels in {guild.name} for prisoner role.")
        else:
            print(f"No restrictions were needed in {guild.name}.")

        print(f"✅ Restored exception settings for {guild.name}. User-defined exceptions are maintained.")
        
    print("✅ All exceptions have been restored successfully!")

    # # Release members whose jail time has expired
    # now = datetime.now(timezone.utc)
    # jailed_users = collection.find({})

    # for user_data in jailed_users:
    #     release_time = user_data.get("release_time")
    
    # # إذا كان release_time موجودًا وتحين وقت الإفراج
    #     if release_time:
    #         if isinstance(release_time, str):
    #             release_time = parser.parse(release_time)

    #     # التحقق إذا كانت فترة السجن قد انتهت
    #         if release_time <= now:
    #             guild = bot.get_guild(user_data["guild_id"])
    #             if not guild:
    #                 continue

    #             member = guild.get_member(user_data["user_id"])
    #             if member:
    #                 try:
    #                     await release_member(discord.Object(id=guild.id), member, silent=True)
    #                     print(f"✅ Released {member.name} from jail in {guild.name} (auto-release).")
    #                 except Exception as e:
    #                     print(f"❌ Failed to release {member.id} in {guild.id}: {e}")

# on message
@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Log user messages
    guild = message.guild
    user_id = message.author.id
    current_time = datetime.now(timezone.utc)

    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    prisoner_role_id = server_data.get("prisoner_role_id") if server_data else None
    prisoner_role = None
    
    if prisoner_role_id:
        prisoner_role = guild.get_role(int(prisoner_role_id))
    
    if message.content.strip().lower() == "بدر":
        await message.reply("عمي المؤسس فديته 🤩")
        
    if user_id not in user_messages:
        user_messages[user_id] = []
        user_spam_messages[user_id] = []  # Store messages for deletion

    # Store message timestamp and actual message
    user_messages[user_id].append(current_time)
    user_spam_messages[user_id].append(message)

    # Remove old messages outside the time frame
    user_messages[user_id] = [
        msg_time for msg_time in user_messages[user_id] 
        if current_time - msg_time <= timedelta(seconds=SPAM_TIME_FRAME)
    ]

    user_spam_messages[user_id] = [
        msg for msg in user_spam_messages[user_id]
        if current_time - msg.created_at <= timedelta(seconds=SPAM_TIME_FRAME)
    ]

    # Check for spam (Ignore admins)
    if len(user_messages[user_id]) >= SPAM_THRESHOLD:
        if not message.author.guild_permissions.administrator:
            try:
                # Ensure timeout duration is defined
                if TIMEOUT_DURATION_MINUTES is None:
                    raise ValueError("TIMEOUT_DURATION_MINUTES is not defined")

                # Convert minutes to seconds
                timeout_duration_seconds = TIMEOUT_DURATION_MINUTES * 60
                timeout_until = current_time + timedelta(seconds=timeout_duration_seconds)  # Use offset-aware datetime

                if message.author.timed_out_until and message.author.timed_out_until > current_time:
                    return  # Skip if the user is already timed out

                # Apply timeout punishment first
                await message.author.timeout(timeout_until, reason="Spam detected")
                await message.channel.send(f"🚫 {message.author.mention} has been timed out for spamming")

                # Delete all spam messages AFTER timeout
                deleted_count = 0
                for msg in user_spam_messages[user_id]:
                    try:
                        await msg.delete()
                        deleted_count += 1
                    except discord.NotFound:
                        pass  # Message is already deleted
                    except discord.Forbidden:
                        await message.channel.send(f"❌ I don't have permission to delete messages from {message.author.mention}")
                        break

                if deleted_count > 0:
                    await message.channel.send(f"🗑️ Deleted {deleted_count} spam messages from {message.author.mention}")

                # Clear user data after punishment
                user_messages[user_id] = []
                user_spam_messages[user_id] = []
                
            except discord.Forbidden:
                await message.channel.send(f"❌ I don't have permission to timeout {message.author.mention}")
            except ValueError as ve:
                print(f"Error: {ve}")
                await message.channel.send(f"❌ Error: {ve}")
            except Exception as e:
                print(f"Error: {e}")
                await message.channel.send("❌ An unexpected error occurred")
        else:
            user_messages[user_id] = []
            user_spam_messages[user_id] = []

    # Offensive word detection
    offensive_words = [word["word"] for word in offensive_words_collection.find({}, {"_id": 0, "word": 1})]
    message_words = re.findall(r'\b\w+\b', message.content.lower())  # Extract words from message
    matched_word = next((word for word in offensive_words if word in message_words or re.search(rf'\b{word}\b', message.content.lower())), None)
    
    if matched_word:
        if not message.content.startswith("-") and not message.author.guild_permissions.administrator:
            try:
                bot_member = guild.get_member(bot.user.id)
                if prisoner_role >= bot_member.top_role:
                    await message.channel.send("❌ I don't have permission to assign the prisoner role!")
                    return

                if prisoner_role in message.author.roles:
                    print(f"User {message.author.mention} is already jailed. No action taken.")
                    return

                default_duration = "8h"
                time_units = {"m": "minutes", "h": "hours", "d": "days"}
                time_value = int(default_duration[:-1])
                delta = timedelta(**{time_units[default_duration[-1]]: time_value})

                release_time = datetime.now(timezone.utc) + delta

                # **Save previous roles in the database**
                previous_roles = [role.id for role in message.author.roles if role != message.guild.default_role and role != prisoner_role]
                collection.update_one(
                    {"user_id": message.author.id, "guild_id": message.guild.id},
                    {"$set": {"roles": previous_roles, "release_time": release_time}},
                    upsert=True
                )

                # **Assign prisoner role and remove all other roles**
                await message.author.edit(roles=[prisoner_role])
                await message.delete()

                # Fetch mod log channel from database
                server_data = db["guild_settings"].find_one({"guild_id": str(message.guild.id)})
                mod_log_channel = None  # افتراضيًا لا يوجد روم مخصص

                if server_data and "mod_log_channel_id" in server_data:
                    try:
                        mod_log_channel_id = int(server_data["mod_log_channel_id"])  # تحويل إلى رقم صحيح
                        mod_log_channel = bot.get_channel(mod_log_channel_id)  # استرجاع القناة

                        if mod_log_channel is None:
                            print(f"⚠️ تحذير: القناة المحددة كـ mod_log (ID: {mod_log_channel_id}) غير موجودة أو لم يتم تحميلها.")
                    except ValueError:
                        print(f"❌ خطأ: المعرف المحفوظ للقناة ({server_data['mod_log_channel_id']}) ليس رقماً صحيحًا.")

                if mod_log_channel:
                    await mod_log_channel.send(f"⚠️ {message.author.mention} has been jailed for using offensive language!\n🚫 Offending word: `{matched_word}`\nFull message: `{message.content}`")
                else:
                    await message.channel.send(f"⚠️ {message.author.mention} has been jailed for using offensive language!\n🚫 Offending word: `{matched_word}`\nFull message: `{message.content}`")
                
                # Auto-release after duration
                await asyncio.sleep(delta.total_seconds())
                await release_member(message.guild, message.author)

            except discord.Forbidden:
                await message.channel.send(f"❌ I don't have permission to jail {message.author.mention}.")
            except Exception as e:
                print(f"Error in auto-jail: {e}")

    if message.content.startswith("-"):
        command_name = message.content.split(" ")[0][1:]  # Extract command name
        if not bot.get_command(command_name) and not any(command_name in cmd.aliases for cmd in bot.commands):
            return  # Ignore unknown commands

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
        
    # else: await ctx.message.reply(f"❌ | An error occurred: {str(error)}")

# on_member_join
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        return

    prisoner_role_id = server_data.get("prisoner_role_id")
    if not prisoner_role_id:
        return

    prisoner_role = guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        return

    # التحقق مما إذا كان العضو مسجونًا في قاعدة البيانات
    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})
    if data:
        await member.edit(roles=[prisoner_role])
        
        try:
            await member.send(f"⚠️ {member.mention} You have been sent back to jail!")
        except discord.Forbidden:
            print(f"⚠️ Cannot send DM to {member.name}#{member.discriminator}. They might have DMs disabled.")

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        return

    prisoner_role_id = server_data.get("prisoner_role_id")
    if not prisoner_role_id:
        return

    prisoner_role = guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        return

    # التأكد أن العضو لديه رتبة السجن
    if prisoner_role in after.roles:
        for role in after.roles:
            if role != prisoner_role and role != guild.default_role:  # استثناء الرتبة الافتراضية
                await after.remove_roles(role)
                print(f"🚨 Removed {role.name} from {after.display_name} because they are jailed.")

@bot.command()
@commands.has_permissions(administrator=True)
async def set(ctx, role: discord.Role = None):
    guild_id = str(ctx.guild.id)
    guild = ctx.guild

    if role is None:
        await ctx.message.reply("❌ You must mention a role or provide a valid role ID.")
        return

    # استرجاع البيانات المخزنة من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": guild_id})
    current_role_id = server_data.get("prisoner_role_id") if server_data else None
    exception_channels = server_data.get("exception_channels", []) if server_data else []

    # إذا كانت نفس الرتبة المخزنة، لا داعي للحفظ مرة أخرى
    if current_role_id == str(role.id):
        await ctx.message.reply(f"⚠️ The prisoner role is already set to: **{role.name}**.")
        return

    # تحديث الرتبة في قاعدة البيانات
    guilds_collection.update_one(
        {"guild_id": guild_id},
        {"$set": {"prisoner_role_id": str(role.id)}},
        upsert=True
    )

    # إخفاء كل القنوات عن الرتبة المختارة باستثناء القنوات المستثناة
    for channel in guild.channels:
        if str(channel.id) not in exception_channels:
            await channel.set_permissions(role, view_channel=False)

    await ctx.message.reply(f"✅ The prisoner role has been set to: **{role.name}**.")

@bot.command()
@commands.has_permissions(administrator=True)
async def mod(ctx, channel: discord.TextChannel):
    server_data = db["guild_settings"].find_one({"guild_id": str(ctx.guild.id)})
    existing_channel_id = server_data.get("mod_log_channel_id") if server_data else None

    if existing_channel_id and str(existing_channel_id) == str(channel.id):
        await ctx.message.reply(f"⚠️ The moderation log channel is already set to {channel.mention}.")
        return

    db["guild_settings"].update_one(
        {"guild_id": str(ctx.guild.id)},
        {"$set": {"mod_log_channel_id": str(channel.id)}},
        upsert=True
    )
    await ctx.message.reply(f"✅ The moderation log channel has been set to {channel.mention}")


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
    exception_manager.add_exception(guild_id, str(channel_to_add.id))  # No restriction on duplicates

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

    # Remove channel from exceptions
    exception_manager = ExceptionManager(db)
    exception_manager.remove_exception(guild_id, str(channel_to_remove.id))

    await channel_to_remove.set_permissions(prisoner_role, view_channel=False, read_messages=False, send_messages=False, connect=False, speak=False)

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


@bot.command()
@commands.has_permissions(administrator=True)
async def abad(ctx, *, words: str):
    word_list = [word.strip().lower() for word in words.split(",")]
    added_words = []
    for word in word_list:
        if not offensive_words_collection.find_one({"word": word, "server_id": ctx.guild.id}):
            offensive_words_collection.insert_one({"word": word, "server_id": ctx.guild.id})
            added_words.append(word)
    if added_words:
        await ctx.message.reply(f"✅ Added: {', '.join(added_words)} to the offensive words list!")
    else:
        await ctx.message.reply("⚠ All words are already saved!")

@bot.command()
@commands.has_permissions(administrator=True)
async def rbad(ctx, *, words: str):
    word_list = [word.strip().lower() for word in words.split(",")]
    removed_words = []
    for word in word_list:
        if offensive_words_collection.find_one({"word": word, "server_id": ctx.guild.id}):
            offensive_words_collection.delete_one({"word": word, "server_id": ctx.guild.id})
            removed_words.append(word)
    if removed_words:
        await ctx.message.reply(f"✅ Removed: {', '.join(removed_words)} from the offensive words list!")
    else:
        await ctx.message.reply("⚠️ None of the provided words were found in the database!")

@bot.command()
@commands.has_permissions(administrator=True)
async def lbad(ctx):
    words = [word["word"] for word in offensive_words_collection.find({"server_id": ctx.guild.id}, {"_id": 0, "word": 1})]
    if words:
        await ctx.message.reply(f"📝 Offensive Words: {', '.join(words)}")
    else:
        await ctx.message.reply("✅ No offensive words in the database!")
        
@bot.command()
@commands.has_permissions(administrator=True)
async def pbad(ctx):
    await ctx.message.reply("🔧 Manage Offensive Words:", view=BadWordsView())

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

    try:
        fetched_user = await bot.fetch_user(user.id)
        await ctx.guild.ban(fetched_user, delete_message_days=0, reason=reason)

        embed = discord.Embed(
            title="✅ User Banned!",
            description=f"**User:** {fetched_user.mention} (`{fetched_user.id}`)\n**Reason:** {reason}",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Banned by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

        await ctx.message.reply(embed=embed)

    except discord.NotFound:
        await ctx.message.reply("❌ User not found. Make sure the ID is correct.")
    except discord.Forbidden:
        await ctx.message.reply("❌ I don't have permission to ban this user.")
    except discord.HTTPException as e:
        await ctx.message.reply(f"An error occurred while trying to ban the user: {e}")

@bot.command(aliases=['unban', 'un'])
@commands.has_permissions(ban_members=True)
async def فك(ctx, *, user_input=None):
    if user_input is None:
        await ctx.reply("Please mention the user or their ID to unban.")
        return

    try:
        # تحديد الـ ID سواء من منشن أو ID مباشرة
        if user_input.startswith("<@") and user_input.endswith(">"):
            user_id = int(user_input[2:-1].replace("!", ""))  # استخراج ID من المنشن
        else:
            user_id = int(user_input)  # استخدام ID مباشرة

        # البحث في قائمة الباندات
        async for ban_entry in ctx.guild.bans():
            if ban_entry.user.id == user_id:
                await ctx.guild.unban(ban_entry.user)  # فك الباند

                embed = discord.Embed(
                    title="✅ Unban Successful",
                    description=f"User {ban_entry.user.mention} (`{ban_entry.user.id}`) has been unbanned.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Action by: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                embed.timestamp = ctx.message.created_at  # الوقت

                await ctx.reply(embed=embed)
                return

        # لو ما كان متبند
        embed = discord.Embed(
            title="❌ Unban Failed",
            description=f"User with ID `{user_id}` is not banned.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Action by: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.timestamp = ctx.message.created_at
        await ctx.reply(embed=embed)

    except ValueError:
        embed = discord.Embed(
            title="⚠️ Invalid Input",
            description="Please mention a user (`@username`) or enter their ID correctly.",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Action by: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.timestamp = ctx.message.created_at
        await ctx.reply(embed=embed)

    except discord.HTTPException as e:
        embed = discord.Embed(
            title="❌ An Error Occurred",
            description=f"Failed to unban the user: `{e}`",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Action by: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.timestamp = ctx.message.created_at
        await ctx.reply(embed=embed)
        
# Jail command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['كوي', 'عدس', 'ارمي', 'اشخط', 'احبس', 'حبس'])
async def سجن(ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
    guild = ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

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

    if isinstance(member, discord.Member):
        pass
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
        duration = "8h"  # default to 8 hours
    if reason is None:
        reason = "No reason provided"  # default reason

    time_units = {"m": "minutes", "h": "hours", "d": "days", "o": "days"}  # assuming "o" is months

    if duration[-1] in time_units:
        try:
            time_value = int(duration[:-1])
        except ValueError:
            await ctx.message.reply("Invalid duration. Use numbers followed by m, h, d, or o.")
            return
    else:
        await ctx.message.reply("Invalid duration format. Use m, h, d, or o.")
        return

    if duration[-1] == "o":
        delta = timedelta(days=time_value * 30)
    else:
        delta = timedelta(**{time_units[duration[-1]]: time_value})

    saudi_tz = ZoneInfo("Asia/Riyadh")
    release_time = datetime.now(saudi_tz) + delta
    
    # Save member's roles and jail them
    previous_roles = []
    for role in member.roles:
        if role == guild.default_role:
            continue
        if role.is_premium_subscriber():
            continue
        previous_roles.append(role.id)

    await member.edit(roles=[prisoner_role])  # حذف كل الرتب وإعطاء رتبة السجن

    collection.update_one(
        {"user_id": member.id, "guild_id": ctx.guild.id},
        {"$set": {
            "roles": previous_roles,
            "release_time": release_time.astimezone(timezone.utc).isoformat()
        }},
        upsert=True
    )

    # Send embed
    if duration[-1] == "m" and time_value < 1:
        duration_text = f"المدة: {time_value} ثواني"
    else:
        duration_text = f"المدة: {duration}"
        
    embed = discord.Embed(
        title="**تم السجن بنجاح**",
        description=(
            f"الشخص: {member.mention}\n"
            f"{duration_text}\n"
            f"السبب: {reason}"
        ),
        color=0x2f3136
    )
    
    embed.set_footer(text=f"Action by: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.timestamp = datetime.utcnow()
    
    await ctx.message.reply(embed=embed)
    
    await asyncio.sleep(delta.total_seconds())
    await release_member(ctx, member)

async def release_member(ctx, member: discord.Member, silent=False):
    guild = member.guild if ctx is None else ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if not server_data:
        return

    prisoner_role_id = server_data.get('prisoner_role_id')
    if not prisoner_role_id:
        return

    prisoner_role = guild.get_role(int(prisoner_role_id))

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

    if not silent and ctx:
        await ctx.send(f"{member.mention} has been released from jail.")

@bot.command(aliases=['باقي', 'مدة_السجن', 'remaining'])
async def كم(ctx):
    member = ctx.author
    data = collection.find_one({"user_id": member.id, "guild_id": ctx.guild.id})

    if not data or "release_time" not in data:
        await ctx.reply("❌ | You are not currently in jail.", delete_after=5)
        await ctx.message.delete(delay=5)
        return

    release_time = data["release_time"]

    if isinstance(release_time, str):
        release_time = datetime.fromisoformat(release_time)
        if release_time.tzinfo is None:
            release_time = release_time.replace(tzinfo=timezone.utc)

    saudi_tz = ZoneInfo("Asia/Riyadh")
    release_time = release_time.astimezone(saudi_tz)

    now = datetime.now(saudi_tz)
    remaining = release_time - now

    if remaining.total_seconds() <= 0:
        await ctx.reply("✅ | Your jail time has expired, you should be released soon!", delete_after=5)
        await ctx.message.delete(delay=5)
    else:
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        release_time_str = release_time.strftime("%I:%M %p")  # 12 ساعة مع AM/PM

        await ctx.reply(
            f"⏳ | Remaining jail time: `{hours}h {minutes}m {seconds}s`\n"
            f"⏰ | Release time (Saudi): `{release_time_str}`",
            delete_after=5
        )
        await ctx.message.delete(delay=5)
        
# Prisoners command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['مساجين', 'مسجون', 'مسجونين', 'عرض'])
async def سجين(ctx):
    guild = ctx.guild
    prisoners_data = collection.find({"guild_id": guild.id})
    
    embed = discord.Embed(title="🔒 Currently Jailed Members", color=0x2f3136)
    count = 0
    jailed_list = []

    saudi_tz = ZoneInfo("Asia/Riyadh")
    now = datetime.now(saudi_tz)

    for prisoner in prisoners_data:
        member = guild.get_member(prisoner["user_id"])
        release_time = prisoner.get("release_time")

        if release_time:
            # If release_time is a string, convert it to a datetime object first
            if isinstance(release_time, str):
                release_time = datetime.fromisoformat(release_time)

            # Now that release_time is a datetime object, convert to Saudi time
            release_time = release_time.replace(tzinfo=timezone.utc).astimezone(saudi_tz)
            remaining = release_time - now

            if remaining.total_seconds() > 0:
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                remaining_str = f"{hours}h {minutes}m remaining"
            else:
                remaining_str = "Time's up (release pending)"

            release_time_str = release_time.strftime("%Y-%m-%d %I:%M %p Saudi")
        else:
            release_time_str = "Unknown"
            remaining_str = "Unknown"

        if member:
            jailed_list.append(
                f"-{member.mention} — 📆 Release: {release_time_str} | ⏳ {remaining_str}"
            )
            count += 1

    if count == 0:
        embed.description = "There are no members currently jailed."
    else:
        embed.description = "\n".join(jailed_list)

    await ctx.message.reply(embed=embed, delete_after=5)
    await ctx.message.delete(delay=5)

# Pardon command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['اعفاء', 'اخراج', 'طلع', 'سامح', 'اخرج', 'اطلع', 'اعفي'])
async def عفو(ctx, *, member: str = None):
    guild = ctx.guild
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})

    if member is None or isinstance(member, str) and member.lower() in ['الكل', 'الجميع', 'all', 'All']:
        prisoners_data = collection.find({"guild_id": ctx.guild.id})
        pardoned_members = []

        for prisoner in prisoners_data:
            member_obj = ctx.guild.get_member(prisoner["user_id"])
            if member_obj:
                await release_member(ctx, member_obj, silent=True)  # Pass silent=True
                pardoned_members.append(member_obj)

        if pardoned_members:
            mentions = ", ".join(member.mention for member in pardoned_members)
            await ctx.message.reply(
                f"✅ {len(pardoned_members)} prisoner(s) have been pardoned:\n{mentions}"
            )
        else:
            await ctx.message.reply("⚠️ No prisoners found to pardon.")
        return

    if not server_data:
        await ctx.message.reply("⚠️ The bot is not properly set up for this server.")
        return

    prisoner_role_id = server_data.get("prisoner_role_id")
    if not prisoner_role_id:
        await ctx.message.reply("⚠️ The 'Prisoner' role is not set.")
        return

    prisoner_role = guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        await ctx.message.reply("⚠️ The saved prisoner role does not exist anymore.")
        return

    # Try to get the member if it's a string
    if isinstance(member, str):
        member_id = None
        if member.startswith("<@") and member.endswith(">"):
            member_id = member.replace("<@", "").replace("!", "").replace(">", "")
        elif member.isdigit():
            member_id = member
        else:
            # Try find by name
            target = discord.utils.find(lambda m: m.name == member or m.display_name == member, guild.members)
            if target:
                member = target
            else:
                await ctx.reply("❌ | The mention is incorrect. Please mention a valid member or use a valid ID.")
                return

        if member_id:
            member = guild.get_member(int(member_id))
            if not member:
                await ctx.reply("❌ | Member not found. Please provide a valid ID or mention.")
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


bot.run(os.getenv("B"))
