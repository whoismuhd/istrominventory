# SQLite to PostgreSQL Migration Guide

This guide provides step-by-step instructions for migrating your Istrom Inventory Management System from SQLite to PostgreSQL.

## 🎯 Overview

The migration process involves:
1. **Database Schema Migration** - Convert SQLite schema to PostgreSQL
2. **Code Refactoring** - Replace SQLite-specific code with PostgreSQL-compatible code
3. **Data Migration** - Transfer existing data from SQLite to PostgreSQL
4. **Testing & Validation** - Ensure all functionality works with PostgreSQL

## 📋 Prerequisites

- Python 3.8+
- PostgreSQL database (local or cloud)
- Existing SQLite database (`istrominventory.db`)
- All required Python packages installed

## 🚀 Step-by-Step Migration

### Step 1: Install Required Packages

```bash
pip install psycopg2-binary sqlalchemy pandas streamlit
```

### Step 2: Set Up PostgreSQL Database

#### Option A: Local PostgreSQL
```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt-get install postgresql postgresql-contrib

# Create database
sudo -u postgres createdb istrominventory

# Create user
sudo -u postgres psql -c "CREATE USER istrom WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE istrominventory TO istrom;"
```

#### Option B: Cloud PostgreSQL (Render)
1. Create a new PostgreSQL database on Render
2. Get the connection string from Render dashboard
3. Set the `DATABASE_URL` environment variable

### Step 3: Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
# For local development
export DATABASE_URL="postgresql://istrom:your_password@localhost:5432/istrominventory"

# For production (Render)
export DATABASE_URL="postgresql://username:password@hostname:port/database_name"
```

### Step 4: Initialize PostgreSQL Database

```bash
# Bootstrap the database schema
python bootstrap_schema.py
```

This will:
- Create all required tables
- Set up indexes for performance
- Insert default data (admin user, access codes, project sites)

### Step 5: Migrate Data from SQLite

```bash
# Migrate existing data from SQLite to PostgreSQL
python migrate_sqlite_to_postgres.py
```

This will:
- Read all data from `istrominventory.db`
- Convert data types for PostgreSQL compatibility
- Insert data into PostgreSQL tables
- Reset ID sequences to match existing data
- Verify migration success

### Step 6: Update Application Code

Replace the main application file:

```bash
# Backup original file
cp istrominventory.py istrominventory_sqlite_backup.py

# Replace with PostgreSQL version
cp istrominventory_postgres.py istrominventory.py
```

### Step 7: Test the Application

```bash
# Run the application
streamlit run istrominventory.py
```

Verify that:
- ✅ Database connection works
- ✅ User authentication works
- ✅ All data is accessible
- ✅ CRUD operations work
- ✅ Notifications system works

## 🔧 Configuration Files

### Environment Variables

Create a `.env` file:

```env
# Database Configuration
DATABASE_URL=postgresql://username:password@hostname:port/database_name

# Application Settings
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Optional Settings
CREATE_SAMPLE_DATA=false
DEBUG=false
```

### Render Deployment

Update `render.yaml`:

```yaml
services:
  - type: web
    name: istrominventory
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: streamlit run istrominventory.py --server.headless true --server.port $PORT
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: istrominventory
          property: connectionString
      - key: STREAMLIT_SERVER_HEADLESS
        value: true
      - key: STREAMLIT_SERVER_PORT
        value: 8501
```

## 📊 Database Schema Changes

### Key Differences

| Aspect | SQLite | PostgreSQL |
|--------|--------|------------|
| Primary Keys | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |
| Data Types | `TEXT`, `INTEGER`, `REAL` | `TEXT`, `INTEGER`, `NUMERIC`, `BOOLEAN` |
| Timestamps | `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` or `NOW()` |
| Foreign Keys | `FOREIGN KEY (col) REFERENCES table(id)` | `FOREIGN KEY (col) REFERENCES table(id) ON DELETE CASCADE` |
| Indexes | `CREATE INDEX` | `CREATE INDEX IF NOT EXISTS` |

### New Features

- **Cascade Deletion** - Deleting a user removes all related data
- **Performance Indexes** - Optimized for common queries
- **Data Validation** - CHECK constraints for data integrity
- **Connection Pooling** - Better performance under load

## 🧪 Testing & Validation

### Automated Tests

```bash
# Test database connection
python -c "from database_postgres import check_database_health; print(check_database_health())"

# Test data migration
python migrate_sqlite_to_postgres.py

