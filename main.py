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
        if server_data:
            return server_data.get("exception_channels", [])
        return []

    def add_exception(self, guild_id, channel_id):
        exceptions = self.get_exceptions(guild_id)
        if channel_id not in exceptions:
            exceptions.append(channel_id)
            self.collection.update_one(
                {"guild_id": guild_id},
                {"$set": {"exception_channels": exceptions}},
                upsert=True
            )

    def remove_exception(self, guild_id, channel_id):
        exceptions = self.get_exceptions(guild_id)
        if channel_id in exceptions:
            exceptions.remove(channel_id)
            self.collection.update_one(
                {"guild_id": guild_id},
                {"$set": {"exception_channels": exceptions}}
            )



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
            guilds_collection.insert_one({"guild_id": guild_id, "exception_channels": []})
            print(f"Initialized database entry for guild {guild.name} (ID: {guild.id}).")

        # استرجاع إعدادات الرتبة "Prisoner" من قاعدة البيانات
        prisoner_settings = server_data.get('prisoner_role', {})
        prisoner_name = prisoner_settings.get('name', "Prisoner")
        prisoner_color = prisoner_settings.get('color', discord.Color.dark_gray().value)
        prisoner_permissions = prisoner_settings.get('permissions', [])

        # التحقق مما إذا كانت رتبة 'Prisoner' موجودة، وإن لم تكن موجودة يتم إنشاؤها
        prisoner_role = discord.utils.get(guild.roles, name=prisoner_name)
        if not prisoner_role:
            prisoner_role = await guild.create_role(
                name=prisoner_name,
                permissions=discord.Permissions.none(),
                color=discord.Color(prisoner_color)
            )
            print(f"Created 'Prisoner' role in {guild.name}.")
        else:
            # تحديث لون الرتبة إذا كان مختلفًا
            if prisoner_role.color != discord.Color(prisoner_color):
                await prisoner_role.edit(color=discord.Color(prisoner_color))
                print(f"Updated 'Prisoner' role color in {guild.name}.")

        # تحديث صلاحيات الرتبة
        permissions = discord.Permissions.none()
        for perm in prisoner_permissions:
            if hasattr(permissions, perm):
                setattr(permissions, perm, True)
        await prisoner_role.edit(permissions=permissions)

        # استرجاع القنوات المستثناة من قاعدة البيانات
        exception_channels = exception_manager.get_exceptions(guild_id)

        # تحديث صلاحيات القنوات
        for channel in guild.channels:
            if str(channel.id) in exception_channels:
                if isinstance(channel, discord.TextChannel):
                    await channel.set_permissions(prisoner_role, read_messages=True, send_messages=True)
                    print(f"Restored exception permissions for text channel: {channel.name} in {guild.name}.")
                elif isinstance(channel, discord.VoiceChannel):
                    await channel.set_permissions(prisoner_role, view_channel=True, connect=True, speak=True)
                    print(f"Restored exception permissions for voice channel: {channel.name} in {guild.name}.")
            else:
                await channel.set_permissions(prisoner_role, read_messages=False, send_messages=False, connect=False, speak=False)

    print("✅ All exceptions have been restored successfully!")

# on message
@bot.event
async def on_message(message):
    # Ignore bot messages
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
async def role(ctx):
    """إعداد الرتبة من خلال واجهة تفاعلية"""
    # إعداد الأزرار
    button_name = Button(label="Change Name", style=discord.ButtonStyle.primary)
    button_color = Button(label="Change Color", style=discord.ButtonStyle.success)
    button_permissions = Button(label="Change Permissions", style=discord.ButtonStyle.danger)

    # تعريف الواجهة التي تحتوي على الأزرار
    view = View()
    view.add_item(button_name)
    view.add_item(button_color)
    view.add_item(button_permissions)

    # إرسال الرسالة
    await ctx.send("Choose an option to modify the 'Prisoner' role:", view=view)

    # وظيفة الزر: تغيير الاسم
    async def change_name(interaction: discord.Interaction):
        await interaction.response.send_message("Please enter the new name for the 'Prisoner' role:")
        name_message = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == ctx.channel)
        new_name = name_message.content.strip()

        # تحديث الرتبة في قاعدة البيانات
        guild_id = str(ctx.guild.id)
        prisoner_settings = guilds_collection.find_one({"guild_id": guild_id})['prisoner_role']
        prisoner_settings['name'] = new_name
        guilds_collection.update_one({"guild_id": guild_id}, {"$set": {"prisoner_role": prisoner_settings}})
        
        await interaction.followup.send(f"The 'Prisoner' role name has been updated to: {new_name}")

    # وظيفة الزر: تغيير اللون
    async def change_color(interaction: discord.Interaction):
        await interaction.response.send_message("Please enter the new color for the 'Prisoner' role (e.g., #FF5733):")
        color_message = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == ctx.channel)
        new_color = discord.Color(int(color_message.content.strip()[1:], 16))

        # تحديث الرتبة في قاعدة البيانات
        guild_id = str(ctx.guild.id)
        prisoner_settings = guilds_collection.find_one({"guild_id": guild_id})['prisoner_role']
        prisoner_settings['color'] = new_color.value
        guilds_collection.update_one({"guild_id": guild_id}, {"$set": {"prisoner_role": prisoner_settings}})
        
        await interaction.followup.send(f"The 'Prisoner' role color has been updated to: {new_color}")

    # وظيفة الزر: تغيير الصلاحيات
    async def change_permissions(interaction: discord.Interaction):
        await interaction.response.send_message("Please enter the new permissions for the 'Prisoner' role (comma-separated, e.g., read_messages, send_messages):")
        permissions_message = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == ctx.channel)
        new_permissions = permissions_message.content.split(',')
        new_permissions = [perm.strip() for perm in new_permissions]

        # تحديث الرتبة في قاعدة البيانات
        guild_id = str(ctx.guild.id)
        prisoner_settings = guilds_collection.find_one({"guild_id": guild_id})['prisoner_role']
        prisoner_settings['permissions'] = new_permissions
        guilds_collection.update_one({"guild_id": guild_id}, {"$set": {"prisoner_role": prisoner_settings}})
        
        await interaction.followup.send(f"The 'Prisoner' role permissions have been updated to: {new_permissions}")

    # ربط الوظائف بالأزرار
    button_name.callback = change_name
    button_color.callback = change_color
    button_permissions.callback = change_permissions

