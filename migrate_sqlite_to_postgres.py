"""
SQLite to PostgreSQL Migration Script

This script migrates all data from the existing SQLite database to PostgreSQL.
It handles data type conversions, ID sequence alignment, and preserves all relationships.
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
from database_postgres import get_engine, execute_query, execute_update, get_conn

logger = logging.getLogger(__name__)

def connect_sqlite() -> sqlite3.Connection:
    """Connect to the existing SQLite database."""
    try:
        conn = sqlite3.connect('istrominventory.db')
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to SQLite database: {e}")
        raise

def get_table_data(conn: sqlite3.Connection, table_name: str) -> List[Dict[str, Any]]:
    """Get all data from a SQLite table."""
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name}")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get data from {table_name}: {e}")
        return []

def migrate_users() -> bool:
    """Migrate users table data."""
    try:
        logger.info("Migrating users table...")
        
        with connect_sqlite() as sqlite_conn:
            users_data = get_table_data(sqlite_conn, 'users')
        
        if not users_data:
            logger.info("No users data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM users")
        
        # Insert users data
        for user in users_data:
            execute_update("""
                INSERT INTO users (id, username, full_name, user_type, project_site, admin_code, created_at, is_active)
                VALUES (:id, :username, :full_name, :user_type, :project_site, :admin_code, :created_at, :is_active)
            """, user)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users))")
        
        logger.info(f"Migrated {len(users_data)} users")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate users: {e}")
        return False

def migrate_project_sites() -> bool:
    """Migrate project_sites table data."""
    try:
        logger.info("Migrating project_sites table...")
        
        with connect_sqlite() as sqlite_conn:
            sites_data = get_table_data(sqlite_conn, 'project_sites')
        
        if not sites_data:
            logger.info("No project_sites data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM project_sites")
        
        # Insert project sites data
        for site in sites_data:
            execute_update("""
                INSERT INTO project_sites (id, name, description, created_at, is_active)
                VALUES (:id, :name, :description, :created_at, :is_active)
            """, site)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('project_sites', 'id'), (SELECT MAX(id) FROM project_sites))")
        
        logger.info(f"Migrated {len(sites_data)} project sites")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate project_sites: {e}")
        return False

def migrate_items() -> bool:
    """Migrate items table data."""
    try:
        logger.info("Migrating items table...")
        
        with connect_sqlite() as sqlite_conn:
            items_data = get_table_data(sqlite_conn, 'items')
        
        if not items_data:
            logger.info("No items data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM items")
        
        # Insert items data
        for item in items_data:
            execute_update("""
                INSERT INTO items (id, code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site, created_at)
                VALUES (:id, :code, :name, :category, :unit, :qty, :unit_cost, :budget, :section, :grp, :building_type, :project_site, :created_at)
            """, item)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('items', 'id'), (SELECT MAX(id) FROM items))")
        
        logger.info(f"Migrated {len(items_data)} items")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate items: {e}")
        return False

def migrate_requests() -> bool:
    """Migrate requests table data."""
    try:
        logger.info("Migrating requests table...")
        
        with connect_sqlite() as sqlite_conn:
            requests_data = get_table_data(sqlite_conn, 'requests')
        
        if not requests_data:
            logger.info("No requests data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM requests")
        
        # Insert requests data
        for request in requests_data:
            execute_update("""
                INSERT INTO requests (id, item_id, item_name, requested_by, requested_qty, current_price, status, note, created_at, approved_by, approved_at, rejected_by, rejected_at)
                VALUES (:id, :item_id, :item_name, :requested_by, :requested_qty, :current_price, :status, :note, :created_at, :approved_by, :approved_at, :rejected_by, :rejected_at)
            """, request)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('requests', 'id'), (SELECT MAX(id) FROM requests))")
        
        logger.info(f"Migrated {len(requests_data)} requests")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate requests: {e}")
        return False

def migrate_notifications() -> bool:
    """Migrate notifications table data."""
    try:
        logger.info("Migrating notifications table...")
        
        with connect_sqlite() as sqlite_conn:
            notifications_data = get_table_data(sqlite_conn, 'notifications')
        
        if not notifications_data:
            logger.info("No notifications data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM notifications")
        
        # Insert notifications data with schema mapping
        for notification in notifications_data:
            # Map old schema to new schema
            mapped_data = {
                'id': notification.get('id'),
                'sender_id': None,  # Old schema doesn't have sender_id
                'receiver_id': notification.get('user_id'),
                'message': notification.get('message'),
                'type': notification.get('notification_type', 'info'),
                'is_read': bool(notification.get('is_read', 0)),
                'event_key': None,  # Old schema doesn't have event_key
                'created_at': notification.get('created_at')
            }
            
            execute_update("""
                INSERT INTO notifications (id, sender_id, receiver_id, message, type, is_read, event_key, created_at)
                VALUES (:id, :sender_id, :receiver_id, :message, :type, :is_read, :event_key, :created_at)
            """, mapped_data)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('notifications', 'id'), (SELECT MAX(id) FROM notifications))")
        
        logger.info(f"Migrated {len(notifications_data)} notifications")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate notifications: {e}")
        return False

def migrate_actuals() -> bool:
    """Migrate actuals table data."""
    try:
        logger.info("Migrating actuals table...")
        
        with connect_sqlite() as sqlite_conn:
            actuals_data = get_table_data(sqlite_conn, 'actuals')
        
        if not actuals_data:
            logger.info("No actuals data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM actuals")
        
        # Insert actuals data
        for actual in actuals_data:
            execute_update("""
                INSERT INTO actuals (id, item_id, actual_qty, actual_cost, actual_date, recorded_by, notes, project_site, created_at)
                VALUES (:id, :item_id, :actual_qty, :actual_cost, :actual_date, :recorded_by, :notes, :project_site, :created_at)
            """, actual)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('actuals', 'id'), (SELECT MAX(id) FROM actuals))")
        
        logger.info(f"Migrated {len(actuals_data)} actuals")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate actuals: {e}")
        return False

def migrate_access_codes() -> bool:
    """Migrate access_codes table data."""
    try:
        logger.info("Migrating access_codes table...")
        
        with connect_sqlite() as sqlite_conn:
            codes_data = get_table_data(sqlite_conn, 'access_codes')
        
        if not codes_data:
            logger.info("No access_codes data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM access_codes")
        
        # Insert access codes data
        for code in codes_data:
            execute_update("""
                INSERT INTO access_codes (id, admin_code, user_code, updated_at, updated_by)
                VALUES (:id, :admin_code, :user_code, :updated_at, :updated_by)
            """, code)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('access_codes', 'id'), (SELECT MAX(id) FROM access_codes))")
        
        logger.info(f"Migrated {len(codes_data)} access codes")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate access_codes: {e}")
        return False

def migrate_access_logs() -> bool:
    """Migrate access_logs table data."""
    try:
        logger.info("Migrating access_logs table...")
        
        with connect_sqlite() as sqlite_conn:
            logs_data = get_table_data(sqlite_conn, 'access_logs')
        
        if not logs_data:
            logger.info("No access_logs data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM access_logs")
        
        # Insert access logs data
        for log in logs_data:
            execute_update("""
                INSERT INTO access_logs (id, username, action, timestamp, ip_address, user_agent)
                VALUES (:id, :username, :action, :timestamp, :ip_address, :user_agent)
            """, log)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('access_logs', 'id'), (SELECT MAX(id) FROM access_logs))")
        
        logger.info(f"Migrated {len(logs_data)} access logs")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate access_logs: {e}")
        return False

def migrate_project_site_access_codes() -> bool:
    """Migrate project_site_access_codes table data."""
    try:
        logger.info("Migrating project_site_access_codes table...")
        
        with connect_sqlite() as sqlite_conn:
            codes_data = get_table_data(sqlite_conn, 'project_site_access_codes')
        
        if not codes_data:
            logger.info("No project_site_access_codes data to migrate")
            return True
        
        # Clear existing data
        execute_update("DELETE FROM project_site_access_codes")
        
        # Insert project site access codes data
        for code in codes_data:
            execute_update("""
                INSERT INTO project_site_access_codes (id, project_site, admin_code, user_code, updated_at)
                VALUES (:id, :project_site, :admin_code, :user_code, :updated_at)
            """, code)
        
        # Reset sequence
        execute_update("SELECT setval(pg_get_serial_sequence('project_site_access_codes', 'id'), (SELECT MAX(id) FROM project_site_access_codes))")
        
        logger.info(f"Migrated {len(codes_data)} project site access codes")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate project_site_access_codes: {e}")
        return False

def verify_migration() -> bool:
    """Verify that the migration was successful by comparing record counts."""
    try:
        logger.info("Verifying migration...")
        
        # Get counts from SQLite
        with connect_sqlite() as sqlite_conn:
            sqlite_counts = {}
            tables = ['users', 'project_sites', 'items', 'requests', 'notifications', 'actuals', 'access_codes', 'access_logs', 'project_site_access_codes']
            
            for table in tables:
                try:
                    cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}")
                    sqlite_counts[table] = cursor.fetchone()[0]
                except:
                    sqlite_counts[table] = 0
        
        # Get counts from PostgreSQL
        postgres_counts = {}
        for table in tables:
            try:
                result = execute_query(f"SELECT COUNT(*) FROM {table}")
                postgres_counts[table] = result.iloc[0, 0] if not result.empty else 0
            except:
                postgres_counts[table] = 0
        
        # Compare counts
        all_match = True
        for table in tables:
            sqlite_count = sqlite_counts.get(table, 0)
            postgres_count = postgres_counts.get(table, 0)
            
            if sqlite_count != postgres_count:
                logger.warning(f"Count mismatch for {table}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
                all_match = False
            else:
                logger.info(f"✓ {table}: {postgres_count} records")
        
        return all_match
        
    except Exception as e:
        logger.error(f"Failed to verify migration: {e}")
        return False

def run_migration() -> bool:
    """Run the complete migration process."""
    try:
        logger.info("Starting SQLite to PostgreSQL migration...")
        
        # Check if SQLite database exists
        if not os.path.exists('istrominventory.db'):
            logger.error("SQLite database file not found")
            return False
        
        # Check PostgreSQL connection
        try:
            health = get_engine().connect()
            health.close()
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            return False
        
        # Run migrations in order (respecting foreign key constraints)
        migrations = [
            ("users", migrate_users),
            ("project_sites", migrate_project_sites),
            ("items", migrate_items),
            ("requests", migrate_requests),
            ("notifications", migrate_notifications),
            ("actuals", migrate_actuals),
            ("access_codes", migrate_access_codes),
            ("access_logs", migrate_access_logs),
            ("project_site_access_codes", migrate_project_site_access_codes)
        ]
        
        for table_name, migration_func in migrations:
            logger.info(f"Migrating {table_name}...")
            if not migration_func():
                logger.error(f"Failed to migrate {table_name}")
                return False
        
        # Verify migration
        if not verify_migration():
            logger.error("Migration verification failed")
            return False
        
        logger.info("Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("🔄 SQLite to PostgreSQL Migration")
    print("=" * 50)
    
    if run_migration():
        print("✅ Migration completed successfully!")
        print("You can now use the PostgreSQL database.")
    else:
        print("❌ Migration failed!")
        print("Please check the logs for details.")
