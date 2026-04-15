import sys
import traceback
import os
import discord
from discord.ext import commands
from discord.ui import Button, View
import json
from datetime import datetime
import asyncio
import threading
import requests
import time
from flask import Flask

# Print debug info
print("=" * 50)
print("Starting bot...")
print(f"Python version: {sys.version}")
print("=" * 50)

# ========== SELF-PING SYSTEM (Keep Bot Alive) ==========
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_webserver():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def self_ping():
    """Pings itself every 4 minutes to stay awake"""
    while True:
        time.sleep(240)  # 4 minutes
        try:
            url = os.environ.get('BOT_URL', 'http://localhost:8080')
            requests.get(url, timeout=10)
            print(f"[{datetime.now()}] Self-ping successful")
        except Exception as e:
            print(f"[{datetime.now()}] Self-ping failed: {e}")

def start_keep_alive():
    """Starts both the webserver and self-ping"""
    web_thread = threading.Thread(target=run_webserver, daemon=True)
    web_thread.start()
    
    ping_thread = threading.Thread(target=self_ping, daemon=True)
    ping_thread.start()
    
    print("✅ Keep-alive system started!")

# ========== BOT SETUP ==========
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Store active tickets
active_tickets = {}

# Store closed tickets channel IDs for viewing
closed_tickets = {}

# Config file
CONFIG_FILE = 'config.json'

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Warning: Could not load config.json: {e}")
        return {}

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Warning: Could not save config.json: {e}")

config = load_config()

class TicketModal(discord.ui.Modal, title="Create Ticket"):
    def __init__(self, ticket_type):
        super().__init__()
        self.ticket_type = ticket_type
        
    reason = discord.ui.TextInput(
        label="What do you need help with?",
        placeholder="Describe your issue or question...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket_channel(interaction, self.ticket_type, self.reason.value)

async def create_ticket_channel(interaction, ticket_type, reason):
    guild = interaction.guild
    member = interaction.user
    
    # Check for existing ticket
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.name.startswith(f"ticket-{member.id}"):
            await interaction.response.send_message("❌ You already have an open ticket! Close it first.", ephemeral=True)
            return
    
    # Get category
    category_id = config.get('ticket_category')
    category = discord.utils.get(guild.categories, id=category_id) if category_id else None
    
    # Get support role
    support_role_id = config.get('support_role')
    support_role = guild.get_role(support_role_id) if support_role_id else None
    
    # Get view role (for viewing closed tickets)
    view_role_id = config.get('view_role')
    view_role = guild.get_role(view_role_id) if view_role_id else None
    
    # Permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    
    if view_role:
        overwrites[view_role] = discord.PermissionOverwrite(view_channel=False)  # Can't view open tickets, only closed ones
    
    # Create channel name based on ticket type
    prefix = "purchase" if ticket_type == "Purchase" else "support"
    channel_name = f"🎫┃{prefix}-{member.name}".lower().replace(" ", "-")[:32]
    
    # Create channel
    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=f"Ticket Type: {ticket_type} | User: {member.name} | Created: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Status: Open"
    )
    
    # Store ticket info
    active_tickets[channel.id] = {
        'user_id': member.id,
        'type': ticket_type,
        'reason': reason,
        'created_at': datetime.now(),
        'support_role_id': support_role_id,
        'view_role_id': view_role_id,
        'category_id': category_id
    }
    
    # Send welcome message in ticket
    embed = discord.Embed(
        title=f"🎫 {ticket_type} Ticket Created",
        description=f"**User:** {member.mention}\n**Reason:** {reason}",
        color=0x00ff00 if ticket_type == "Purchase" else 0x00aaff
    )
    embed.set_footer(text="Croxy X Cheat Support | Type !close to close this ticket")
    
    view = CloseTicketView()
    await channel.send(embed=embed, view=view)
    
    await interaction.response.send_message(f"✅ Ticket created! Check {channel.mention}", ephemeral=True)

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ Closing ticket in 5 seconds...", ephemeral=False)
        
        # Create transcript
        transcript = []
        async for message in interaction.channel.history(limit=200, oldest_first=True):
            transcript.append(f"[{message.created_at}] {message.author.name}: {message.content}")
        
        # Save transcript
        transcript_text = "\n".join(transcript)
        transcript_filename = f"transcript_{interaction.channel.id}.txt"
        with open(transcript_filename, "w", encoding="utf-8") as f:
            f.write(transcript_text)
        
        # Get ticket info before closing
        ticket_info = active_tickets.get(interaction.channel.id, {})
        support_role_id = ticket_info.get('support_role_id')
        view_role_id = ticket_info.get('view_role_id')
        category_id = ticket_info.get('category_id')
        
        await asyncio.sleep(5)
        
        # Make channel visible to view_role but keep it
        if view_role_id:
            view_role = interaction.guild.get_role(view_role_id)
            if view_role:
                await interaction.channel.set_permissions(view_role, view_channel=True, send_messages=False, read_message_history=True)
        
        # Keep support role but remove write permissions
        if support_role_id:
            support_role = interaction.guild.get_role(support_role_id)
            if support_role:
                await interaction.channel.set_permissions(support_role, view_channel=True, send_messages=False, read_message_history=True)
        
        # Remove user's write permissions (they can still view)
        user = interaction.user
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=False, read_message_history=True)
        
        # Update channel name to show it's closed
        new_name = interaction.channel.name.replace("🎫┃", "🔒┃closed-")
        await interaction.channel.edit(name=new_name, topic=f"CLOSED: {interaction.channel.topic} | Closed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Send final message before locking
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"This ticket has been closed by {user.mention}\n\n**Support staff can still view this ticket**\nTo reopen, use `!reopen`",
            color=0xff0000
        )
        await interaction.channel.send(embed=embed)
        
        # Store in closed tickets
        closed_tickets[interaction.channel.id] = {
            'closed_at': datetime.now(),
            'closed_by': user.id,
            'transcript': transcript_filename
        }
        
        # Try to send transcript to user
        try:
            with open(transcript_filename, "r", encoding="utf-8") as f:
                await user.send(f"📄 Your ticket transcript for {interaction.channel.name}\n", file=discord.File(f))
        except:
            pass

