import discord
from discord.ext import commands
import logging
import asyncio
import re
import os
TOKEN = os.getenv('BOT_TOKEN')


# تفعيل صلاحيات البوت
intents = discord.Intents.default()
intents.members = True  # تفعيل الصلاحية للوصول إلى الأعضاء
intents.messages = True  # تفعيل صلاحية قراءة الرسائل
intents.message_content = True # صلاحية الرد والتفاعل مع الرسائل

# إعداد سجل الأخطاء
logging.basicConfig(level=logging.ERROR)

bot = commands.Bot(command_prefix='-', intents=intents)  # تحديد البادئة "-"

# تخزين رتب الأعضاء المسجونين
jailed_roles = {}

# الحدث عندما يصبح البوت جاهزًا
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # طباعة اسم البوت في التيرمينال عندما يصبح جاهزًا
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.message.reply(":x: | Invalid mention")
    else:
        await ctx.message.reply(f":x: | An error occurred: {str(error)}")

@bot.event
async def on_guild_join(guild):
    try:
        # Create prison role
        prison_role = await guild.create_role(
            name="🔒 Prisoner",
            color=discord.Color.darker_gray(),
            permissions=discord.Permissions.none()  # no permissions
        )

        # Modify channel permissions for prisoners
        for channel in guild.channels:
            await channel.set_permissions(prison_role,
                read_messages=False,
                view_channel=False
            )

        # Create prison category
        prison_category = await guild.create_category(
            name="🏛️ Central Prison",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                prison_role: discord.PermissionOverwrite(
                    read_messages=True,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            }
        )

        # Create prison text channel
        await guild.create_text_channel(
            name="💀︱Prison",
            category=prison_category
        )

        # Create admin communication channel
        await guild.create_text_channel(
            name="📮︱Prisoner-Requests",
            category=prison_category
        )

        # Create prison voice channel
        await guild.create_voice_channel(
            name="🔊︱Prison-voice",
            category=prison_category
        )

    except Exception as e:
        print(f"An error occurred: {e}")

# أمر سجن: -سجن @username reason
@bot.command(aliases = ['كوي' , 'عدس' , 'ارمي' , 'اشخط' , 'احبس'])
@commands.has_permissions(administrator=true)
async def سجن(ctx, member: discord.Member = None, time_unit: str = "1d", *, reason = "No reason"):
    try:
        prison_role = discord.utils.get(ctx.guild.roles, name="🔒 Prisoner")
        
        # التحقق من المنشن للعضو المراد سجنه
        if not member:
            await ctx.message.reply("⚠️ Please mention the member you want to jail.")
            return
            
        # حفظ الرولات الأصلية للعضو قبل السجن
            prisoner_roles[member.id] = [role.id for role in member.roles if role != ctx.guild.default_role]

        # إضافة رول السجن وإزالة باقي الرولات
        await member.remove_roles(member.roles[1:])
        await member.add_roles(prison_role)
        await ctx.message.reply(f"✅ The member {member.mention} has been jailed for {time_unit}!")

        match = re.match(r"(\d+)([a-zA-Z]+)", time_unit)
        if not match:
            await ctx.message.reply("⚠️ Invalid time format. Please use something like '1d', '2h', or '30m'.")
            return

        time = int(match.group(1))  # The number part
        unit = match.group(2).lower()  # The unit part (d, h, m)

         # Convert the time to seconds based on the chosen unit
        if unit in ["minute", "minutes", "m"]:
            seconds = time * 60
        elif unit in ["hour", "hours", "h"]:
            seconds = time * 3600
        elif unit in ["day", "days", "d"]:
            seconds = time * 86400
        else:
            await ctx.message.reply("⚠️ Invalid unit. Please choose from 'minute', 'hour', or 'day' and their shortcuts.")
            return

        # Wait for the specified time and then release the member from jail
        await asyncio.sleep(seconds)  # Wait in seconds
        original_roles = jailed_roles.pop(member.id)  # Restore the original roles
        await member.edit(roles=original_roles)  # Restore the roles
        await ctx.message.reply(f"✅ {member.mention} has been released from jail.")

    except Exception as e:
        await ctx.message.reply(f"⚠️ An error occurred while executing the command: {str(e)}")
        logging.error(f"Error in 'سجن' command: {str(e)}")  # سجل الخطأ في سجل الأخطاء

# أمر عفو: -عفو @username
@bot.command()
@commands.has_permissions(administrator=true)
async def عفو(ctx, member: discord.Member = None):
    try:
        prison_role = discord.utils.get(ctx.guild.roles, name="🔒 Prisoner")
        
        # التحقق من المنشن للعضو المراد العفو عنه
        if not member:
            await ctx.message.reply("⚠️ Please mention the member you want to pardon.")
            return

        print("The pardon command 'عفو' was invoked")  # رسالة تحقق
        if member.id not in prison_role:
            await ctx.message.reply(f"⚠️ {member.mention} is not jailed.")
            logging.warning(f"{member.mention} is not jailed")  # سجل تحذير إذا لم يكن العضو مسجونًا
            return
            
        if prison_role in member.roles:
            await member.remove_roles(prison_role)

       if member.id in prisoner_roles:
                roles_to_add = [ctx.guild.get_role(role_id) for role_id in prisoner_roles[member.id]]
                roles_to_add = [role for role in roles_to_add if role is not None]
                await member.add_roles(*roles_to_add)
                del prisoner_roles[member.id]
            await ctx.send(f"The release of {member.mention} has been issued!")
        else:
            await ctx.send(f"{member.mention} is not imprisoned!")
            

        """حذف جميع الرولات بعد تنفيذ امر العفو"""
        # prison_role = discord.utils.get(ctx.guild.roles, name="Jail")
        # if prison_role:
        #     await member.remove_roles(prison_role, reason="Pardon from jail")

    except Exception as e:
        await ctx.message.reply(f"⚠️ An error occurred while executing the command: {str(e)}")
        logging.error(f"Error in 'عفو' command: {str(e)}")  # تسجيل الخطأ في سجل الأخطاء
        
bot.run(os.environ['B'])
