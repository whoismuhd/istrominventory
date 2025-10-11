# Istrom Inventory System - Deployment Guide

## 🚀 Cloud Database Setup (PostgreSQL)

### 1. Choose a PostgreSQL Provider

**Recommended Options:**
- **Railway**: Easy setup, free tier available
- **Supabase**: PostgreSQL with additional features
- **Neon**: Serverless PostgreSQL
- **AWS RDS**: Enterprise-grade solution
- **Heroku Postgres**: Simple and reliable

### 2. Database Setup

#### Option A: Railway (Recommended for beginners)
1. Go to [Railway.app](https://railway.app)
2. Create a new project
3. Add PostgreSQL database
4. Copy connection details

#### Option B: Supabase
1. Go to [Supabase.com](https://supabase.com)
2. Create a new project
3. Go to Settings > Database
4. Copy connection details

### 3. Environment Variables

Create a `.env` file in your project root:

```env
# Database Configuration
DATABASE_TYPE=postgresql

# PostgreSQL Configuration
POSTGRES_HOST=your-postgres-host.com
POSTGRES_PORT=5432
POSTGRES_DB=istrominventory
POSTGRES_USER=your-username
POSTGRES_PASSWORD=your-password

# Application Configuration
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
```

### 4. Hosting Platforms

#### Option A: Streamlit Cloud (Recommended)
1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repository
4. Set environment variables in Streamlit Cloud
5. Deploy!

#### Option B: Railway
1. Connect your GitHub repository to Railway
2. Set environment variables
3. Deploy automatically

#### Option C: Heroku
1. Create a `Procfile`:
   ```
   web: streamlit run istrominventory.py --server.port=$PORT --server.address=0.0.0.0
   ```
2. Deploy to Heroku
3. Set environment variables

#### Option D: Render
1. Connect GitHub repository
2. Set environment variables
3. Deploy automatically

### 5. Database Migration

The application will automatically:
- Create all necessary tables
- Migrate data from SQLite (if exists)
- Set up proper indexes and constraints

### 6. Security Considerations

- Use strong passwords for database
- Enable SSL connections
- Set up proper firewall rules
- Regular backups

### 7. Monitoring

- Monitor database performance
- Set up alerts for failures
- Regular health checks
- Backup verification

## 🔧 Local Development

For local development, the app will automatically use SQLite:

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run istrominventory.py
```

## 📊 Database Schema

The application creates the following tables:
- `items`: Inventory items
- `requests`: User requests
- `users`: User accounts
- `notifications`: System notifications
- `actuals`: Actual usage data
- `access_codes`: Access codes
- `access_logs`: User activity logs

## 🚨 Troubleshooting

### Common Issues:

1. **Database Connection Failed**
   - Check environment variables
   - Verify database credentials
   - Ensure database is accessible

2. **Migration Issues**
   - Check database permissions
   - Verify table structure
   - Review error logs

3. **Performance Issues**
   - Monitor database performance
   - Check connection pooling
   - Optimize queries

## 📞 Support

If you encounter issues:
1. Check the logs
2. Verify environment variables
3. Test database connection
4. Review deployment guide

## 🎯 Benefits of PostgreSQL

- **Scalability**: Handles large datasets
- **Reliability**: ACID compliance
- **Performance**: Optimized for production
- **Backup**: Built-in backup solutions
- **Security**: Advanced security features
