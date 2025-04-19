import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio
import json
import uuid
from datetime import datetime, timedelta

async def setup(bot, db, api_manager, guild_id, servers):
    """Set up the create command for a specific guild"""
    
    # Get available servers for autocomplete
    server_choices = []
    for server in servers:
        server_choices.append(app_commands.Choice(name=server["server_name"], value=server["server_id"]))
    
    # Get available inbounds for each server
    inbounds_by_server = {}
    for server in servers:
        server_id = server["server_id"]
        inbounds = await api_manager.get_inbounds(server_id)
        inbounds_by_server[server_id] = inbounds
    
    async def server_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for server selection"""
        return [
            choice for choice in server_choices 
            if current.lower() in choice.name.lower()
        ][:25]
    
    async def inbound_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for inbound selection"""
        # Get the selected server from the interaction options
        server_id = None
        for option in interaction.data.get("options", []):
            if option.get("name") == "server":
                server_id = option.get("value")
                break
        
        if not server_id or server_id not in inbounds_by_server:
            return []
        
        inbounds = inbounds_by_server[server_id]
        choices = []
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            remark = inbound.get("remark", "Unnamed")
            protocol = inbound.get("protocol", "unknown")
            port = inbound.get("port", "?")
            
            # Create a descriptive name for the inbound
            name = f"{remark} ({protocol.upper()}:{port})"
            
            if current.lower() in name.lower() or current.lower() in str(inbound_id):
                choices.append(app_commands.Choice(name=name, value=str(inbound_id)))
        
        return choices[:25]
    
    # Create the command
    @bot.tree.command(
        name="create",
        description="Create a new V2ray configuration",
        guild=discord.Object(id=guild_id)
    )
    @app_commands.describe(
        server="Select the server to create the configuration on",
        inbound="Select the inbound to use",
        user="Mention the user to create configuration for (admin only, leave empty for self)",
        days="Duration in days (default: 30)",
        data_limit="Data limit in GB (0 for unlimited)"
    )
    @app_commands.autocomplete(server=server_autocomplete, inbound=inbound_autocomplete)
    async def create_command(
        interaction: discord.Interaction, 
        server: str,
        inbound: str,
        user: Optional[discord.Member] = None,
        days: int = 30,
        data_limit: int = 0
    ):
        await interaction.response.defer(ephemeral=True)
        
        # If user is specified, check admin permissions
        if user and user.id != interaction.user.id:
            guild = interaction.guild
            admin_role_id = None
            
            # Get admin role ID from database
            async with await db._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT admin_role_id FROM guilds WHERE guild_id = ?", 
                    (str(guild_id),)
                )
                row = await cursor.fetchone()
                if row:
                    admin_role_id = row[0]
            
            is_admin = admin_role_id and any(role.id == int(admin_role_id) for role in interaction.user.roles)
            if not is_admin:
                await interaction.followup.send(
                    "❌ You don't have permission to create configurations for other users.", 
                    ephemeral=True
                )
                return
        else:
            # If no user is specified, use the interaction user
            user = interaction.user
        
        # Validate inputs
        if days < 1 or days > 365:
            await interaction.followup.send(
                "❌ Duration must be between 1 and 365 days.",
                ephemeral=True
            )
            return
            
        if data_limit < 0 or data_limit > 10000:
            await interaction.followup.send(
                "❌ Data limit must be between 0 and 10000 GB.",
                ephemeral=True
            )
            return
        
        try:
            # Create user record if it doesn't exist
            user_id = await db.add_user(
                discord_id=str(user.id),
                guild_id=str(guild_id),
                username=user.name
            )
            
            if not user_id:
                await interaction.followup.send(
                    "❌ Failed to create or find user record.",
                    ephemeral=True
                )
                return
            
            # Generate client email (username_discordid)
            client_email = f"{user.name}_{user.id}"
            
            # Create client on V2ray server
            client = await api_manager.create_client(
                server_id=server,
                inbound_id=int(inbound),
                email=client_email,
                expiry_days=days,
                data_limit_gb=data_limit
            )
            
            if not client:
                await interaction.followup.send(
                    "❌ Failed to create configuration on the server.",
                    ephemeral=True
                )
                return
            
            # Record configuration in database
            config_id = await db.add_config(
                server_id=server,
                user_id=user_id,
                inbound_id=int(inbound),
                client_uuid=client["uuid"],
                client_email=client_email,
                expiry_days=days,
                data_limit_gb=data_limit
            )
            
            if not config_id:
                # Rollback - delete client from server if database insertion fails
                await api_manager.delete_client(server, int(inbound), client["uuid"])
                await interaction.followup.send(
                    "❌ Failed to record configuration in database.",
                    ephemeral=True
                )
                return
            
            # Generate VLESS link
            vless_link = await api_manager.generate_client_link(
                server_id=server,
                inbound_id=int(inbound),
                client_uuid=client["uuid"]
            )
            
            # Get server name for display
            server_name = next((s["server_name"] for s in servers if s["server_id"] == server), "Unknown Server")
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Configuration Created Successfully",
                description="Your V2ray configuration has been created. Details below:",
                color=0x5865F2
            )
            
            embed.add_field(
                name="👤 User",
                value=f"{user.mention}",
                inline=True
            )
            
            embed.add_field(
                name="🖥️ Server",
                value=f"{server_name}",
                inline=True
            )
            
            embed.add_field(
                name="⏳ Duration",
                value=f"{days} days",
                inline=True
            )
            
            embed.add_field(
                name="📊 Data Limit",
                value=f"{'Unlimited' if data_limit == 0 else f'{data_limit} GB'}",
                inline=True
            )
            
            embed.add_field(
                name="📅 Expiry Date",
                value=f"<t:{int((datetime.now() + timedelta(days=days)).timestamp())}:F>",
                inline=True
            )
            
            embed.add_field(
                name="🔐 Configuration Link",
                value=f"```\n{vless_link if vless_link else 'Link generation failed'}\n```",
                inline=False
            )
            
            embed.set_footer(text=f"Config ID: {config_id}")
            
            # Add user's avatar as thumbnail
            embed.set_thumbnail(url=user.display_avatar.url)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    # Return the command so it can be tracked
    return create_command
