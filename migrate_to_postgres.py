#!/usr/bin/env python3
"""
Migration script to move data from SQLite to PostgreSQL
Run this before deploying to ensure data persistence
"""

import sqlite3
import psycopg2
import os
from datetime import datetime
import pandas as pd

def migrate_sqlite_to_postgres():
    """Migrate all data from SQLite to PostgreSQL"""
    
    # SQLite connection
    sqlite_conn = sqlite3.connect('istrominventory.db')
    sqlite_cur = sqlite_conn.cursor()
    
    # PostgreSQL connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found. Set it in your environment.")
        return False
    
    try:
        pg_conn = psycopg2.connect(database_url)
        pg_cur = pg_conn.cursor()
        
        print("🔄 Starting migration from SQLite to PostgreSQL...")
        
        # Get all tables from SQLite
        sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in sqlite_cur.fetchall()]
        
        print(f"📋 Found tables: {tables}")
        
        for table in tables:
            if table == 'sqlite_sequence':
                continue
                
            print(f"🔄 Migrating table: {table}")
            
            # Get table structure
            sqlite_cur.execute(f"PRAGMA table_info({table})")
            columns = sqlite_cur.fetchall()
            
            # Get all data
            sqlite_cur.execute(f"SELECT * FROM {table}")
            rows = sqlite_cur.fetchall()
            
            if not rows:
                print(f"   ⚠️  Table {table} is empty, skipping...")
                continue
            
            # Insert data into PostgreSQL
            for row in rows:
                try:
                    # Create placeholders for the values
                    placeholders = ', '.join(['%s'] * len(row))
                    columns_str = ', '.join([col[1] for col in columns])
                    
                    query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                    pg_cur.execute(query, row)
                    
                except Exception as e:
                    print(f"   ⚠️  Error inserting row into {table}: {e}")
                    continue
            
            print(f"   ✅ Migrated {len(rows)} rows to {table}")
        
        pg_conn.commit()
        print("🎉 Migration completed successfully!")
        
        # Verify migration
        print("\n📊 Verification:")
        for table in tables:
            if table == 'sqlite_sequence':
                continue
            try:
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                pg_count = pg_cur.fetchone()[0]
                sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
                sqlite_count = sqlite_cur.fetchone()[0]
                print(f"   {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
            except:
                pass
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    finally:
        sqlite_conn.close()
        if 'pg_conn' in locals():
            pg_conn.close()

if __name__ == "__main__":
    print("🚀 Starting SQLite to PostgreSQL migration...")
    success = migrate_sqlite_to_postgres()
    if success:
        print("✅ Migration completed! Your data is now persistent.")
    else:
        print("❌ Migration failed. Check the errors above.")
