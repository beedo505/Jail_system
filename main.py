import discord
from discord.ext import commands
import logging
import asyncio
import re
import os
from collections import defaultdict
import time
from datetime import timedelta, datetime
TOKEN = os.getenv('B')

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

MESSAGE_LIMIT = 5  # عدد الرسائل قبل اعتباره سبام
TIME_WINDOW = 10  # خلال عدد الثواني هذه

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
    if message.content.startswith("-"):
        command_name = message.content.split(" ")[0][1:]
    
        if not bot.get_command(command_name) and not any(command_name in cmd.aliases for cmd in bot.commands):
            return
    await bot.process_commands(message)
    
    
    if message.author.bot:
        return  # تجاهل رسائل البوتات

    user_id = message.author.id
    current_time = time.time()
    
    # تسجيل الرسائل
    user_messages[user_id].append(current_time)

    # حذف الرسائل القديمة
    user_messages[user_id] = [
        timestamp for timestamp in user_messages[user_id]
        if current_time - timestamp <= TIME_WINDOW
    ]

    # تحقق من عدد الرسائل في الإطار الزمني
    if len(user_messages[user_id]) > MESSAGE_LIMIT:
        guild = message.guild
        await guild.ban(message.author, reason="Spam detected")
        await message.channel.send(f"⚠️ {message.author.mention} has been banned for exceeding the allowed message limit!")
        user_messages[user_id] = []  # إعادة تعيين الرسائل

    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.message.reply("❌ | The mention is incorrect")
    else:
        await ctx.message.reply(f"❌ | An error occurred: {str(error)}")

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
