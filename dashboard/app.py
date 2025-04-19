import os
import json
import time
from datetime import datetime, timezone
import sqlite3
import secrets
import sys
import threading
import logging

from flask import Flask, render_template, redirect, session, url_for, request, jsonify, flash
from flask_discord import DiscordOAuth2Session, requires_authorization, Unauthorized

# Add parent directory to path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.db import Database
from utils.api_manager import APIManager
from utils.logger import setup_logger

# Set up logging
logger = setup_logger("dashboard")

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# For development only - allow OAuth2 without HTTPS
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
logging.getLogger('oauthlib').setLevel(logging.INFO)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
app.config["DISCORD_BOT_TOKEN"] = os.getenv("BOT_TOKEN")
app.config["SUPERADMIN_IDS"] = [int(id) for id in os.getenv("SUPERADMIN_IDS", "").split(",") if id]

# Debug OAuth configuration
print("\nDiscord OAuth Configuration:")
print(f"Client ID: {app.config['DISCORD_CLIENT_ID']}")
print(f"Redirect URI: {app.config['DISCORD_REDIRECT_URI']}")
print("Make sure this exact Redirect URI is added to your Discord application OAuth settings")
print("OAUTHLIB_INSECURE_TRANSPORT is enabled for local development\n")

# Initialize Discord OAuth
discord = DiscordOAuth2Session(app)

# Initialize database connection
db = Database()
db_connection = None

# Initialize a thread-local SQLite connection
def get_db_connection():
    thread_local = threading.local()
    
    # Check if the current thread already has a database connection
    if not hasattr(thread_local, 'db_connection'):
        # Create a new database connection for this thread
        thread_local.db_connection = sqlite3.connect(os.getenv('DB_PATH'))
    
    # Set the row factory for dictionary-like access
    thread_local.db_connection.row_factory = sqlite3.Row
    
    return thread_local.db_connection

# Initialize API manager
api_manager = APIManager(db)

# Error handlers
@app.errorhandler(Unauthorized)
def handle_unauthorized(e):
    """Handle unauthorized access attempts"""
    return redirect(url_for("login"))

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    logger.error(f"Server error: {str(e)}")
    return render_template("500.html", error=str(e)), 500

# Routes
@app.route("/")
def index():
    """Landing page"""
    if discord.authorized:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/login")
def login():
    """Discord OAuth login"""
    return discord.create_session()

@app.route("/callback")
def callback():
    """Discord OAuth callback"""
    try:
        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id
        session['username'] = user.name
        session['avatar_url'] = user.avatar_url or user.default_avatar_url
        return redirect(url_for("dashboard"))
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return redirect(url_for("index"))

@app.route("/logout")
def logout():
    """Logout from the dashboard"""
    discord.revoke()
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@requires_authorization
def dashboard():
    """Main dashboard after login"""
    user = discord.fetch_user()
    is_superadmin = user.id in app.config["SUPERADMIN_IDS"]
    shared_guilds = []
    conn = get_db_connection()

    if is_superadmin:
        cursor = conn.execute("SELECT guild_id, guild_name FROM guilds")
        rows = cursor.fetchall()
        shared_guilds = [{"id": row["guild_id"], "name": row["guild_name"]} for row in rows]
    else:
        user_guilds = discord.fetch_guilds()
        for guild in user_guilds:
            cursor = conn.execute(
                "SELECT guild_name FROM guilds WHERE guild_id = ?", 
                (str(guild.id),)
            )
            row = cursor.fetchone()
            if row:
                shared_guilds.append({"id": str(guild.id), "name": row[0]})

    return render_template(
        "dashboard.html", 
        user=user, 
        shared_guilds=shared_guilds,
        is_superadmin=is_superadmin
    )

@app.route("/guild/<guild_id>")
@requires_authorization
def guild_dashboard(guild_id):
    """Dashboard for a specific guild"""
    user = discord.fetch_user()
    logger.info(f"User {user.id} ({user.name}) accessing guild dashboard for {guild_id}")
    
    # Check if user is authorized for this guild
    if not is_user_authorized_for_guild(user.id, guild_id):
        logger.warning(f"User {user.id} ({user.name}) not authorized for guild {guild_id} - redirecting")
        flash("You don't have access to this Discord server.", "danger")
        return redirect(url_for("dashboard"))
    
    try:
        logger.info(f"User {user.id} authorized for guild {guild_id} - rendering dashboard")
            
        # Get guild information
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT guild_name FROM guilds WHERE guild_id = ?", 
            (guild_id,)
        )
        guild = cursor.fetchone()
        
        if not guild:
            logger.warning(f"Guild {guild_id} not found in database - redirecting")
            flash("This Discord server is not configured with Cloud Manager.", "warning")
            return redirect(url_for("dashboard"))
            
        logger.info(f"Found guild in database: {guild_id} ({guild['guild_name']})")
        
        # Get servers for this guild
        cursor = conn.execute(
            "SELECT * FROM servers WHERE guild_id = ? AND is_enabled = 1",
            (guild_id,)
        )
        servers = cursor.fetchall()
        logger.info(f"Found {len(servers)} servers for guild {guild_id}")
            
        # Check if user is admin
        is_admin = is_user_admin_for_guild(user.id, guild_id)
        logger.info(f"User {user.id} admin status for guild {guild_id}: {is_admin}")
            
        return render_template(
            "guild_dashboard.html",
            user=user,
            guild_id=guild_id,
            guild_name=guild["guild_name"],
            servers=servers,
            is_admin=is_admin
        )
    except Exception as e:
        logger.error(f"Error loading guild dashboard for {guild_id}: {str(e)}")
        flash(f"An error occurred while loading the server dashboard: {str(e)}", "danger")
        return redirect(url_for("dashboard"))

