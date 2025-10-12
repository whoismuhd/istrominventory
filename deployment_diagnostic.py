#!/usr/bin/env python3
"""
Deployment Diagnostic Script
This script helps identify issues with the deployed app
"""

import os
import sys
import traceback

def run_diagnostic():
    """Run comprehensive diagnostic checks"""
    print("🔍 DEPLOYMENT DIAGNOSTIC")
    print("=" * 50)
    
    # Check environment variables
    print("📊 Environment Variables:")
    env_vars = [
        'DATABASE_URL', 'DATABASE_TYPE', 'PRODUCTION_MODE', 
        'DISABLE_MIGRATION', 'PORT', 'STREAMLIT_SERVER_HEADLESS'
    ]
    
    for var in env_vars:
        value = os.getenv(var, 'NOT SET')
        status = "✅" if value != 'NOT SET' else "❌"
        print(f"  {status} {var}: {value}")
    
    print("\n🔗 Database Connection Test:")
    try:
        from database_config import get_conn
        with get_conn() as conn:
            if conn:
                print("  ✅ Database connection successful")
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result:
                    print("  ✅ Database query successful")
                else:
                    print("  ❌ Database query failed")
            else:
                print("  ❌ Database connection failed")
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        traceback.print_exc()
    
    print("\n📦 Package Import Test:")
    try:
        import streamlit
        print(f"  ✅ Streamlit: {streamlit.__version__}")
    except Exception as e:
        print(f"  ❌ Streamlit import failed: {e}")
    
    try:
        import pandas
        print(f"  ✅ Pandas: {pandas.__version__}")
    except Exception as e:
        print(f"  ❌ Pandas import failed: {e}")
    
    try:
        import psycopg2
        print(f"  ✅ psycopg2: Available")
    except Exception as e:
        print(f"  ❌ psycopg2 import failed: {e}")
    
    print("\n🏗️ App Import Test:")
    try:
        import istrominventory
        print("  ✅ App imports successfully")
    except Exception as e:
        print(f"  ❌ App import failed: {e}")
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("🔍 DIAGNOSTIC COMPLETE")

if __name__ == "__main__":
    run_diagnostic()
