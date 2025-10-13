"""
Migration script for notification system improvements.

This script safely migrates the existing notification table to the new schema
with proper indexes, foreign keys, and cascade deletion.
"""

import logging
from sqlalchemy import text
from database_config import get_engine

logger = logging.getLogger(__name__)

def migrate_notification_schema():
    """
    Migrate the notification table to the new schema.
    This is safe to run multiple times (idempotent).
    """
    try:
        engine = get_engine()
        
        with engine.connect() as conn:
            # Check if we need to migrate
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = 'notifications' AND column_name = 'sender_id'
            """))
            
            if result.scalar() == 0:
                logger.info("Starting notification schema migration...")
                
                # Step 1: Add new columns
                conn.execute(text("""
                    ALTER TABLE notifications 
                    ADD COLUMN IF NOT EXISTS sender_id INTEGER,
                    ADD COLUMN IF NOT EXISTS receiver_id INTEGER,
                    ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'info',
                    ADD COLUMN IF NOT EXISTS event_key TEXT UNIQUE
                """))
                
                # Step 2: Migrate existing data
                conn.execute(text("""
                    UPDATE notifications 
                    SET receiver_id = user_id,
                        type = notification_type,
                        sender_id = NULL
                    WHERE receiver_id IS NULL
                """))
                
                # Step 3: Add foreign key constraints
                conn.execute(text("""
                    ALTER TABLE notifications 
                    ADD CONSTRAINT fk_notifications_sender 
                    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
                """))
                
                conn.execute(text("""
                    ALTER TABLE notifications 
                    ADD CONSTRAINT fk_notifications_receiver 
                    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
                """))
                
                # Step 4: Create indexes
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_notifications_receiver_read_created 
                    ON notifications(receiver_id, is_read, created_at DESC)
                """))
                
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_notifications_sender_created 
                    ON notifications(sender_id, created_at DESC)
                """))
                
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_notifications_event_key 
                    ON notifications(event_key) WHERE event_key IS NOT NULL
                """))
                
                # Step 5: Clean up old columns (optional, can be done later)
                # conn.execute(text("ALTER TABLE notifications DROP COLUMN IF EXISTS notification_type"))
                # conn.execute(text("ALTER TABLE notifications DROP COLUMN IF EXISTS title"))
                # conn.execute(text("ALTER TABLE notifications DROP COLUMN IF EXISTS user_id"))
                # conn.execute(text("ALTER TABLE notifications DROP COLUMN IF EXISTS request_id"))
                
                logger.info("Notification schema migration completed successfully!")
                return True
            else:
                logger.info("Notification schema already migrated")
                return True
                
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful."""
    try:
        engine = get_engine()
        
        with engine.connect() as conn:
            # Check if new columns exist
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'notifications' 
                AND column_name IN ('sender_id', 'receiver_id', 'type', 'event_key')
            """))
            
            columns = [row[0] for row in result.fetchall()]
            expected_columns = ['sender_id', 'receiver_id', 'type', 'event_key']
            
            if all(col in columns for col in expected_columns):
                logger.info("✅ Migration verification successful")
                return True
            else:
                logger.error("❌ Migration verification failed")
                return False
                
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Starting notification system migration...")
    
    if migrate_notification_schema():
        if verify_migration():
            print("✅ Migration completed successfully!")
        else:
            print("❌ Migration verification failed")
    else:
        print("❌ Migration failed")
