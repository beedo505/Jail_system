import discord
from discord.ext import commands
import logging
import asyncio
import re
import os
TOKEN = os.getenv('B')

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
        await ctx.message.reply("❌ | The mention is incorrect")
    else:
        await ctx.message.reply(f"❌ | An error occurred: {str(error)}")

# أمر سجن: -سجن @username reason
@bot.command(aliases = ['كوي' , 'عدس' , 'ارمي' , 'اشخط' , 'احبس'])
async def سجن(ctx, member: discord.Member = None, time_unit: str = "1d", *, reason = "No reason"):
    try:
        # التحقق من المنشن للعضو المراد سجنه
        if not member:
            await ctx.message.reply("⚠️ Please mention the member you want to jail.")
            return

        if member.id in jailed_roles:
            await ctx.message.reply(f"⚠️ The member {member.mention} is already jailed!")
            return
        print("The jail command 'سجن' was invoked")  # رسالة تحقق
        jail_role = discord.utils.get(ctx.guild.roles, name="Jail")
        if not jail_role:
            await ctx.message.reply("⚠️ The 'Jail' role was not found. Please create the role first")
            logging.error("The role 'Jail' was not found.")  # سجل الخطأ إذا لم يكن الدور موجودًا
            return

        # حفظ الرولات الأصلية للعضو قبل السجن
        if member.id not in jailed_roles:
            jailed_roles[member.id] = [role for role in member.roles if role != ctx.guild.default_role]

        # إضافة رول السجن وإزالة باقي الرولات
        await member.edit(roles=[jail_role], reason=reason)
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
async def عفو(ctx, member: discord.Member = None):
    try:
        # التحقق من المنشن للعضو المراد العفو عنه
        if not member:
            await ctx.message.reply("⚠️ Please mention the member you want to pardon.")
            return

        print("The pardon command 'عفو' was invoked")  # رسالة تحقق
        if member.id not in jailed_roles:
            await ctx.message.reply(f"⚠️ {member.mention} is not jailed.")
            logging.warning(f"{member.mention} is not jailed")  # سجل تحذير إذا لم يكن العضو مسجونًا
            return

        # ارجاع كل الرولات كما كانت
        original_roles = jailed_roles.pop(member.id)  # إزالة العضو من القاموس بعد استعادة رولاته
        await member.edit(roles=original_roles)
        await ctx.message.reply(f"✅ The member {member.mention} has been pardoned.")

        # حذف جميع الرولات بعد تنفيذ امر العفو
        jail_role = discord.utils.get(ctx.guild.roles, name="Jail")
        if jail_role:
            await member.remove_roles(jail_role, reason="Pardon from jail")

    except Exception as e:
        await ctx.message.reply(f"⚠️ An error occurred while executing the command: {str(e)}")
        logging.error(f"Error in 'عفو' command: {str(e)}")  # تسجيل الخطأ في سجل الأخطاء


bot.run(os.environ['B'])
