import aiosqlite
import os
import json
import uuid
from datetime import datetime, timedelta
import asyncio
from utils.logger import setup_logger

logger = setup_logger("database")

class Database:
    def __init__(self, db_path="cloud_manager.db"):
        self.db_path = db_path
        self.lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize database tables if they don't exist"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Create guilds table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS guilds (
                            guild_id TEXT PRIMARY KEY,
                            guild_name TEXT NOT NULL,
                            admin_role_id TEXT,
                            manager_role_id TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Create servers table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS servers (
                            server_id TEXT PRIMARY KEY,
                            guild_id TEXT NOT NULL,
                            server_name TEXT NOT NULL,
                            api_url TEXT NOT NULL,
                            api_user TEXT NOT NULL,
                            api_password TEXT NOT NULL,
                            is_enabled BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                        )
                    ''')
                    
                    # Create users table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            user_id TEXT PRIMARY KEY,
                            discord_id TEXT NOT NULL,
                            guild_id TEXT NOT NULL,
                            username TEXT NOT NULL,
                            is_admin BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                        )
                    ''')
                    
                    # Create configs table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS configs (
                            config_id TEXT PRIMARY KEY,
                            server_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            inbound_id INTEGER NOT NULL,
                            client_uuid TEXT NOT NULL,
                            client_email TEXT NOT NULL,
                            expiry_date TIMESTAMP,
                            data_limit INTEGER DEFAULT 0,
                            data_used INTEGER DEFAULT 0,
                            is_enabled BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (server_id) REFERENCES servers(server_id),
                            FOREIGN KEY (user_id) REFERENCES users(user_id)
                        )
                    ''')
                    
                    await db.commit()
                    logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise
    
    async def add_guild(self, guild_id, guild_name):
        """Add a new guild or update existing one"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Check if guild exists
                    cursor = await db.execute(
                        "SELECT guild_id FROM guilds WHERE guild_id = ?",
                        (str(guild_id),)
                    )
                    existing = await cursor.fetchone()
                    
                    if existing:
                        # Update guild name
                        await db.execute(
                            "UPDATE guilds SET guild_name = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                            (guild_name, str(guild_id))
                        )
                        logger.info(f"Updated guild {guild_name} ({guild_id})")
                    else:
                        # Insert new guild
                        await db.execute(
                            "INSERT INTO guilds (guild_id, guild_name) VALUES (?, ?)",
                            (str(guild_id), guild_name)
                        )
                        logger.info(f"Added new guild {guild_name} ({guild_id})")
                    
                    await db.commit()
                    return True
        except Exception as e:
            logger.error(f"Error adding guild {guild_id}: {str(e)}")
            return False
    
    async def update_guild_roles(self, guild_id, admin_role_id, manager_role_id):
        """Update guild role IDs"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE guilds SET admin_role_id = ?, manager_role_id = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                        (str(admin_role_id), str(manager_role_id), str(guild_id))
                    )
                    await db.commit()
                    logger.info(f"Updated roles for guild {guild_id}")
                    return True
        except Exception as e:
            logger.error(f"Error updating roles for guild {guild_id}: {str(e)}")
            return False
    
    async def add_server(self, guild_id, server_name, api_url, api_user, api_password):
        """Add a new V2ray server to a guild"""
        try:
            server_id = str(uuid.uuid4())
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        INSERT INTO servers 
                        (server_id, guild_id, server_name, api_url, api_user, api_password) 
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (server_id, str(guild_id), server_name, api_url, api_user, api_password)
                    )
                    await db.commit()
                    logger.info(f"Added server {server_name} to guild {guild_id}")
                    return server_id
        except Exception as e:
            logger.error(f"Error adding server to guild {guild_id}: {str(e)}")
            return None
    
    async def get_servers_for_guild(self, guild_id):
        """Get all servers configured for a guild"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM servers WHERE guild_id = ? AND is_enabled = TRUE",
                    (str(guild_id),)
                )
                rows = await cursor.fetchall()
                servers = [dict(row) for row in rows]
                return servers
        except Exception as e:
            logger.error(f"Error getting servers for guild {guild_id}: {str(e)}")
            return []
    
    async def get_server(self, server_id):
        """Get a specific server by ID"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM servers WHERE server_id = ?",
                    (server_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Error getting server {server_id}: {str(e)}")
            return None
    
    async def add_user(self, discord_id, guild_id, username, is_admin=False):
        """Add or update a user"""
        try:
            user_id = str(uuid.uuid4())
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Check if user exists for this guild
                    cursor = await db.execute(
                        "SELECT user_id FROM users WHERE discord_id = ? AND guild_id = ?",
                        (str(discord_id), str(guild_id))
                    )
                    existing = await cursor.fetchone()
                    
                    if existing:
                        user_id = existing[0]
                        await db.execute(
                            """
                            UPDATE users SET 
                            username = ?, 
                            is_admin = ?,
                            updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = ?
                            """,
                            (username, is_admin, user_id)
                        )
                        logger.info(f"Updated user {username} ({discord_id}) in guild {guild_id}")
                    else:
                        await db.execute(
                            """
                            INSERT INTO users 
                            (user_id, discord_id, guild_id, username, is_admin) 
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (user_id, str(discord_id), str(guild_id), username, is_admin)
                        )
                        logger.info(f"Added new user {username} ({discord_id}) to guild {guild_id}")
                    
                    await db.commit()
                    return user_id
        except Exception as e:
            logger.error(f"Error adding user {discord_id} to guild {guild_id}: {str(e)}")
            return None
    
    async def add_config(self, server_id, user_id, inbound_id, client_uuid, client_email, 
                         expiry_days=30, data_limit_gb=0):
        """Add a new client configuration"""
        try:
            config_id = str(uuid.uuid4())
            # Calculate expiry date
            expiry_date = datetime.now() + timedelta(days=expiry_days)
            # Convert data limit from GB to bytes
            data_limit = data_limit_gb * 1024 * 1024 * 1024 if data_limit_gb > 0 else 0
            
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        INSERT INTO configs 
                        (config_id, server_id, user_id, inbound_id, client_uuid, client_email, 
                         expiry_date, data_limit) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (config_id, server_id, user_id, inbound_id, client_uuid, client_email, 
                         expiry_date.isoformat(), data_limit)
                    )
                    await db.commit()
                    logger.info(f"Added config for user {user_id} on server {server_id}")
                    return config_id
        except Exception as e:
            logger.error(f"Error adding config for user {user_id}: {str(e)}")
            return None
    
    async def get_configs_for_user(self, discord_id, guild_id):
        """Get all configs for a user across servers in a guild"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT c.*, s.server_name, s.api_url 
                    FROM configs c
                    JOIN users u ON c.user_id = u.user_id
                    JOIN servers s ON c.server_id = s.server_id
                    WHERE u.discord_id = ? AND u.guild_id = ? AND s.guild_id = ?
                    """,
                    (str(discord_id), str(guild_id), str(guild_id))
                )
                rows = await cursor.fetchall()
                configs = [dict(row) for row in rows]
                return configs
        except Exception as e:
            logger.error(f"Error getting configs for user {discord_id}: {str(e)}")
            return []
    
    async def update_config_usage(self, config_id, data_used):
        """Update the data usage for a config"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        UPDATE configs SET 
                        data_used = ?,
                        updated_at = CURRENT_TIMESTAMP
                        WHERE config_id = ?
                        """,
                        (data_used, config_id)
                    )
                    await db.commit()
                    return True
        except Exception as e:
            logger.error(f"Error updating usage for config {config_id}: {str(e)}")
            return False
    
    async def update_config_expiry(self, config_id, expiry_days):
        """Extend the expiry date for a config"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Get current expiry date
                    cursor = await db.execute(
                        "SELECT expiry_date FROM configs WHERE config_id = ?",
                        (config_id,)
                    )
                    row = await cursor.fetchone()
                    if not row:
                        return False
                    
                    # Calculate new expiry date
                    current_expiry = datetime.fromisoformat(row[0])
                    new_expiry = current_expiry + timedelta(days=expiry_days)
                    
                    # Update the database
                    await db.execute(
                        """
                        UPDATE configs SET 
                        expiry_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                        WHERE config_id = ?
                        """,
                        (new_expiry.isoformat(), config_id)
                    )
                    await db.commit()
                    logger.info(f"Extended expiry for config {config_id} by {expiry_days} days")
                    return True
        except Exception as e:
            logger.error(f"Error updating expiry for config {config_id}: {str(e)}")
            return False
    
    async def delete_config(self, config_id):
        """Delete a configuration"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "DELETE FROM configs WHERE config_id = ?",
                        (config_id,)
                    )
                    await db.commit()
                    logger.info(f"Deleted config {config_id}")
                    return True
        except Exception as e:
            logger.error(f"Error deleting config {config_id}: {str(e)}")
            return False
    
    async def toggle_config_status(self, config_id, is_enabled):
        """Enable or disable a configuration"""
        try:
            async with self.lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        UPDATE configs SET 
                        is_enabled = ?,
                        updated_at = CURRENT_TIMESTAMP
                        WHERE config_id = ?
                        """,
                        (is_enabled, config_id)
                    )
                    await db.commit()
                    status = "enabled" if is_enabled else "disabled"
                    logger.info(f"Config {config_id} {status}")
                    return True
        except Exception as e:
            logger.error(f"Error toggling status for config {config_id}: {str(e)}")
            return False