# Add command
@bot.command()
@commands.has_permissions(administrator=True)
async def add(ctx, *, channel=None):
    guild_id = ctx.guild.id
    channel_to_add = None

    # إذا كانت القناة المذكورة في الأمر (باستخدام الاسم أو الـ ID)
    if channel:
        if channel.isdigit():  # تم تقديم ID
            channel_to_add = ctx.guild.get_channel(int(channel))
        else:
            # محاولة الحصول على القناة بالـ منشن
            channel_to_add = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None

        if not channel_to_add:
            await ctx.message.reply("Invalid channel ID or mention!")
            return
    else:
        # إذا لم يتم تقديم قناة، سيتم استخدام القناة التي تم إرسال الأمر فيها
        channel_to_add = ctx.channel

    # إضافة القناة إلى الاستثناء
    exception_manager = ExceptionManager(db)
    exception_manager.add_exception(str(guild_id), str(channel_to_add.id))

    # استرجاع معرّف الرتبة "Prisoner" من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": str(guild_id)})
    prisoner_role_id = server_data.get('prisoner_role_id')

    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role wasn't found in this server.")
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))
    if prisoner_role:
        if isinstance(channel_to_add, discord.VoiceChannel):
            await channel_to_add.set_permissions(prisoner_role, view_channel=True, speak=True, connect=True)
        elif isinstance(channel_to_add, discord.TextChannel):
            await channel_to_add.set_permissions(prisoner_role, read_messages=True, send_messages=True)
        await ctx.message.reply(f"Channel {channel_to_add.name} has been added to exceptions.")
    else:
        await ctx.message.reply("The 'Prisoner' role wasn't found in this server.")

# Remove command
@bot.command()
@commands.has_permissions(administrator=True)
async def rem(ctx, *, channel=None):
    guild_id = ctx.guild.id
    channel_to_remove = None

    # إذا كانت القناة المذكورة في الأمر (باستخدام الاسم أو الـ ID)
    if channel:
        if channel.isdigit():  # تم تقديم ID
            channel_to_remove = ctx.guild.get_channel(int(channel))
        else:
            # محاولة الحصول على القناة بالـ منشن
            channel_to_remove = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None

        if not channel_to_remove:
            await ctx.message.reply("Invalid channel ID or mention!")
            return
    else:
        # إذا لم يتم تقديم قناة، سيتم استخدام القناة التي تم إرسال الأمر فيها
        channel_to_remove = ctx.channel

    # إزالة القناة من الاستثناء
    exception_manager = ExceptionManager(db)
    if not exception_manager.is_exception(str(guild_id), str(channel_to_remove.id)):
        await ctx.message.reply(f"Channel {channel_to_remove.name} is not in the exception list.")
        return

    exception_manager.remove_exception(str(guild_id), str(channel_to_remove.id))

    # استرجاع معرّف الرتبة "Prisoner" من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": str(guild_id)})
    prisoner_role_id = server_data.get('prisoner_role_id')

    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role wasn't found in this server.")
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))
    if prisoner_role:
        if isinstance(channel_to_remove, discord.VoiceChannel):
            await channel_to_remove.set_permissions(prisoner_role, speak=False, connect=False)
        elif isinstance(channel_to_remove, discord.TextChannel):
            await channel_to_remove.set_permissions(prisoner_role, read_messages=False, send_messages=False)

        await ctx.message.reply(f"Channel {channel_to_remove.name} has been removed from exceptions.")
    else:
        await ctx.message.reply("The 'Prisoner' role wasn't found in this server.")