# Test application startup
streamlit run istrominventory.py --server.headless true
```

### Manual Testing Checklist

- [ ] **Authentication** - Login with admin and user accounts
- [ ] **Data Access** - View items, requests, notifications
- [ ] **CRUD Operations** - Create, read, update, delete data
- [ ] **Notifications** - Send and receive notifications
- [ ] **User Management** - Create and manage users
- [ ] **Request Workflow** - Submit, approve, reject requests
- [ ] **Performance** - Page load times and responsiveness

## 🔍 Troubleshooting

### Common Issues

#### 1. Connection Errors
```
Error: connection to server at "localhost" (127.0.0.1), port 5432 failed
```
**Solution**: Check PostgreSQL is running and connection string is correct.

#### 2. Authentication Errors
```
Error: password authentication failed for user "istrom"
```
**Solution**: Verify username and password in connection string.

#### 3. Permission Errors
```
Error: permission denied for table "users"
```
**Solution**: Grant proper permissions to database user.

#### 4. Data Type Errors
```
Error: column "is_read" is of type boolean but expression is of type integer
```
**Solution**: Update data types in migration script.

#### 5. Sequence Errors
```
Error: duplicate key value violates unique constraint
```
**Solution**: Reset sequences after data migration.

### Debug Commands

```bash
# Check database connection
python -c "from database_postgres import get_connection_string; print(get_connection_string())"

# Check table structure
python -c "from database_postgres import get_table_info; print(get_table_info('users'))"

# Check data counts
python -c "from database_postgres import execute_query; print(execute_query('SELECT COUNT(*) FROM users'))"
```

## 📈 Performance Optimization

### Database Indexes

The migration creates optimized indexes:

```sql
-- Performance indexes
CREATE INDEX idx_items_budget ON items(budget);
CREATE INDEX idx_items_section ON items(section);
CREATE INDEX idx_items_building_type ON items(building_type);
CREATE INDEX idx_items_category ON items(category);
CREATE INDEX idx_items_name ON items(name);
CREATE INDEX idx_items_code ON items(code);
CREATE INDEX idx_items_project_site ON items(project_site);
CREATE INDEX idx_requests_status ON requests(status);
CREATE INDEX idx_requests_item_id ON requests(item_id);
CREATE INDEX idx_requests_requested_by ON requests(requested_by);
CREATE INDEX idx_notifications_receiver_read_created ON notifications(receiver_id, is_read, created_at DESC);
CREATE INDEX idx_notifications_sender_created ON notifications(sender_id, created_at DESC);
CREATE INDEX idx_notifications_event_key ON notifications(event_key) WHERE event_key IS NOT NULL;
CREATE INDEX idx_access_logs_timestamp ON access_logs(timestamp);
CREATE INDEX idx_access_logs_username ON access_logs(username);
```

### Connection Pooling

PostgreSQL connection pooling is configured for better performance:

```python
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10
)
```

## 🔒 Security Considerations

### Database Security

- **Connection Encryption** - Use SSL connections in production
- **User Permissions** - Grant minimal required permissions
- **Password Security** - Use strong passwords and environment variables
- **Network Security** - Restrict database access to application servers

### Application Security

- **Input Validation** - All inputs are sanitized
- **SQL Injection Prevention** - Using parameterized queries
- **User Isolation** - Users only see their project data
- **Admin Controls** - Proper admin/user role separation

## 📚 Additional Resources

### Documentation

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Streamlit Documentation](https://docs.streamlit.io/)

### Support

If you encounter issues:

1. **Check logs** - Look for error messages in application logs
2. **Verify configuration** - Ensure environment variables are set correctly
3. **Test connectivity** - Use the debug commands above
4. **Review migration** - Check if data migration completed successfully

## ✅ Migration Checklist

- [ ] PostgreSQL database created and accessible
- [ ] Environment variables configured
- [ ] Database schema bootstrapped
- [ ] Data migrated from SQLite
- [ ] Application code updated
- [ ] All functionality tested
- [ ] Performance optimized
- [ ] Security configured
- [ ] Documentation updated
- [ ] Team trained on new system

## 🎉 Post-Migration

After successful migration:

1. **Backup SQLite database** - Keep as backup
2. **Update documentation** - Reflect new PostgreSQL setup
3. **Train team** - Ensure everyone knows the new system
4. **Monitor performance** - Watch for any issues
5. **Plan maintenance** - Regular backups and updates

The migration is complete! Your application now runs on PostgreSQL with improved performance, security, and scalability.