class MainView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🛒 PURCHASE", style=discord.ButtonStyle.success, emoji="💰", custom_id="purchase_btn")
    async def purchase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TicketModal("Purchase")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🎫 SUPPORT", style=discord.ButtonStyle.primary, emoji="✨", custom_id="support_btn")
    async def support_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TicketModal("Support")
        await interaction.response.send_modal(modal)

@bot.event
async def on_ready():
    print(f"✅ Bot is online! Logged in as {bot.user}")
    print(f"📡 Connected to {len(bot.guilds)} servers")
    
    # Add persistent views
    bot.add_view(MainView())
    bot.add_view(CloseTicketView())
    
    # Set status
    await bot.change_presence(activity=discord.Game(name="Croxy X Cheat | !ticket"))

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Setup the ticket system (Admin only)"""
    embed = discord.Embed(
        title="🎫 **CROXY X CHEAT SUPPORT** 🎫",
        description="""
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        ## ✨ **Best Premium FF Pannels** ✨
        
        Welcome to the official **Croxy X Cheat** support center!
        
        ### 🚀 **Why Choose Us?**
        • 🎯 Main id Safe Cheats
        • ⚡ 24/7 Fast Support
        • 🔄 Lifetime Updates
        • 🛡️ Anti-Ban Protection
        • 🛡️ Second id brutual Rank Push Pannel 
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        ### 💎 **Select an Option Below:**
        
        > **🛒 PURCHASE** - Get instant access to our cheats
        > **🎫 SUPPORT** - Need help? Open a ticket
        
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """,
        color=0x9b59b6
    )
    
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
    embed.set_footer(text="Croxy X Cheat | Premium Gaming Solutions", icon_url=bot.user.avatar.url if bot.user.avatar else None)
    
    view = MainView()
    await ctx.send(embed=embed, view=view)
    await ctx.send("✅ Ticket panel setup complete!", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def set_category(ctx, category_id: int):
    """Set ticket category (Admin only)"""
    config['ticket_category'] = category_id
    save_config(config)
    await ctx.send(f"✅ Ticket category set to <#{category_id}>")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_support_role(ctx, role_id: int):
    """Set support role (Admin only)"""
    config['support_role'] = role_id
    save_config(config)
    role = ctx.guild.get_role(role_id)
    await ctx.send(f"✅ Support role set to {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_view_role(ctx, role_id: int):
    """Set role that can view closed tickets (Admin only)"""
    config['view_role'] = role_id
    save_config(config)
    role = ctx.guild.get_role(role_id)
    await ctx.send(f"✅ View role set to {role.mention} - This role can view closed tickets")

@bot.command()
async def close(ctx):
    """Close current ticket"""
    if ctx.channel.name.startswith(("🎫┃purchase-", "🎫┃support-")):
        view = CloseTicketView()
        await ctx.send("🔒 Are you sure you want to close this ticket?", view=view)
    else:
        await ctx.send("❌ This command can only be used in ticket channels!")

@bot.command()
async def reopen(ctx):
    """Reopen a closed ticket (Support role only)"""
    if not ctx.channel.name.startswith(("🔒┃closed-purchase-", "🔒┃closed-support-")):
        await ctx.send("❌ This command can only be used in closed ticket channels!")
        return
    
    # Check if user has support role
    support_role_id = config.get('support_role')
    if support_role_id:
        support_role = ctx.guild.get_role(support_role_id)
        if support_role not in ctx.author.roles:
            await ctx.send("❌ Only support staff can reopen tickets!")
            return
    
    # Reopen the ticket
    new_name = ctx.channel.name.replace("🔒┃closed-", "🎫┃")
    await ctx.channel.edit(name=new_name, topic=ctx.channel.topic.replace("CLOSED:", "REOPENED:"))
    
    # Update permissions
    support_role_id = config.get('support_role')
    if support_role_id:
        support_role = ctx.guild.get_role(support_role_id)
        if support_role:
            await ctx.channel.set_permissions(support_role, send_messages=True, read_message_history=True)
    
    # Get original user from channel name
    user_name = ctx.channel.name.split("-")[-1]
    # Find member and give them permissions back
    for member in ctx.guild.members:
        if member.name.lower() == user_name or user_name in member.name.lower():
            await ctx.channel.set_permissions(member, send_messages=True, read_message_history=True)
            break
    
    embed = discord.Embed(
        title="🔄 Ticket Reopened",
        description=f"This ticket has been reopened by {ctx.author.mention}",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
async def adduser(ctx, member: discord.Member):
    """Add user to ticket"""
    if ctx.author.guild_permissions.administrator or ctx.channel.name.startswith(("🎫┃purchase-", "🎫┃support-")):
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.send(f"✅ Added {member.mention} to this ticket")

@bot.command()
async def removeuser(ctx, member: discord.Member):
    """Remove user from ticket"""
    if ctx.author.guild_permissions.administrator or ctx.channel.name.startswith(("🎫┃purchase-", "🎫┃support-")):
        await ctx.channel.set_permissions(member, view_channel=False)
        await ctx.send(f"✅ Removed {member.mention} from this ticket")

@bot.command()
async def tickets(ctx):
    """List all open and closed tickets (Admin only)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ This command is for administrators only!")
        return
    
    open_ticket_list = []
    closed_ticket_list = []
    
    for channel in ctx.guild.channels:
        if isinstance(channel, discord.TextChannel):
            if channel.name.startswith("🎫┃"):
                open_ticket_list.append(f"• {channel.mention} - {channel.topic}")
            elif channel.name.startswith("🔒┃closed-"):
                closed_ticket_list.append(f"• {channel.mention} - {channel.topic}")
    
    embed = discord.Embed(title="📋 Ticket List", color=0x9b59b6)
    
    if open_ticket_list:
        embed.add_field(name="🟢 Open Tickets", value="\n".join(open_ticket_list) or "None", inline=False)
    else:
        embed.add_field(name="🟢 Open Tickets", value="No open tickets", inline=False)
    
    if closed_ticket_list:
        embed.add_field(name="🔒 Closed Tickets", value="\n".join(closed_ticket_list) or "None", inline=False)
    else:
        embed.add_field(name="🔒 Closed Tickets", value="No closed tickets", inline=False)
    
    await ctx.send(embed=embed)

# ========== RUN BOT ==========
if __name__ == "__main__":
    try:
        # Get token from environment variable (for Render)
        TOKEN = os.environ.get('DISCORD_TOKEN')
        
        if not TOKEN:
            print("❌ ERROR: DISCORD_TOKEN environment variable not set!")
            print("Please add it in Render Dashboard -> Environment tab")
            exit(1)
        
        print(f"✅ Token found (length: {len(TOKEN)})")
        
        # START THE KEEP-ALIVE SYSTEM
        print("Starting keep-alive system...")
        start_keep_alive()
        
        print("Starting Discord bot...")
        # Run your bot
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
