import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from supabase import Client, create_client

# Load environment variables
load_dotenv()

class SupabaseClient:
    """A wrapper around the Supabase client for better type handling and error management"""
    
    def __init__(self):
        # Use different Supabase projects for test/prod environments
        env_type = os.getenv('ENV_TYPE', 'prod')
        url_key = "SUPABASE_URL_TEST" if env_type == "test" else "SUPABASE_URL"
        api_key = "SUPABASE_KEY_TEST" if env_type == "test" else "SUPABASE_KEY"
        
        url = os.getenv(url_key)
        key = os.getenv(api_key)
        
        if not url or not key:
            raise ValueError(f"{url_key} and {api_key} must be set in environment variables")
        
        self.client: Client = create_client(url, key)
    
    async def get_server_setting(self, server_id: str, key: str) -> Optional[Any]:
        """Retrieve a server-specific setting"""
        try:
            response = await self.client.table('server_settings').select('value') \
                .eq('server_id', server_id) \
                .eq('key', key) \
                .single() \
                .execute()
            return response.data.get('value') if response.data else None
        except Exception as e:
            print(f"Error fetching server setting: {e}")
            return None

    async def set_server_setting(self, server_id: str, key: str, value: Any) -> bool:
        """Set or update a server-specific setting"""
        try:
            # Try to update first
            response = await self.client.table('server_settings') \
                .update({'value': value}) \
                .eq('server_id', server_id) \
                .eq('key', key) \
                .execute()
            
            # If no rows were updated, insert new record
            if not response.data:
                response = self.client.table('server_settings').insert({
                    'server_id': server_id,
                    'key': key,
                    'value': value
                }).execute()
            
            return True
        except Exception as e:
            print(f"Error setting server setting: {e}")
            return False

    async def store_reminder(self, reminder_data: Dict[str, Any]) -> Optional[str]:
        """Store a reminder in the database"""
        try:
            response = self.client.table('reminders').insert(reminder_data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            print(f"Error storing reminder: {e}")
            return None

    async def get_active_reminders(self) -> List[Dict[str, Any]]:
        """Get all active reminders"""
        try:
            response = self.client.table('reminders') \
                .select('*') \
                .eq('is_active', True) \
                .execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching active reminders: {e}")
            return []

    async def update_reminder(self, reminder_id: str, data: Dict[str, Any]) -> bool:
        """Update a reminder's data"""
        try:
            response = self.client.table('reminders') \
                .update(data) \
                .eq('id', reminder_id) \
                .execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error updating reminder: {e}")
            return False

    async def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder"""
        try:
            response = self.client.table('reminders') \
                .delete() \
                .eq('id', reminder_id) \
                .execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error deleting reminder: {e}")
            return False

    async def cleanup_old_reminders(self, older_than_days: int = 7) -> int:
        """Delete old inactive reminders from the database
        
        Args:
            older_than_days: Delete reminders older than this many days
            
        Returns:
            Number of reminders deleted
        """
        try:
            # Calculate cutoff date
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=older_than_days)).isoformat()
            
            # Delete old inactive reminders or expired one-time reminders
            response = self.client.table('reminders') \
                .delete() \
                .filter('is_active', 'eq', False) \
                .filter('reminder_time', 'lt', cutoff_date) \
                .execute()
                
            return len(response.data) if response.data else 0
        except Exception as e:
            print(f"Error cleaning up old reminders: {e}")
            return 0

    # Generic data storage methods
    async def store_data(self, table: str, data: Dict[str, Any]) -> Optional[str]:
        """Store data in any table"""
        try:
            response = self.client.table(table).insert(data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            print(f"Error storing data in {table}: {e}")
            return None

    async def get_data(self, table: str, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get data from any table with query parameters"""
        try:
            query = self.client.table(table).select('*')
            for key, value in query_params.items():
                query = query.eq(key, value)
            response = query.execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching data from {table}: {e}")
            return []

# Singleton instance
_instance: Optional[SupabaseClient] = None

def get_client() -> SupabaseClient:
    """Get the Supabase client instance"""
    global _instance
    if _instance is None:
        _instance = SupabaseClient()
    return _instance
