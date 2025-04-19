# Cloud Manager - Multi-server V2ray Management Bot

Cloud Manager is a Discord bot with a web dashboard that allows server owners to manage V2ray configurations across multiple servers. Each Discord server can have its own set of V2ray servers, and users can only access their own configurations.

## Features

- **Multi-server Management**: Configure and manage multiple V2ray servers from one dashboard
- **Discord Authorization**: Use Discord OAuth2 for secure login to the dashboard
- **Role-based Permissions**: Configurable admin and manager roles
- **User Isolation**: Each Discord server's configurations are isolated
- **Dynamic Commands**: Server-specific Discord slash commands
- **Usage Monitoring**: Track bandwidth usage and expiration dates
- **Web Dashboard**: Modern, responsive interface for configuration management

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Discord Bot Token
- Discord Application with OAuth2 configured
- V2ray servers with accessible API

### Installation

1. Clone the repository
   ```
   git clone https://github.com/yourusername/cloud-manager.git
   cd cloud-manager
   ```

2. Create a virtual environment
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```
   pip install -r requirements.txt
   ```

4. Copy the example environment file
   ```
   cp .env.example .env
   ```

5. Edit the `.env` file with your configuration:
   - `BOT_TOKEN`: Your Discord bot token
   - `DISCORD_CLIENT_ID`: Your Discord OAuth2 client ID
   - `DISCORD_CLIENT_SECRET`: Your Discord OAuth2 client secret
   - `DISCORD_REDIRECT_URI`: The redirect URI (usually http://localhost:5000/callback for local development)
   - `SUPERADMIN_IDS`: Comma-separated list of Discord user IDs who should have superadmin access

### Running the Bot and Dashboard

1. Start the Discord bot:
   ```
   python main.py
   ```

2. In a separate terminal, start the web dashboard:
   ```
   cd dashboard
   python app.py
   ```

3. Access the web dashboard at http://localhost:5000

## Discord Commands

- `/create` - Create a new V2ray configuration
- `/update` - Update or extend an existing configuration
- `/delete` - Delete a configuration
- `/config` - Show configuration status and details
- `/usage` - Display bandwidth usage statistics
- `/servers add` - Add a new V2ray server (admin only)
- `/servers list` - List configured servers
- `/servers remove` - Remove a server (admin only)
- `/admin roles` - Configure admin and manager roles
- `/admin stats` - Display server usage statistics
- `/admin find` - Find a user's configuration

## Dashboard Features

- View and manage servers for each Discord server
- Create, update and delete client configurations
- Monitor bandwidth usage and expiration dates
- Bulk operations for client management
- Admin tools for server monitoring

## License

[MIT License](LICENSE)
