import os
from dashboard.app import app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# For development only - allow OAuth2 without HTTPS
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
print("OAUTHLIB_INSECURE_TRANSPORT is enabled for local development")

if __name__ == "__main__":
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    # Print dashboard URL
    dashboard_url = os.getenv("DASHBOARD_URL", f"http://{host}:{port}")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
    
    print("\n" + "=" * 50)
    print(f"🌐 Dashboard running at: {dashboard_url}")
    if host == "0.0.0.0":
        print(f"🌐 Local access URL: http://localhost:{port}")
    print("=" * 50)
    
    print("\n💡 OAuth Configuration:")
    print(f"Discord OAuth redirect URI: {redirect_uri}")
    print("Make sure this EXACT redirect URI is added in your Discord Developer Portal")
    print("under OAuth2 -> Redirects. For more help, see DISCORD_OAUTH_SETUP.md")
    print("=" * 50 + "\n")
    
    app.run(host=host, port=port, debug=debug)
