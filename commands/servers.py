import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio

async def setup(bot, db, api_manager, guild_id, servers):
    """Set up the servers command for a specific guild"""
    
    # Create the group
    servers_group = app_commands.Group(
        name="servers",
        description="Manage V2ray servers",
        guild=discord.Object(id=guild_id)
    )
    
    # Function to check admin permissions
    async def check_admin(interaction: discord.Interaction):
        """Check if the user has admin role"""
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
            await interaction.response.send_message("You don't have permission to manage servers.", ephemeral=True)
            return False
        return True
    
    @servers_group.command(name="add", description="Add a new V2ray server")
    @app_commands.describe(
        server_name="Name for the server",
        api_url="API URL (e.g., http://hostname:port)",
        api_user="API username",
        api_password="API password"
    )
    async def add_server(interaction: discord.Interaction, server_name: str, api_url: str, api_user: str, api_password: str):
        """Add a new server to manage"""
        await interaction.response.defer(ephemeral=True)
        
        if not await check_admin(interaction):
            return
        
        try:
            # Test connection to the server
            session = await api_manager._ensure_login(None, None, api_url, api_user, api_password)
            if not session:
                await interaction.followup.send(f"❌ Failed to connect to server at {api_url}", ephemeral=True)
                return
            
            # Add server to database
            server_id = await db.add_server(
                guild_id=str(guild_id),
                server_name=server_name,
                api_url=api_url,
                api_user=api_user,
                api_password=api_password
            )
            
            if not server_id:
                await interaction.followup.send("❌ Failed to add server to database", ephemeral=True)
                return
            
            # Reload commands to include the new server
            await bot.load_guild_commands(guild_id)
            
            embed = discord.Embed(
                title="✅ Server Added",
                description=f"Server **{server_name}** has been added successfully.",
                color=0x5865F2
            )
            embed.add_field(name="API URL", value=api_url, inline=False)
            embed.set_footer(text=f"Server ID: {server_id}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error adding server: {str(e)}", ephemeral=True)
    
    @servers_group.command(name="list", description="List all configured servers")
    async def list_servers(interaction: discord.Interaction):
        """List all servers for this guild"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get all servers for this guild
            servers = await db.get_servers_for_guild(str(guild_id))
            
            if not servers:
                await interaction.followup.send("No servers configured for this Discord server.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🖥️ Configured Servers",
                description=f"This Discord server has {len(servers)} V2ray server(s) configured.",
                color=0x5865F2
            )
            
            for server in servers:
                status = "✅ Enabled" if server["is_enabled"] else "❌ Disabled"
                embed.add_field(
                    name=f"{server['server_name']} ({status})",
                    value=f"API URL: {server['api_url']}\nAdded: {server['created_at']}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error listing servers: {str(e)}", ephemeral=True)
    
    @servers_group.command(name="remove", description="Remove a server configuration")
    @app_commands.describe(server_name="Name of the server to remove")
    async def remove_server(interaction: discord.Interaction, server_name: str):
        """Remove a server from the configuration"""
        await interaction.response.defer(ephemeral=True)
        
        if not await check_admin(interaction):
            return
        
        try:
            # Get all servers for this guild to find the one to remove
            servers = await db.get_servers_for_guild(str(guild_id))
            
            server_to_remove = None
            for server in servers:
                if server["server_name"].lower() == server_name.lower():
                    server_to_remove = server
                    break
            
            if not server_to_remove:
                await interaction.followup.send(f"❌ No server named '{server_name}' found.", ephemeral=True)
                return
            
            # Confirmation view
            class ConfirmView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60)
                    self.confirmed = False
                
                @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.danger)
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                        return
                    
                    self.confirmed = True
                    await button_interaction.response.defer()
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if button_interaction.user != interaction.user:
                        await button_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                        return
                    
                    await button_interaction.response.defer()
                    self.stop()
            
            view = ConfirmView()
            confirm_embed = discord.Embed(
                title="⚠️ Confirm Server Removal",
                description=f"Are you sure you want to remove **{server_to_remove['server_name']}**?\n\nThis will delete all related configuration data and is irreversible.",
                color=0xFF0000
            )
            
            await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)
            
            # Wait for confirmation
            await view.wait()
            
            if not view.confirmed:
                await interaction.followup.send("Server removal cancelled.", ephemeral=True)
                return
            
            # Delete the server from database
            success = await db.delete_server(server_to_remove["server_id"])
            
            if success:
                # Reload commands to remove the deleted server
                await bot.load_guild_commands(guild_id)
                
                await interaction.followup.send(
                    f"✅ Server **{server_to_remove['server_name']}** has been removed successfully.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to remove server **{server_to_remove['server_name']}**.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(f"❌ Error removing server: {str(e)}", ephemeral=True)
    
    @servers_group.command(name="test", description="Test connection to a server")
    @app_commands.describe(server_name="Name of the server to test")
    async def test_server(interaction: discord.Interaction, server_name: str):
        """Test connection to a specific server"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get all servers for this guild to find the one to test
            servers = await db.get_servers_for_guild(str(guild_id))
            
            server_to_test = None
            for server in servers:
                if server["server_name"].lower() == server_name.lower():
                    server_to_test = server
                    break
            
            if not server_to_test:
                await interaction.followup.send(f"❌ No server named '{server_name}' found.", ephemeral=True)
                return
            
            # Test connection to server
            session = await api_manager.get_session(server_to_test["server_id"])
            if not session:
                await interaction.followup.send(f"❌ Failed to connect to server **{server_name}**", ephemeral=True)
                return
            
            # Get basic server info to verify connection
            inbounds = await api_manager.get_inbounds(server_to_test["server_id"])
            inbound_count = len(inbounds) if inbounds else 0
            
            embed = discord.Embed(
                title="✅ Connection Successful",
                description=f"Successfully connected to **{server_name}**.",
                color=0x00FF00
            )
            
            embed.add_field(
                name="Server Information",
                value=f"API URL: {server_to_test['api_url']}\nInbounds: {inbound_count}",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error testing server connection: {str(e)}", ephemeral=True)
    
    # Register the server commands
    bot.tree.add_command(servers_group, guild=discord.Object(id=guild_id))
    
    return servers_group
