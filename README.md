# Istrom Inventory Management System

A comprehensive Streamlit-based inventory management system for tracking materials and labour across construction project sites.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Database](#database)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Known Issues & Fixes](#known-issues--fixes)

## 🚀 Quick Start

1. **Install Python 3.9+**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app:**
   ```bash
   streamlit run istrominventory.py
   ```

4. **Access in browser:**
   - The app will open at `http://localhost:8501`
   - Use access codes to log in (admin or project site codes)

## ✨ Features

### Core Functionality
- **Inventory Management**: Track materials and labour items with quantities, costs, and categories
- **Request System**: Submit, approve, and reject material/labour requests
- **Multi-Project Support**: Manage inventory across multiple project sites
- **User Management**: Admin and project site account types
- **Notifications**: Real-time notifications for request status changes
- **Data Import**: Import items from Excel/CSV files with column mapping
- **Reporting**: View request history, statistics, and analytics

### User Roles
- **Admin**: Full access to all features, can approve/reject requests, manage users
- **Project Site**: Can view inventory, make requests, view notifications

## 💾 Installation

### Prerequisites
- Python 3.9 or higher
- pip (Python package manager)

### Steps

1. **Clone or download the repository**

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables (optional):**
   - Copy `env.example` to `.env`
   - Configure `DATABASE_URL` if using PostgreSQL (otherwise SQLite is used)

5. **Run the application:**
   ```bash
   streamlit run istrominventory.py
   ```

## 🎯 Usage

### Application Tabs

1. **Import / Setup**
   - Upload Excel/CSV files
   - Map columns to inventory fields
   - Import materials and labour separately

2. **Inventory**
   - View all inventory items
   - Filter by project site, category, search term
   - Edit individual items (quantity, unit cost)
   - View totals and statistics

3. **Make Request**
   - Create new material/labour requests
   - Select items, quantities, and project sites
   - Add notes and specifications

4. **Review & History** (Admin)
   - View pending requests
   - Approve or reject requests
   - View request history and statistics

5. **Notifications** (Project Site)
   - View unread and read notifications
   - See request status updates

### Data Import Notes
- Import materials and labour separately (choose "Treat rows as" accordingly)
- If your Excel has multiple sheets, export the sheet you need and import
- Column mapping allows flexibility in source file formats

## 🗄️ Database

### Default Configuration
- **Local Development**: SQLite database (`istrominventory.db`)
- **Production**: PostgreSQL (via `DATABASE_URL` environment variable)

### Database Schema
- **Items**: code, name, category (materials/labour), unit, qty, unit_cost, project_site
- **Requests**: item_id, requested_by, qty, status, created_at, updated_at
- **Users**: username, full_name, user_type, project_site
- **Notifications**: user_id, request_id, notification_type, read_status
- **Access Logs**: access_code, user_name, access_time, success, role

### Database Operations
- Database connection is handled by `db.py`
- Schema initialization via `schema_init.py`
- Automatic migrations for schema updates

### Database Migration (SQLite to PostgreSQL)

If migrating from SQLite to PostgreSQL:

1. **Set up PostgreSQL database** on your hosting provider (e.g., Render.com)

2. **Configure environment variable:**
   ```bash
   DATABASE_URL=postgresql://user:password@host:port/database
   ```

3. **Run migration script:**
   ```bash
   python scripts/migrate_sqlite_to_pg.py
   ```

4. **Verify migration:**
   - Check all tables have data
   - Verify user accounts work
   - Test request workflow

## 🏗️ Architecture

### Current Structure
The application is currently in a transition phase:
- **Main File**: `istrominventory.py` (~11,700 lines) - monolithic but functional
- **Modules**: Authentication module extracted to `modules/auth.py`
- **Database**: Unified connection via `db.py`
- **Logging**: Centralized via `logger.py`

### Project Structure
```
istrominventory/
├── istrominventory.py      # Main application file
├── db.py                   # Database connection module
├── logger.py               # Logging module
├── schema_init.py          # Database schema initialization
├── modules/
│   ├── auth.py             # Authentication and session management
│   └── ui/                 # UI components (future)
├── scripts/                # Utility scripts
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Refactoring Status
- ✅ Authentication module extracted
- ✅ Database connection consolidated
- ✅ Logging infrastructure in place
- ✅ Critical print statements replaced with logging
- ⏳ Further modularization in progress

### Module Responsibilities

#### `modules/auth.py` - Authentication
- User authentication and session management
- Access code validation
- Session persistence (24-hour login)
- Login/logout functionality

#### `db.py` - Database Connection
- Unified database connection management
- Supports both SQLite and PostgreSQL
- Connection pooling and error handling
- Proper logging

#### `logger.py` - Logging
- Centralized logging system
- File and console output
- Configurable log levels

## 🚢 Deployment

### Local Development
```bash
streamlit run istrominventory.py
```

### Production Deployment (Render.com)

#### Pre-Deployment Checklist
- [ ] PostgreSQL database created on Render
- [ ] Database connection string obtained
- [ ] Environment variables configured
- [ ] Database permissions verified
- [ ] All SQLite dependencies removed (if migrating)
- [ ] Application code updated
- [ ] Local testing completed

#### Deployment Steps

1. **Update `render.yaml`**:
```yaml
services:
  - type: web
    name: istrominventory
    env: python
    buildCommand: pip install -r requirements.txt && python schema_init.py
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

2. **Set environment variables:**
   - `DATABASE_URL`: PostgreSQL connection string
   - `PRODUCTION_MODE`: Set to `true`

3. **Push to GitHub:**
   ```bash
   git add -A
   git commit -m "Deploy to production"
   git push origin main
   ```

4. **Monitor deployment:**
   - Check Render logs for errors
   - Verify database connection
   - Test application functionality

#### Post-Deployment Verification
- [ ] Application loads successfully
- [ ] Database connection established
- [ ] User authentication works
- [ ] All pages load correctly
- [ ] CRUD operations work
- [ ] Notifications system works

### Docker (Optional)
```bash
docker-compose up
```

## 🔧 Development

### Code Organization
- **Main Application**: `istrominventory.py`
- **Modules**: `modules/` directory for extracted functionality
- **Database**: `db.py` for all database operations
- **Logging**: `logger.py` for centralized logging

### Adding New Features
1. For authentication-related features: Add to `modules/auth.py`
2. For database operations: Use `db.py` for connections
3. For logging: Use `logger.py` functions

### Code Quality
- Use the logging module for all log messages (not `print()`)
- Use `db.py` for all database operations
- Follow existing code structure
- Test changes thoroughly before committing

## 🧪 Testing

The application includes a comprehensive test suite with unit tests and integration tests.

### Quick Start

```bash
# Install test dependencies (already in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=istrominventory --cov-report=html
```

### Test Structure

- **Unit Tests**: Test individual functions (`test_database.py`, `test_auth.py`, `test_inventory.py`, etc.)
- **Integration Tests**: Test component interactions (`test_integration.py`)
- **Coverage**: Target 70%+ code coverage

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_database.py -v

# With coverage
pytest tests/ --cov=istrominventory --cov-report=html

# Unit tests only
pytest tests/ -m unit -v

# Integration tests only
pytest tests/ -m integration -v
```

### Test Coverage

Current test coverage includes:
- ✅ Database operations (connection, initialization, queries)
- ✅ Authentication (access codes, user authentication)
- ✅ Inventory management (item retrieval, summary data)
- ✅ Request management (CRUD operations, status updates)
- ✅ Notifications (retrieval, management)
- ✅ Integration tests (component interactions)

For detailed testing documentation, see [TESTING.md](TESTING.md).

## 🐛 Troubleshooting

### Database Connection Issues
- **Problem**: Connection to server failed
- **Solution**: 
  - Check `DATABASE_URL` environment variable
  - Verify database credentials
  - Check network connectivity (for PostgreSQL)
  - Ensure SSL mode is set correctly for PostgreSQL

### Table Does Not Exist
- **Problem**: `relation "users" does not exist`
- **Solution**: Run `python schema_init.py` to initialize database schema

### Import Issues
- **Problem**: Data import fails or shows incorrect data
- **Solution**:
  - Ensure Excel/CSV format matches expected structure
  - Check column mapping during import
  - Verify data types match expected formats
  - Import materials and labour separately

### Session Issues
- **Problem**: App logs out on browser refresh
- **Solution**:
  - Clear browser cache and cookies
  - Check browser console for errors
  - Verify session persistence settings
  - Check `localStorage` in browser DevTools

### Cache Issues
- **Problem**: Data not updating after changes
- **Solution**:
  - Clear browser cache
  - Check if cache clearing functions are working
  - Verify database updates are committed

### Module Import Errors
- **Problem**: `ModuleNotFoundError` or import errors
- **Solution**:
  - Verify all dependencies are installed: `pip install -r requirements.txt`
  - Check Python version (3.9+ required)
  - Verify file structure matches expected layout

## 🔍 Known Issues & Fixes

### Critical Bug Fixed: Cache Key Issue in df_requests()

**Problem:**
The `df_requests()` function was cached, but when called without explicit `user_type` and `project_site` parameters, it would read these from `st.session_state` inside the function. However, Streamlit's cache key is based on function parameters, not session state values accessed inside.

**Impact:**
- Admin calls `df_requests(status=None)` → caches result with key `(None, None, None)`
- Project site user calls `df_requests(status=None)` → cache hit returns admin's data (ALL requests) instead of just their project site's requests
- This caused incorrect data to be displayed to project site users

**Solution:**
- Updated `df_requests()` to always explicitly use `user_type` and `project_site` in cache keys
- Fixed all calls to `df_requests()` to explicitly pass `user_type` and `project_site` parameters

### Deprecated Files

The following files have been deprecated and removed:
- `database_config.py` - Use `db.py` instead
- `database_postgres.py` - Use `db.py` instead
- `database.py` - Not used, removed
- `auth.py` (root) - Use `modules/auth.py` instead
- `main.py` (old version) - Not used, removed

**Migration:**
All database operations should import from `db.py`:
```python
from db import get_engine, init_db
```

## 🔒 Security

- Access code-based authentication
- Session management with 24-hour timeout
- Role-based access control (Admin vs Project Site)
- Secure database connections (SSL for PostgreSQL)
- Input validation on all forms
- SQL injection prevention via parameterized queries

## 📊 Performance

- Database connection pooling
- Cached queries for frequently accessed data
- Optimized database operations
- Efficient session management
- Connection timeout and retry logic

## 📝 Notes

- **Import Process**: Import materials and labour separately (choose "Treat rows as" accordingly)
- **Multiple Sheets**: If your Excel has multiple sheets, export the sheet you need and import
- **Session Persistence**: Sessions persist for 24 hours across browser refreshes
- **Database**: SQLite is used by default; PostgreSQL for production
- **Logging**: All logs are written to `app.log` and console

## 🤝 Contributing

1. Follow the existing code structure
2. Use the logging module for all log messages
3. Use `db.py` for all database operations
4. Test changes thoroughly before committing
5. Update documentation as needed

## 📄 License

This project is proprietary software for Istrom Inventory Management.

## 🎉 Status

**The application provides:**
- ✅ **Full Functionality** - All features working
- ✅ **Well Organized** - Modular structure (in progress)
- ✅ **Production Ready** - Optimized for deployment
- ✅ **Maintainable** - Easy to update and extend
- ✅ **Scalable** - Ready for future growth
- ✅ **Error-Free** - All critical bugs fixed
- ✅ **Clean Codebase** - Redundant files removed

## 📞 Support

For questions or issues:
- Check this README for common solutions
- Review error logs in `app.log`
- Contact the development team

---

**Last Updated**: November 2024  
**Version**: 1.0  
**Status**: Production Ready ✅
