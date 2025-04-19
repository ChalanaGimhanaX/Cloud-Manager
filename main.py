import discord
import asyncio
import os
import datetime
import sys
import importlib
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from utils.db import Database
from utils.api_manager import APIManager
from utils.logger import setup_logger

# Load environment variables
load_dotenv()
logger = setup_logger("bot")

# Bot configuration
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Initialize database connection
db = Database()
api_manager = APIManager(db)

# Store loaded commands per guild
GUILD_COMMANDS = {}

async def load_guild_commands(guild_id):
    """Load commands for a specific guild based on their server configurations"""
    try:
        # Clear existing commands for this guild
        if guild_id in GUILD_COMMANDS:
            for cmd in GUILD_COMMANDS[guild_id]:
                bot.tree.remove_command(cmd.name, guild=discord.Object(id=guild_id))
        
        # Get server configurations for this guild
        servers = await db.get_servers_for_guild(guild_id)
        if not servers:
            logger.warning(f"No servers configured for guild {guild_id}")
            return
        
        # Dynamic command modules to load based on permissions
        command_modules = {
            'create': 'commands.create',
            'update': 'commands.update',
            'delete': 'commands.delete', 
            'config': 'commands.config',
            'usage': 'commands.usage',
            'servers': 'commands.servers',
            'admin': 'commands.admin'
        }
        
        # Load command modules for this guild
        loaded_commands = []
        for cmd_name, module_path in command_modules.items():
            try:
                # Import or reload the module
                if module_path in sys.modules:
                    module = importlib.reload(sys.modules[module_path])
                else:
                    module = importlib.import_module(module_path)
                
                # Initialize the command with guild-specific context
                if hasattr(module, 'setup'):
                    cmd = await module.setup(bot, db, api_manager, guild_id, servers)
                    if cmd:
                        loaded_commands.append(cmd)
                        logger.info(f"Loaded {cmd_name} command for guild {guild_id}")
            except Exception as e:
                logger.error(f"Failed to load {cmd_name} for guild {guild_id}: {str(e)}")
        
        # Store loaded commands for this guild
        GUILD_COMMANDS[guild_id] = loaded_commands
        
        # Sync the command tree for this guild
        await bot.tree.sync(guild=discord.Object(id=guild_id))
        logger.info(f"Synced commands for guild {guild_id}")
    except Exception as e:
        logger.error(f"Failed to load commands for guild {guild_id}: {str(e)}")

@bot.event
async def on_guild_join(guild):
    """Initialize bot when it joins a new guild"""
    logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
    # Set up the guild in the database
    await db.add_guild(guild.id, guild.name)
    # Setup default roles if needed
    await setup_default_roles(guild)

@bot.event
async def on_ready():
    """Initialize bot when it starts up"""
    try:
        logger.info(f"Bot connected as {bot.user}")
        
        # Print dashboard URL to console
        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:5000")
        print("\n" + "=" * 50)
        print(f"🌐 Dashboard URL: {dashboard_url}")
        print("=" * 50 + "\n")
        
        # Initialize database tables if they don't exist
        await db.initialize()
        
        # Load commands for each guild the bot is in
        for guild in bot.guilds:
            logger.info(f"Loading commands for {guild.name} (ID: {guild.id})")
            await db.add_guild(guild.id, guild.name)  # Ensure guild is in database
            await load_guild_commands(guild.id)
        
        # Start status update task
        update_status_task.start()
        logger.info("Bot is fully ready!")
    except Exception as e:
        logger.error(f"Error in on_ready: {str(e)}")

@tasks.loop(minutes=10)
async def update_status_task():
    """Update the bot status periodically"""
    try:
        guild_count = len(bot.guilds)
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name=f"{guild_count} servers | /help"
            ),
            status=discord.Status.online
        )
    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")

async def setup_default_roles(guild):
    """Create default roles for a new guild"""
    try:
        # Check if "Server Admin" role exists, create if not
        admin_role = discord.utils.get(guild.roles, name="Server Admin")
        if not admin_role:
            admin_role = await guild.create_role(
                name="Server Admin",
                permissions=discord.Permissions(administrator=True),
                color=discord.Color.blue()
            )
            logger.info(f"Created Server Admin role in {guild.name}")
        
        # Check if "Config Manager" role exists, create if not
        manager_role = discord.utils.get(guild.roles, name="Config Manager")
        if not manager_role:
            manager_role = await guild.create_role(
                name="Config Manager",
                permissions=discord.Permissions(
                    manage_roles=True,
                    manage_messages=True
                ),
                color=discord.Color.green()
            )
            logger.info(f"Created Config Manager role in {guild.name}")
        
        # Save role IDs to database
        await db.update_guild_roles(guild.id, admin_role.id, manager_role.id)
    except Exception as e:
        logger.error(f"Error setting up roles for {guild.name}: {str(e)}")

@bot.tree.command(name="reload", description="Reload commands for this server")
@app_commands.default_permissions(administrator=True)
async def reload_commands(interaction: discord.Interaction):
    """Reload all commands for the current guild"""
    await interaction.response.defer(ephemeral=True)
    try:
        guild_id = interaction.guild_id
        await load_guild_commands(guild_id)
        await interaction.followup.send("✅ Commands reloaded successfully!")
    except Exception as e:
        logger.error(f"Error reloading commands: {str(e)}")
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="dashboard", description="Get a link to the management dashboard")
async def dashboard_link(interaction: discord.Interaction):
    """Provide a link to the web dashboard"""
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
    
    embed = discord.Embed(
        title="🌐 Cloud Manager Dashboard",
        description="Access your configuration management dashboard by clicking the link below.",
        color=0x5865F2
    )
    embed.add_field(
        name="Dashboard Link",
        value=f"[Click here to access the dashboard]({dashboard_url})",
        inline=False
    )
    embed.add_field(
        name="Instructions",
        value="1. Log in with your Discord account\n"
              "2. Manage your V2ray servers and configurations\n"
              "3. Monitor usage and client status",
        inline=False
    )
    embed.set_footer(text="You will need to authorize with your Discord account")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))
