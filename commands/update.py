import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio
from datetime import datetime, timedelta

async def setup(bot, db, api_manager, guild_id, servers):
    """Set up the update command for a specific guild"""
    
    async def user_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for users with configurations"""
        # Get users who have configurations in this guild
        try:
            async with await db._get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT DISTINCT u.discord_id, u.username 
                    FROM users u
                    JOIN configs c ON u.user_id = c.user_id
                    WHERE u.guild_id = ?
                    """,
                    (str(guild_id),)
                )
                rows = await cursor.fetchall()
            
            choices = []
            for discord_id, username in rows:
                if current.lower() in username.lower() or current in discord_id:
                    # Try to get member object for the user
                    try:
                        member = await interaction.guild.fetch_member(int(discord_id))
                        display_name = member.display_name
                    except:
                        display_name = username
                    
                    choices.append(app_commands.Choice(
                        name=f"{display_name} ({discord_id})",
                        value=discord_id
                    ))
            
            return choices[:25]
        except Exception as e:
            print(f"Error in user_autocomplete: {e}")
            return []
    
    @bot.tree.command(
        name="update",
        description="Update or extend a V2ray configuration",
        guild=discord.Object(id=guild_id)
    )
    @app_commands.describe(
        user_id="Discord ID of the user whose configuration to update",
        days="Number of days to extend (1-365)",
        reset_data="Reset data usage counter (admin only)"
    )
    @app_commands.autocomplete(user_id=user_autocomplete)
    async def update_command(
        interaction: discord.Interaction,
        user_id: str,
        days: int = 30,
        reset_data: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        is_self = str(interaction.user.id) == user_id
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
        
        # Only admins can update other users or reset data
        if (not is_self and not is_admin) or (reset_data and not is_admin):
            await interaction.followup.send(
                "❌ You don't have permission to perform this action.", 
                ephemeral=True
            )
            return
        
        # Validate inputs
        if days < 1 or days > 365:
            await interaction.followup.send(
                "❌ Duration must be between 1 and 365 days.",
                ephemeral=True
            )
            return
        
        try:
            # Get user's configs
            configs = await db.get_configs_for_user(user_id, str(guild_id))
            
            if not configs:
                await interaction.followup.send(
                    f"❌ No configurations found for user ID {user_id}.",
                    ephemeral=True
                )
                return
            
            # Try to get member object for the user
            try:
                member = await interaction.guild.fetch_member(int(user_id))
                username = member.display_name
                avatar_url = member.display_avatar.url
            except:
                username = configs[0].get('client_email', '').split('_')[0]
                avatar_url = None
            
            # Process updates
            success_count = 0
            failed_count = 0
            
            for config in configs:
                server_id = config.get('server_id')
                inbound_id = config.get('inbound_id')
                client_uuid = config.get('client_uuid')
                config_id = config.get('config_id')
                
                # Update on server
                server_success = await api_manager.update_client(
                    server_id=server_id,
                    inbound_id=inbound_id,
                    client_uuid=client_uuid,
                    expiry_days=days
                )
                
                # Update in database
                db_success = await db.update_config_expiry(config_id, days)
                
                # Reset data usage if requested
                if reset_data and is_admin:
                    await db.update_config_usage(config_id, 0)
                
                if server_success and db_success:
                    success_count += 1
                else:
                    failed_count += 1
            
            # Send result
            result_embed = discord.Embed(
                title="🔄 Update Results",
                description=f"Configuration update for {'you' if is_self else username}",
                color=0x5865F2
            )
            
            result_embed.add_field(
                name="✅ Successful Updates",
                value=f"{success_count} configuration(s)",
                inline=True
            )
            
            if failed_count > 0:
                result_embed.add_field(
                    name="❌ Failed Updates",
                    value=f"{failed_count} configuration(s)",
                    inline=True
                )
            
            result_embed.add_field(
                name="⏳ Extended By",
                value=f"{days} days",
                inline=True
            )
            
            # Show new expiry date
            new_expiry = datetime.now() + timedelta(days=days)
            result_embed.add_field(
                name="📅 New Expiry",
                value=f"<t:{int(new_expiry.timestamp())}:F>",
                inline=True
            )
            
            if reset_data and is_admin:
                result_embed.add_field(
                    name="📊 Data Usage",
                    value="Reset to 0",
                    inline=True
                )
            
            if avatar_url:
                result_embed.set_thumbnail(url=avatar_url)
            
            await interaction.followup.send(embed=result_embed, ephemeral=True)
            
            # If it's an admin updating someone else, also send them a notification
            if not is_self and is_admin:
                try:
                    target_user = await bot.fetch_user(int(user_id))
                    if target_user:
                        notify_embed = discord.Embed(
                            title="🔔 Configuration Updated",
                            description=f"Your configuration has been updated by an administrator.",
                            color=0x5865F2
                        )
                        
                        notify_embed.add_field(
                            name="⏳ Extended By",
                            value=f"{days} days",
                            inline=True
                        )
                        
                        notify_embed.add_field(
                            name="📅 New Expiry",
                            value=f"<t:{int(new_expiry.timestamp())}:F>",
                            inline=True
                        )
                        
                        if reset_data:
                            notify_embed.add_field(
                                name="📊 Data Usage",
                                value="Reset to 0",
                                inline=True
                            )
                        
                        await target_user.send(embed=notify_embed)
                except:
                    # Don't fail if notification can't be sent
                    pass
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    # Return the command so it can be tracked
    return update_command
