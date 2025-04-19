import aiohttp
import json
import uuid
import asyncio
from datetime import datetime, timedelta
import urllib.parse
from utils.logger import setup_logger

logger = setup_logger("api")

class APIManager:
    def __init__(self, db, timeout=10):
        self.db = db
        self.timeout = timeout
        self.sessions = {}
        self.session_lock = asyncio.Lock()
    
    async def get_session(self, server_id):
        """Get or create a session for the specified server"""
        async with self.session_lock:
            if server_id not in self.sessions:
                self.sessions[server_id] = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    connector=aiohttp.TCPConnector(verify_ssl=False)
                )
            return self.sessions[server_id]
    
    async def close_all_sessions(self):
        """Close all API sessions"""
        async with self.session_lock:
            for server_id, session in self.sessions.items():
                if not session.closed:
                    await session.close()
            self.sessions = {}
    
    async def make_request(self, server_id, method, endpoint, data=None, params=None):
        """Make an API request to the V2ray panel"""
        try:
            # Get server details from the database
            server = await self.db.get_server(server_id)
            if not server:
                logger.error(f"Server {server_id} not found in database")
                return None
            
            # Get or create a session
            session = await self.get_session(server_id)
            
            # Build full URL
            base_url = server['api_url'].rstrip('/')
            endpoint = endpoint.lstrip('/')
            url = f"{base_url}/{endpoint}"
            
            # Make the request
            try:
                # Login if needed (to be implemented as needed)
                await self._ensure_login(server_id, session, base_url)
                
                # Make the actual request
                if method.upper() == 'GET':
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"API error: {response.status} - {await response.text()}")
                            return None
                elif method.upper() == 'POST':
                    async with session.post(url, json=data) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"API error: {response.status} - {await response.text()}")
                            return None
            except aiohttp.ClientError as e:
                logger.error(f"Request error to {url}: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Error making request: {str(e)}")
            return None
    
    async def _ensure_login(self, server_id, session, base_url):
        """Ensure the session is authenticated (to be implemented based on panel API)"""
        # This is a placeholder implementation. Update according to your panel's auth mechanism
        server = await self.db.get_server(server_id)
        if not server:
            return False
        
        login_url = f"{base_url}/login"
        login_data = {
            "username": server['api_user'],
            "password": server['api_password']
        }
        
        try:
            async with session.post(login_url, json=login_data) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"Login failed for server {server_id}: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Login error for server {server_id}: {str(e)}")
            return False
    
    async def get_inbounds(self, server_id):
        """Get all inbounds from a server"""
        response = await self.make_request(server_id, 'GET', '/panel/api/inbounds/list')
        if response and response.get('success'):
            return response.get('obj', [])
        return []
    
    async def get_client_traffic(self, server_id, email):
        """Get client traffic information"""
        response = await self.make_request(server_id, 'GET', f'/panel/api/inbounds/getClientTraffics/{email}')
        if response and response.get('success'):
            return response.get('obj', {})
        return {}
    
    async def create_client(self, server_id, inbound_id, email, expiry_days=30, data_limit_gb=0):
        """Create a new client on an inbound"""
        try:
            # Generate UUID for client
            client_id = str(uuid.uuid4())
            
            # Calculate expiry timestamp (in milliseconds)
            now = datetime.now()
            expiry_time = int((now + timedelta(days=expiry_days)).timestamp() * 1000)
            
            # Set data limit (in bytes)
            total_gb = data_limit_gb * 1024 * 1024 * 1024 if data_limit_gb > 0 else 0
            
            # Create client payload
            client = {
                "id": client_id,
                "flow": "",
                "email": email,
                "limitIp": 0,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "enable": True,
                "tgId": "",
                "subId": ""
            }
            
            # API endpoint for adding client
            endpoint = f"/panel/api/inbounds/addClient"
            payload = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client]})
            }
            
            # Make request
            response = await self.make_request(server_id, 'POST', endpoint, payload)
            if response and response.get('success'):
                logger.info(f"Created client {email} on inbound {inbound_id}")
                return {
                    "uuid": client_id,
                    "email": email,
                    "inbound_id": inbound_id,
                    "expiry_timestamp": expiry_time,
                    "data_limit": total_gb
                }
            else:
                logger.error(f"Failed to create client: {response}")
                return None
        except Exception as e:
            logger.error(f"Error creating client: {str(e)}")
            return None
    
    async def update_client(self, server_id, inbound_id, client_uuid, email=None, expiry_days=None, data_limit_gb=None):
        """Update an existing client"""
        try:
            # Get current client details
            inbound = await self.get_inbound_details(server_id, inbound_id)
            if not inbound:
                logger.error(f"Inbound {inbound_id} not found on server {server_id}")
                return False
            
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            client = None
            for c in clients:
                if c.get('id') == client_uuid:
                    client = c
                    break
            
            if not client:
                logger.error(f"Client {client_uuid} not found in inbound {inbound_id}")
                return False
            
            # Update client properties if specified
            if email:
                client['email'] = email
            
            if expiry_days is not None:
                # Calculate new expiry timestamp (in milliseconds)
                now = datetime.now()
                expiry_time = int((now + timedelta(days=expiry_days)).timestamp() * 1000)
                client['expiryTime'] = expiry_time
            
            if data_limit_gb is not None:
                # Set data limit (in bytes)
                total_gb = data_limit_gb * 1024 * 1024 * 1024 if data_limit_gb > 0 else 0
                client['totalGB'] = total_gb
            
            # API endpoint for updating client
            endpoint = f"/panel/api/inbounds/updateClient/{client_uuid}"
            payload = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client]})
            }
            
            # Make request
            response = await self.make_request(server_id, 'POST', endpoint, payload)
            if response and response.get('success'):
                logger.info(f"Updated client {client_uuid} on inbound {inbound_id}")
                return True
            else:
                logger.error(f"Failed to update client: {response}")
                return False
        except Exception as e:
            logger.error(f"Error updating client: {str(e)}")
            return False
    
    async def delete_client(self, server_id, inbound_id, client_uuid):
        """Delete a client from an inbound"""
        try:
            endpoint = f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
            response = await self.make_request(server_id, 'POST', endpoint)
            if response and response.get('success'):
                logger.info(f"Deleted client {client_uuid} from inbound {inbound_id}")
                return True
            else:
                logger.error(f"Failed to delete client: {response}")
                return False
        except Exception as e:
            logger.error(f"Error deleting client: {str(e)}")
            return False
    
    async def get_inbound_details(self, server_id, inbound_id):
        """Get details of a specific inbound"""
        try:
            endpoint = f"/panel/api/inbounds/get/{inbound_id}"
            response = await self.make_request(server_id, 'GET', endpoint)
            if response and response.get('success'):
                return response.get('obj', {})
            else:
                logger.error(f"Failed to get inbound details: {response}")
                return None
        except Exception as e:
            logger.error(f"Error getting inbound details: {str(e)}")
            return None
    
    async def generate_client_link(self, server_id, inbound_id, client_uuid):
        """Generate a client configuration link"""
        try:
            # Get inbound details
            inbound = await self.get_inbound_details(server_id, inbound_id)
            if not inbound:
                return None
            
            # Get server details
            server = await self.db.get_server(server_id)
            if not server:
                return None
            
            # Parse server URL to get hostname
            parsed_url = urllib.parse.urlparse(server['api_url'])
            hostname = parsed_url.netloc.split(':')[0]
            
            # Get client details
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            client = None
            for c in clients:
                if c.get('id') == client_uuid:
                    client = c
                    break
            
            if not client:
                return None
            
            # Parse stream settings
            stream_settings = json.loads(inbound.get('streamSettings', '{}'))
            security = stream_settings.get('security', 'tls')
            network = stream_settings.get('network', 'tcp')
            
            # Build VLESS link
            port = inbound.get('port', 443)
            vless_params = f"type={network}&security={security}"
            
            if security == 'tls' and 'tlsSettings' in stream_settings:
                sni = stream_settings['tlsSettings'].get('serverName', hostname)
                if sni:
                    vless_params += f"&sni={sni}"
            
            username = client.get('email', '').split('_')[0]
            vless_link = f"vless://{client_uuid}@{hostname}:{port}?{vless_params}#{username}"
            
            return vless_link
        except Exception as e:
            logger.error(f"Error generating client link: {str(e)}")
            return None
