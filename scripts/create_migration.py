#!/usr/bin/env python3
"""
Helper script to create new migrations.
Usage: python scripts/create_migration.py "description of migration"
"""

import os
import sys
from datetime import datetime


def create_migration(description):
    # Convert description to snake_case
    name = description.lower().replace(' ', '_')
    
    # Get timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Create filename
    filename = f"{timestamp}_{name}.sql"
    
    # Get migrations directory
    migrations_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'supabase',
        'migrations'
    )
    
    # Create file
    filepath = os.path.join(migrations_dir, filename)
    with open(filepath, 'w') as f:
        f.write(f"-- Migration: {description}\n\n")