# List command
@bot.command(aliases=['عرض_الاستثناءات', 'رؤية_الرومات', 'show_exp'])
@commands.has_permissions(administrator=True)
async def list(ctx):
    guild_id = str(ctx.guild.id)
    exception_manager = ExceptionManager(db)
    exceptions = exception_manager.get_exceptions(guild_id)

    # استرجاع معرّف الرتبة "Prisoner" من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": guild_id})
    prisoner_role_id = server_data.get('prisoner_role_id')

    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role doesn't exist in this server.")
        return

    if exceptions:
        exception_channels = []
        for channel_id in exceptions:
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                channel_type = 'Voice' if isinstance(channel, discord.VoiceChannel) else 'Text'
                exception_channels.append(f"**{channel.name}** ({channel_type})")

        if exception_channels:
            embed = discord.Embed(title="Exception Channels", color=0x2f3136)
            embed.add_field(name="📝 Exception Channels List", value="\n".join(exception_channels), inline=False)
            await ctx.message.reply(embed=embed)
        else:
            await ctx.message.reply("No valid exception channels found.")
    else:
        await ctx.message.reply("No exception channels found in this server.")
        
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
    prisoner_role_id = server_data.get('prisoner_role_id')

    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
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
        # If it's a member mention
        member = member
    else:
        # If it's an ID
        try:
            # First try to get the member from guild using ID
            member = guild.get_member(int(member))
            # If member not found in the guild, try to fetch it from Discord
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
        duration = "8h"  # Default to 8 hours if no duration and a reason is provided

    # Parse duration
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
    prisoner_role = discord.utils.get(guild.roles, name="Prisoner")

    # Fetch member's data from the database
    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})
    if not data:
        return

    # Remove the "Prisoner" role
    if prisoner_role and prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    # Restore the member's previous roles
    previous_roles = [guild.get_role(role_id) for role_id in data.get("roles", []) if guild.get_role(role_id)]
    if previous_roles:
        await member.edit(roles=previous_roles)
    else:
        await member.edit(roles=[guild.default_role])  # Assign default role if no previous roles exist

    # Remove jail data from the database
    collection.delete_one({"user_id": member.id, "guild_id": guild.id})

    await ctx.send(f"{member.mention} has been released from jail.")

# Pardon command
@commands.has_permissions(administrator=True)
@bot.command(aliases=['اعفاء', 'اخراج', 'طلع', 'سامح', 'اخرج', 'اطلع', 'اعفي'])
async def عفو(ctx, member: discord.Member = None):
    guild = ctx.guild

    # استرجاع معرّف الرتبة "Prisoner" من قاعدة البيانات
    server_data = guilds_collection.find_one({"guild_id": str(guild.id)})
    prisoner_role_id = server_data.get('prisoner_role_id')

    if not prisoner_role_id:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
        return

    prisoner_role = ctx.guild.get_role(int(prisoner_role_id))
    if not prisoner_role:
        await ctx.message.reply("The 'Prisoner' role does not exist. Please ensure the bot is running properly.")
        return

    if member is None:
        embed = discord.Embed(title="📝 أمر العفو", color=0x2f3136)
        usage_lines = [
            "•  الأمر        :  -عفو \n",
            "•  الوظيفة        :  العفو عن العضو المسجون \n"
        ]

        aliases_lines = [
            "•  -اعفي \n",
            "•  -اعفاء \n",
            "•  -اخرج \n",
            "•  -سامح \n",
            "•  -طلع \n",
            "•  -اخراج \n",
            "•  -اطلع \n",
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

    if isinstance(member, str):
        member = guild.get_member(int(member))
        if not member:
            await ctx.message.reply("Member not found. Please provide a valid ID or mention.")
            return

    if member == ctx.author:
        await ctx.message.reply("You cannot pardon yourself!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.message.reply("I cannot pardon this member because their role is equal to or higher than mine.")
        return

    # Fetch member's data from the database
    data = collection.find_one({"user_id": member.id, "guild_id": guild.id})
    if not data:
        await ctx.message.reply(f"{member.mention} is not in jail.")
        return

    # Remove the "Prisoner" role
    if prisoner_role and prisoner_role in member.roles:
        await member.remove_roles(prisoner_role)

    # Restore the member's previous roles
    previous_roles = [guild.get_role(role_id) for role_id in data.get("roles", []) if guild.get_role(role_id)]
    if previous_roles:
        await member.edit(roles=previous_roles)
    else:
        await member.edit(roles=[guild.default_role])  # Assign default role if no previous roles exist

    # Remove jail data from the database
    collection.delete_one({"user_id": member.id, "guild_id": guild.id})

    await ctx.message.reply(f"{member.mention} has been pardoned")


bot.run(os.environ['B'])
