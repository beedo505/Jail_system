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

# أمر سجن: -سجن @username reason
@bot.command(aliases = ['كوي' , 'عدس' , 'ارمي' , 'اشخط' , 'احبس'])
async def سجن(ctx, member: discord.Member = None, time_unit: str = "1d", *, reason = "No reason"):
    try:
    
        if not member:
            await ctx.reply("❌ You must mention a valid member.")
            return
    
        if isinstance(member, discord.Role) or isinstance(member, discord.TextChannel) or member == bot.user:
            await ctx.reply("❌ Please mention a member, not a role, channel, or the bot.")
            return

        # Validate the time format
        time_match = re.match(r'(\d+)([mhd])', time)
        if not time_match:
            await ctx.reply("❌ Invalid time format. Please use: [number][m/h/d] (e.g., 1d, 10m, 2h).")
            return

        # Extract the time
        amount, unit = time_match.groups()
        amount = int(amount)

        # Convert the time to timedelta
        if unit == 'm':
            delta = timedelta(minutes=amount)
        elif unit == 'h':
            delta = timedelta(hours=amount)
        elif unit == 'd':
            delta = timedelta(days=amount)

        # Save the member's previous roles
        previous_roles = member.roles[1:]  # Exclude @everyone role

        # Create or get the "Jailed" role
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if not jail_role:
            # If the "Jailed" role doesn't exist, create it
            jail_role = await ctx.guild.create_role(name="Jailed", permissions=discord.Permissions(send_messages=False, read_messages=True))

        # Assign the jail role to the member
        await member.add_roles(jail_role)

        # Remove all other roles from the member
        await member.edit(roles=[jail_role])
        await ctx.reply(f"✅ {member.name} has been jailed for {time}.")

        # Wait for the specified time and then release the member
        await asyncio.sleep(delta.total_seconds())

        # Return the member's previous roles
        await member.edit(roles=[jail_role] + previous_roles)
        await ctx.reply(f"✅ {member.name} has been released after the specified duration.")

# أمر عفو
"""Release a member from jail"""
@bot.command()
async def عفو(ctx, member: discord.Member = None):
    try:
    
        if not member:
            await ctx.reply("❌ You must mention a valid member.")
            return

        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role and jail_role in member.roles:
            # Save the member's previous roles
            previous_roles = member.roles[1:]  # Exclude @everyone role

            # Remove the jail role
            await member.remove_roles(jail_role)
        
            # Return the member's previous roles
            await member.edit(roles=[jail_role] + previous_roles)
            await ctx.reply(f"✅ {member.name} has been released from jail.")
        else:
            await ctx.reply(f"❌ {member.name} is not in jail.")

        except Exception as e:
            await ctx.message.reply(f"⚠️ An error occurred while executing the command: {str(e)}")
            logging.error(f"Error in 'عفو' command: {str(e)}")  # تسجيل الخطأ في سجل الأخطاء
        
bot.run(os.environ['B'])
