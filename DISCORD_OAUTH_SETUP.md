# Setting Up Discord OAuth for Cloud Manager

This guide will help you correctly configure Discord OAuth for your Cloud Manager application.

## Step 1: Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Note down the "Client ID" and "Client Secret" for your .env file

## Step 2: Configure OAuth2

1. In the left sidebar, click on "OAuth2"
2. Under "Redirects", add your redirect URI:
   - For local development: `http://localhost:5000/callback`
   - For production: `https://yourdomain.com/callback`
3. Make sure the URI is EXACTLY the same as what you put in your .env file

## Step 3: Configure OAuth2 URL Generator

1. Still in the OAuth2 section, scroll down to "OAuth2 URL Generator"
2. Select the following scopes:
   - `identify` - To get the user's Discord info
   - `guilds` - To see which servers the user is in
3. You don't need to select any bot permissions here

## Step 4: Update Your .env File

Update your .env file with the correct values:

```
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/callback
```

## Common Issues

### "Invalid OAuth2 redirect URI"

This error means the redirect URI you're using doesn't match EXACTLY what's in your Discord application settings.

Check for:
- HTTP vs HTTPS differences
- Extra or missing trailing slashes
- Different ports
- Different subdomains

### "Invalid client ID"

Make sure you've copied the correct client ID from your Discord application.

### "Invalid client secret"

Make sure you're using the correct client secret and it hasn't been reset recently.

## Testing OAuth Flow

1. Start your dashboard with `python run_dashboard.py`
2. Open the dashboard URL in your browser
3. Click "Login with Discord"
4. You should be redirected to Discord to authorize, then back to your dashboard