@app.route("/server/<server_id>")
@requires_authorization
def server_dashboard(server_id):
    """Dashboard for a specific server"""
    user = discord.fetch_user()
    
    try:
        # Get server details using direct SQLite
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT * FROM servers WHERE server_id = ?",
            (server_id,)
        )
        server = cursor.fetchone()
        
        if not server:
            return redirect(url_for("dashboard"))
        
        guild_id = server["guild_id"]
        
        # Check if user is authorized for this guild
        if not is_user_authorized_for_guild(user.id, guild_id):
            return redirect(url_for("dashboard"))
            
        # Check if user is admin
        is_admin = is_user_admin_for_guild(user.id, guild_id)
        
        return render_template(
            "server_dashboard.html",
            user=user,
            server=dict(server),
            guild_id=guild_id,
            is_admin=is_admin
        )
    except Exception as e:
        logger.error(f"Error loading server dashboard for {server_id}: {str(e)}")
        return redirect(url_for("dashboard"))

# Helper functions
def is_user_authorized_for_guild(user_id, guild_id):
    """Check if a user is authorized to access a guild dashboard"""
    logger.info(f"Checking authorization for user {user_id} in guild {guild_id}")
    
    # Super admins have access to all guilds
    if user_id in app.config["SUPERADMIN_IDS"]:
        logger.info(f"User {user_id} is a superadmin - access granted")
        return True

    try:
        # Check if user has a role in the guild
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT user_id FROM users WHERE discord_id = ? AND guild_id = ?",
            (str(user_id), guild_id)
        )
        if cursor.fetchone():
            logger.info(f"User {user_id} found in guild {guild_id} database - access granted")
            return True

        # Try to check if user is in Discord guild
        try:
            headers = {"Authorization": f"Bot {app.config['DISCORD_BOT_TOKEN']}"}
            user_data = discord.request(
                f"/guilds/{guild_id}/members/{user_id}",
                headers=headers
            )
            
            if user_data:
                logger.info(f"User {user_id} found in Discord guild {guild_id} - access granted")
                return True
            else:
                logger.warning(f"User {user_id} not found in Discord guild {guild_id} - access denied")
                return False
        except Exception as e:
            logger.error(f"Discord API error while checking guild membership: {str(e)}")
            return False
    except Exception as e:
        logger.error(f"Error in is_user_authorized_for_guild: {str(e)}")
        return False

def is_user_admin_for_guild(user_id, guild_id):
    """Check if a user is an admin for a guild"""
    # Super admins are admin for all guilds
    if user_id in app.config["SUPERADMIN_IDS"]:
        return True

    try:
        # Get admin role ID from database
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT admin_role_id FROM guilds WHERE guild_id = ?", 
            (guild_id,)
        )
        row = cursor.fetchone()
        if not row or not row["admin_role_id"]:
            return False

        admin_role_id = row["admin_role_id"]
        
        # Check if user has admin role on Discord
        try:
            headers = {"Authorization": f"Bot {app.config['DISCORD_BOT_TOKEN']}"}
            user_data = discord.request(
                f"/guilds/{guild_id}/members/{user_id}",
                headers=headers
            )
            if not user_data or "roles" not in user_data:
                return False
            return admin_role_id in user_data["roles"]
        except Exception as e:
            logger.error(f"Discord API error while checking admin status: {str(e)}")
            # Fall back to database check for admin status
            cursor = conn.execute(
                """
                SELECT 1 FROM guilds 
                WHERE guild_id = ? AND (owner_id = ? OR admin_ids LIKE ?)
                """, 
                (guild_id, str(user_id), f"%{user_id}%")
            )
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

if __name__ == "__main__":
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0") 
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    # Print dashboard URL
    dashboard_url = os.getenv("DASHBOARD_URL", f"http://{host}:{port}")
    print("\n" + "=" * 50)
    print(f"🌐 Dashboard running at: {dashboard_url}")
    if host == "0.0.0.0":
        print(f"🌐 Local access URL: http://localhost:{port}")
    print("=" * 50 + "\n")
    
    app.run(host=host, port=port, debug=debug)