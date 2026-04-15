import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import os
from datetime import datetime
import asyncio
import threading
import requests
import time
from flask import Flask

# ========== SELF-PING SYSTEM (Keep Bot Alive) ==========
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_webserver():
    app.run(host='0.0.0.0', port=8080)

def self_ping():
    """Pings itself every 4 minutes to stay awake"""
    while True:
        time.sleep(240)  # 4 minutes
        try:
            # Get the URL from environment or use localhost
            url = os.environ.get('BOT_URL', 'http://localhost:8080')
            requests.get(url, timeout=10)
            print(f"[{datetime.now()}] Self-ping successful")
        except Exception as e:
            print(f"[{datetime.now()}] Self-ping failed: {e}")

def start_keep_alive():
    """Starts both the webserver and self-ping"""
    # Start web server in background
    web_thread = threading.Thread(target=run_webserver, daemon=True)
    web_thread.start()
    
    # Start self-ping in background
    ping_thread = threading.Thread(target=self_ping, daemon=True)
    ping_thread.start()
    
    print("✅ Keep-alive system started!")

# ========== BOT SETUP ==========
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Store active tickets
active_tickets = {}

# Config file
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

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
    
    # Permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    
    # Create channel name based on ticket type
    prefix = "purchase" if ticket_type == "Purchase" else "support"
    channel_name = f"🎫┃{prefix}-{member.name}".lower().replace(" ", "-")[:32]
    
    # Create channel
    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=f"Ticket Type: {ticket_type} | User: {member.name} | Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    
    # Store ticket info
    active_tickets[channel.id] = {
        'user_id': member.id,
        'type': ticket_type,
        'reason': reason,
        'created_at': datetime.now()
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
        with open(f"transcript_{interaction.channel.id}.txt", "w", encoding="utf-8") as f:
            f.write(transcript_text)
        
        await asyncio.sleep(5)
        
        # Delete channel
        await interaction.channel.delete()
        
        # Try to send transcript to user (if DM available)
        try:
            user = interaction.user
            with open(f"transcript_{interaction.channel.id}.txt", "r", encoding="utf-8") as f:
                await user.send(f"📄 Your ticket transcript for {interaction.channel.name}\n", file=discord.File(f))
        except:
            pass
        
        # Clean up transcript file
        os.remove(f"transcript_{interaction.channel.id}.txt")

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
        • 🛡️Second id brutual Rank Push Pannel 
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
async def close(ctx):
    """Close current ticket"""
    if ctx.channel.name.startswith(("🎫┃purchase-", "🎫┃support-")):
        view = CloseTicketView()
        await ctx.send("🔒 Are you sure you want to close this ticket?", view=view)
    else:
        await ctx.send("❌ This command can only be used in ticket channels!")

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

# ========== RUN BOT ==========
if __name__ == "__main__":
    # IMPORTANT: Use environment variable for token!
    # Option 1: Use environment variable (RECOMMENDED for hosting)
    TOKEN = os.environ.get('DISCORD_TOKEN')
    
    # Option 2: If no environment variable, ask for input (for local testing)
    if not TOKEN:
        TOKEN = input("Enter your bot token: ")
    
    # START THE KEEP-ALIVE SYSTEM
    start_keep_alive()
    
    # Run your bot
    bot.run(TOKEN)