#!/usr/bin/env python3
"""
Debug script to check SQL placeholder configuration
"""

import os
import sys

# Add current directory to path
sys.path.append('.')

# Check environment variables
print("🔍 Environment Variables:")
print(f"DATABASE_TYPE: {os.getenv('DATABASE_TYPE', 'NOT SET')}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT SET')[:50]}..." if os.getenv('DATABASE_URL') else "DATABASE_URL: NOT SET")

# Check database configuration
try:
    from database_config import get_conn, DATABASE_TYPE, DATABASE_URL
    print(f"\n🔍 Database Config:")
    print(f"DATABASE_TYPE from config: {DATABASE_TYPE}")
    print(f"DATABASE_URL from config: {DATABASE_URL[:50]}..." if DATABASE_URL else "DATABASE_URL: NOT SET")
    
    # Test connection
    try:
        with get_conn() as conn:
            print("✅ Database connection successful!")
            cur = conn.cursor()
            if DATABASE_TYPE == 'postgresql':
                cur.execute("SELECT version();")
            else:
                cur.execute("SELECT sqlite_version();")
            version = cur.fetchone()[0]
            print(f"Database Version: {version}")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        
except ImportError as e:
    print(f"❌ Database config import failed: {e}")

# Test placeholder function
try:
    from istrominventory import get_sql_placeholder, DATABASE_CONFIGURED
    print(f"\n🔍 Placeholder Test:")
    print(f"DATABASE_CONFIGURED: {DATABASE_CONFIGURED}")
    print(f"os.getenv('DATABASE_TYPE'): {os.getenv('DATABASE_TYPE')}")
    placeholder = get_sql_placeholder()
    print(f"get_sql_placeholder() returns: '{placeholder}'")
    
    # Test the actual query that's failing
    project_site = "Lifecamp Kafe"
    placeholder = get_sql_placeholder()
    q = f"SELECT id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site FROM items WHERE project_site = {placeholder}"
    q += " ORDER BY budget, section, grp, building_type, name"
    print(f"\n🔍 Generated Query:")
    print(f"Query: {q}")
    print(f"Params: ({project_site},)")
    
except ImportError as e:
    print(f"❌ Import failed: {e}")

