import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio

async def setup(bot, db, api_manager, guild_id, servers):
    """Set up the delete command for a specific guild"""
    
    # Create the command
    @bot.tree.command(
        name="delete",
        description="Delete a V2ray configuration",
        guild=discord.Object(id=guild_id)
    )
    @app_commands.describe(
        user="Mention the user whose configuration to delete (admin only)"
    )
    async def delete_command(
        interaction: discord.Interaction, 
        user: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions - only admins can delete others' configs
        if user.id != interaction.user.id:
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
                    "❌ You don't have permission to delete configurations for other users.", 
                    ephemeral=True
                )
                return
        
        try:
            # Get user's configs
            configs = await db.get_configs_for_user(str(user.id), str(guild_id))
            
            if not configs:
                await interaction.followup.send(
                    f"❌ No configurations found for {user.mention}.",
                    ephemeral=True
                )
                return
            
            # Create confirmation view with buttons
            class ConfirmationView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60)
                    self.confirmed = False
                
                @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
                async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = True
                    await button_interaction.response.send_message(
                        "Deletion confirmed. Processing...", 
                        ephemeral=True
                    )
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await button_interaction.response.send_message(
                        "❌ Deletion cancelled.", 
                        ephemeral=True
                    )
                    self.stop()
            
            # Create confirmation embed
            embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete {len(configs)} configuration(s) for {user.mention}?",
                color=0xFF5555
            )
            
            # Add information about configs to be deleted
            for i, config in enumerate(configs[:5], 1):  # Limit to 5 to prevent embed from being too large
                server_name = config.get('server_name', 'Unknown Server')
                client_email = config.get('client_email', 'Unknown')
                
                embed.add_field(
                    name=f"Configuration {i}",
                    value=f"Server: {server_name}\nEmail: {client_email}",
                    inline=True
                )
            
            if len(configs) > 5:
                embed.add_field(
                    name=f"And {len(configs) - 5} more...",
                    value=f"Total: {len(configs)} configurations",
                    inline=False
                )
            
            # Send confirmation message with buttons
            view = ConfirmationView()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            # Wait for user interaction
            await view.wait()
            
            if not view.confirmed:
                return
            
            # Process deletions if confirmed
            success_count = 0
            failed_count = 0
            
            for config in configs:
                server_id = config.get('server_id')
                inbound_id = config.get('inbound_id')
                client_uuid = config.get('client_uuid')
                
                # Delete from server
                server_success = await api_manager.delete_client(
                    server_id=server_id,
                    inbound_id=inbound_id,
                    client_uuid=client_uuid
                )
                
                # Delete from database
                db_success = await db.delete_config(config.get('config_id'))
                
                if server_success and db_success:
                    success_count += 1
                else:
                    failed_count += 1
            
            # Send final result
            result_embed = discord.Embed(
                title="🗑️ Deletion Results",
                description=f"Processed deletions for {user.mention}",
                color=0x5865F2
            )
            
            result_embed.add_field(
                name="✅ Successful Deletions",
                value=f"{success_count} configuration(s)",
                inline=True
            )
            
            if failed_count > 0:
                result_embed.add_field(
                    name="❌ Failed Deletions",
                    value=f"{failed_count} configuration(s)",
                    inline=True
                )
            
            result_embed.set_footer(text="Configuration data has been permanently removed.")
            
            await interaction.followup.send(embed=result_embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    # Return the command so it can be tracked
    return delete_command
