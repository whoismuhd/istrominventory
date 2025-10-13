"""
Database Schema Bootstrap Script

This script initializes the PostgreSQL database with all required tables and default data.
It can be run safely multiple times and will not overwrite existing data.
"""

import os
import logging
from database_postgres import initialize_database, check_database_health, get_connection_string

logger = logging.getLogger(__name__)

def bootstrap_database() -> bool:
    """
    Bootstrap the database with tables and default data.
    This function is idempotent and safe to run multiple times.
    """
    try:
        logger.info("Starting database bootstrap...")
        
        # Check database health
        health = check_database_health()
        if health["status"] != "healthy":
            logger.error(f"Database health check failed: {health}")
            return False
        
        logger.info(f"Database connection: {health['database_type']} - {health.get('database_name', 'unknown')}")
        
        # Initialize database
        if not initialize_database():
            logger.error("Database initialization failed")
            return False
        
        logger.info("Database bootstrap completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Database bootstrap failed: {e}")
        return False

def create_default_admin_user() -> bool:
    """
    Create a default admin user if none exists.
    """
    try:
        from database_postgres import execute_query, execute_update
        
        # Check if any admin users exist
        result = execute_query("SELECT COUNT(*) FROM users WHERE user_type = 'admin'")
        admin_count = result.iloc[0, 0] if not result.empty else 0
        
        if admin_count > 0:
            logger.info("Admin users already exist, skipping default admin creation")
            return True
        
        # Create default admin user
        admin_data = {
            'username': 'admin',
            'full_name': 'System Administrator',
            'user_type': 'admin',
            'project_site': 'ALL',
            'admin_code': 'Istrom2026',
            'is_active': 1
        }
        
        execute_update("""
            INSERT INTO users (username, full_name, user_type, project_site, admin_code, is_active)
            VALUES (:username, :full_name, :user_type, :project_site, :admin_code, :is_active)
        """, admin_data)
        
        logger.info("Default admin user created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create default admin user: {e}")
        return False

def create_sample_data() -> bool:
    """
    Create sample data for testing and development.
    """
    try:
        from database_postgres import execute_query, execute_update
        
        # Check if sample data already exists
        result = execute_query("SELECT COUNT(*) FROM items")
        item_count = result.iloc[0, 0] if not result.empty else 0
        
        if item_count > 0:
            logger.info("Sample data already exists, skipping creation")
            return True
        
        # Create sample items
        sample_items = [
            {
                'code': 'CEM001',
                'name': 'Cement (50kg)',
                'category': 'Construction',
                'unit': 'bags',
                'qty': 100.0,
                'unit_cost': 3500.0,
                'budget': 'Budget 1 - Flats',
                'section': 'Foundation',
                'grp': 'General Materials',
                'building_type': 'Flats',
                'project_site': 'Lifecamp Kafe'
            },
            {
                'code': 'STEEL001',
                'name': 'Steel Rods (12mm)',
                'category': 'Construction',
                'unit': 'tons',
                'qty': 5.0,
                'unit_cost': 450000.0,
                'budget': 'Budget 1 - Flats',
                'section': 'Foundation',
                'grp': 'Iron',
                'building_type': 'Flats',
                'project_site': 'Lifecamp Kafe'
            },
            {
                'code': 'SAND001',
                'name': 'Sharp Sand',
                'category': 'Construction',
                'unit': 'trips',
                'qty': 10.0,
                'unit_cost': 15000.0,
                'budget': 'Budget 1 - Flats',
                'section': 'Foundation',
                'grp': 'General Materials',
                'building_type': 'Flats',
                'project_site': 'Lifecamp Kafe'
            }
        ]
        
        for item in sample_items:
            execute_update("""
                INSERT INTO items (code, name, category, unit, qty, unit_cost, budget, section, grp, building_type, project_site)
                VALUES (:code, :name, :category, :unit, :qty, :unit_cost, :budget, :section, :grp, :building_type, :project_site)
            """, item)
        
        logger.info(f"Created {len(sample_items)} sample items")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")
        return False

def run_bootstrap() -> bool:
    """
    Run the complete bootstrap process.
    """
    try:
        print("🚀 Database Bootstrap")
        print("=" * 50)
        
        # Bootstrap database
        if not bootstrap_database():
            print("❌ Database bootstrap failed")
            return False
        
        # Create default admin user
        if not create_default_admin_user():
            print("❌ Default admin user creation failed")
            return False
        
        # Create sample data (optional)
        if os.getenv('CREATE_SAMPLE_DATA', 'false').lower() == 'true':
            if not create_sample_data():
                print("⚠️ Sample data creation failed (non-critical)")
        
        print("✅ Database bootstrap completed successfully!")
        print(f"Connection: {get_connection_string()}")
        return True
        
    except Exception as e:
        print(f"❌ Bootstrap failed: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    success = run_bootstrap()
    exit(0 if success else 1)
