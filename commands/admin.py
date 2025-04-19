import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio
import os
import sys
from datetime import datetime, timedelta

async def setup(bot, db, api_manager, guild_id, servers):
    """Set up admin commands for a specific guild"""
    
    # Create the group
    admin_group = app_commands.Group(
        name="admin", 
        description="Administrative commands",
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
            await interaction.response.send_message("You don't have permission to use admin commands.", ephemeral=True)
            return False
        return True
    
    @admin_group.command(name="roles", description="Set up admin and manager roles")
    @app_commands.describe(
        admin_role="Admin role that has full access to all commands",
        manager_role="Manager role that can create and update configurations"
    )
    async def setup_roles(
        interaction: discord.Interaction, 
        admin_role: discord.Role, 
        manager_role: discord.Role
    ):
        """Set up admin and manager roles for the bot"""
        await interaction.response.defer(ephemeral=True)
        
        # Only server admins can set roles
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need to be a server administrator to use this command.",
                ephemeral=True
            )
            return
        
        try:
            # Update roles in database
            success = await db.update_guild_roles(
                guild_id=str(guild_id),
                admin_role_id=str(admin_role.id),
                manager_role_id=str(manager_role.id)
            )
            
            if success:
                embed = discord.Embed(
                    title="✅ Roles Configured",
                    description="Bot roles have been successfully configured.",
                    color=0x5865F2
                )
                
                embed.add_field(
                    name="Admin Role",
                    value=f"{admin_role.mention}\nMembers with this role have full access to all commands.",
                    inline=False
                )
                
                embed.add_field(
                    name="Manager Role",
                    value=f"{manager_role.mention}\nMembers with this role can create and update user configurations.",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Failed to update roles. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error setting up roles: {str(e)}",
                ephemeral=True
            )
    
    @admin_group.command(name="stats", description="Show server usage statistics")
    async def server_stats(interaction: discord.Interaction):
        """Display usage statistics for all servers"""
        await interaction.response.defer(ephemeral=True)
        
        if not await check_admin(interaction):
            return
            
        try:
            embed = discord.Embed(
                title="📊 Server Usage Statistics",
                description="Overview of usage across all configured servers.",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            # Get server list
            all_servers = await db.get_servers_for_guild(str(guild_id))
            
            if not all_servers:
                await interaction.followup.send("No servers configured for this Discord server.", ephemeral=True)
                return
            
            # Process each server
            for server in all_servers:
                server_id = server["server_id"]
                server_name = server["server_name"]
                
                # Get all inbounds for this server
                inbounds = await api_manager.get_inbounds(server_id)
                if not inbounds:
                    embed.add_field(
                        name=f"❌ {server_name}",
                        value="Failed to fetch data or no inbounds found",
                        inline=False
                    )
                    continue
                
                # Collect statistics
                active_users = 0
                expired_users = 0
                total_traffic = 0
                
                for inbound in inbounds:
                    settings = inbound.get('settings', '{}')
                    if isinstance(settings, str):
                        import json
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    
                    clients = settings.get('clients', [])
                    for client in clients:
                        # Check if client is expired
                        expiry_time = client.get('expiryTime', 0)
                        if expiry_time > 0:
                            expiry_date = datetime.fromtimestamp(expiry_time / 1000)
                            if expiry_date < datetime.now():
                                expired_users += 1
                            else:
                                active_users += 1
                        else:
                            active_users += 1  # No expiry = active
                        
                        # Add traffic (if available)
                        email = client.get('email', '')
                        if email:
                            traffic_data = await api_manager.get_client_traffic(server_id, email)
                            if traffic_data:
                                total_traffic += traffic_data.get('obj', {}).get('total', 0)
                
                # Convert total_traffic from bytes to GB
                total_traffic_gb = total_traffic / (1024**3)
                
                # Add server stats to embed
                server_stats = (
                    f"**Active Users:** {active_users}\n"
                    f"**Expired Users:** {expired_users}\n"
                    f"**Total Traffic:** {total_traffic_gb:.2f} GB\n"
                    f"**Inbounds:** {len(inbounds)}"
                )
                
                embed.add_field(
                    name=f"🖥️ {server_name}",
                    value=server_stats,
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error fetching server statistics: {str(e)}",
                ephemeral=True
            )
    
    @admin_group.command(name="find", description="Find a user's configuration")
    @app_commands.describe(
        search_term="Username or email to search for",
        server="Specific server to search (optional)"
    )
    async def find_user(
        interaction: discord.Interaction, 
        search_term: str,
        server: Optional[str] = None
    ):
        """Find a user's configuration by username or email"""
        await interaction.response.defer(ephemeral=True)
        
        if not await check_admin(interaction):
            return
            
        try:
            results = []
            servers_to_search = []
            
            if server:
                # Find the specific server by name
                all_servers = await db.get_servers_for_guild(str(guild_id))
                for srv in all_servers:
                    if srv["server_name"].lower() == server.lower():
                        servers_to_search.append(srv)
                        break
                
                if not servers_to_search:
                    await interaction.followup.send(f"❌ Server '{server}' not found.", ephemeral=True)
                    return
            else:
                # Search all servers
                servers_to_search = await db.get_servers_for_guild(str(guild_id))
            
            for server in servers_to_search:
                server_id = server["server_id"]
                server_name = server["server_name"]
                
                # Get all inbounds for this server
                inbounds = await api_manager.get_inbounds(server_id)
                if not inbounds:
                    continue
                
                for inbound in inbounds:
                    inbound_id = inbound.get('id')
                    settings = inbound.get('settings', '{}')
                    if isinstance(settings, str):
                        import json
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    
                    clients = settings.get('clients', [])
                    
                    for client in clients:
                        email = client.get('email', '')
                        
                        # Check if the client matches the search term
                        if search_term.lower() in email.lower():
                            # Get traffic data
                            traffic_data = await api_manager.get_client_traffic(server_id, email)
                            total_traffic = 0
                            if traffic_data and 'obj' in traffic_data:
                                total_traffic = traffic_data['obj'].get('total', 0) / (1024**3)  # Convert to GB
                            
                            # Get expiry info
                            expiry_time = client.get('expiryTime', 0)
                            expiry_str = "Never"
                            is_expired = False
                            
                            if expiry_time > 0:
                                expiry_date = datetime.fromtimestamp(expiry_time / 1000)
                                expiry_str = expiry_date.strftime('%Y-%m-%d')
                                is_expired = expiry_date < datetime.now()
                            
                            # Add to results
                            results.append({
                                'server_name': server_name,
                                'server_id': server_id,
                                'inbound_id': inbound_id,
                                'email': email,
                                'uuid': client.get('id', ''),
                                'expiry': expiry_str,
                                'is_expired': is_expired,
                                'traffic': total_traffic
                            })
            
            if not results:
                await interaction.followup.send(f"❌ No configurations found matching '{search_term}'.", ephemeral=True)
                return
            
            # Build response embed
            embed = discord.Embed(
                title=f"🔍 Search Results for '{search_term}'",
                description=f"Found {len(results)} matching configuration(s).",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            for i, result in enumerate(results[:10]):  # Limit to 10 results to avoid embed limits
                status = "❌ Expired" if result['is_expired'] else "✅ Active"
                value = (
                    f"**Server:** {result['server_name']}\n"
                    f"**Email:** {result['email']}\n"
                    f"**Expiry:** {result['expiry']} ({status})\n"
                    f"**Traffic:** {result['traffic']:.2f} GB\n"
                    f"**UUID:** {result['uuid']}"
                )
                
                embed.add_field(
                    name=f"Result {i+1}",
                    value=value,
                    inline=False
                )
            
            if len(results) > 10:
                embed.set_footer(text=f"Showing 10 of {len(results)} results")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error searching for configurations: {str(e)}",
                ephemeral=True
            )
    
    # Register the admin commands group
    bot.tree.add_command(admin_group, guild=discord.Object(id=guild_id))
    
    return admin_group
