#!/usr/bin/env python3
"""
Script to deploy database changes to production.
Usage: python scripts/deploy_db.py
"""

import os
import subprocess
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def get_env_vars(env: str) -> Optional[dict]:
    """Get the required environment variables"""
    env_type = 'TEST' if env == 'test' else 'PROD'
    
    required_vars = {
        'ref': f'SUPABASE_PROJECT_REF_{env_type}',
        'password': f'SUPABASE_DB_PASS_{env_type}'
    }
    
    values = {}
    for key, var_name in required_vars.items():
        value = os.getenv(var_name)
        if not value:
            print(f"Error: {var_name} environment variable not set")
            return None
        values[key] = value
    
    return values

def run_command(cmd: list[str], show_output: bool = False, env: dict = None) -> bool:
    """Run a command and return True if successful"""
    try:
        # Merge environment variables
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)

        if show_output:
            # Show output in real-time
            subprocess.run(cmd, check=True, env=cmd_env)
        else:
            # Capture output for error handling
            subprocess.run(cmd, check=True, capture_output=True, text=True, env=cmd_env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}")
        if not show_output and e.stderr:
            print(f"Error output: {e.stderr}")
        return False

def main():
    # Ensure we have Supabase CLI
    if not run_command(["supabase", "--version"]):
        print("Error: Supabase CLI not found. Install it with:")
        print("  brew install supabase/tap/supabase")
        return 1

    # Get environment variables
    env_vars = get_env_vars("prod")
    if not env_vars:
        return 1

    print("🔄 Deploying database changes to production...")
    
    # Link to production project
    print("Linking to production project...")
    if not run_command(["supabase", "link", "--project-ref", env_vars['ref'], "-p", env_vars['password']]):
        print("Error: Failed to link to production project")
        return 1

    # Push database changes
    print("Pushing database changes...")
    if not run_command(["supabase", "db", "push", "-p", env_vars['password']]):
        print("Error: Failed to push database changes")
        return 1

    print("✅ Database changes deployed successfully!")
    
    # Switch back to test database
    print("Switching back to test database...")
    test_vars = get_env_vars("test")
    if test_vars:
        if not run_command(["supabase", "link", "--project-ref", test_vars['ref'], "-p", test_vars['password']]):
            print("Warning: Failed to switch back to test database")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
