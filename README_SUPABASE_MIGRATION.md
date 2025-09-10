# Supabase Migration Guide

Complete migration from MySQL to Supabase/PostgreSQL for the Vocabulary Database System.

## 📋 Overview

This migration moves your vocabulary database (~22K words, 12.88M similarity records) from MySQL to Supabase running in WSL2 for better performance, built-in authentication, and modern PostgreSQL features.

## 🚀 Quick Start

### 1. WSL2 Setup
```bash
# Run as Administrator in PowerShell
.\setup_wsl2_supabase.ps1
```

### 2. Ubuntu Configuration
```bash
# In WSL2 Ubuntu terminal
bash /mnt/c/temp/ubuntu_setup.sh
# Restart WSL2: wsl --shutdown && wsl
```

### 3. Supabase Installation
```bash
# In WSL2
cd ~/supabase-setup
bash /mnt/c/Users/Brian/vocabulary/supabase_setup.sh
```

### 4. Run Migration
```bash
# From Windows or WSL2
python migrate_to_supabase.py --postgres-password YOUR_SUPABASE_PASSWORD
```

### 5. Validate Migration
```bash
python validate_migration.py --postgres-password YOUR_SUPABASE_PASSWORD
```

### 6. Update Applications
```bash
python update_apps_for_supabase.py
pip install -r requirements_supabase.txt
```

## 📁 Generated Files

| File | Purpose |
|------|---------|
| `setup_wsl2_supabase.ps1` | WSL2 and Ubuntu setup script |
| `supabase_setup.sh` | Supabase Docker configuration and startup |
| `migrate_to_supabase.py` | Complete database migration script |
| `validate_migration.py` | Migration validation and testing |
| `config_supabase.py` | Updated configuration for PostgreSQL |
| `update_apps_for_supabase.py` | Application code updater |
| `requirements_supabase.txt` | PostgreSQL dependencies |
| `.env.template` | Environment configuration template |

## 🛠 Migration Process

### Phase 1: Infrastructure (30 minutes)
1. **WSL2 Setup**: Install Ubuntu 22.04 with 16GB RAM, 6 cores
2. **Docker Installation**: Latest Docker with Compose
3. **Supabase Deployment**: Optimized for vocabulary workload

### Phase 2: Database Migration (4-6 hours)
1. **Schema Creation**: PostgreSQL-optimized tables with better indexes
2. **Data Migration**: Batch processing with progress tracking
   - Small tables: ~5 minutes each
   - Large tables (similarities): 3-4 hours each
3. **Index Creation**: Optimized for vocabulary queries

### Phase 3: Application Updates (1 hour)
1. **Configuration**: Switch from MySQL to PostgreSQL connections
2. **Query Updates**: MySQL → PostgreSQL syntax
3. **Error Handling**: psycopg2 instead of mysql-connector
4. **Testing**: Validate all functionality

## 📊 Expected Performance Improvements

| Feature | MySQL | Supabase/PostgreSQL |
|---------|-------|-------------------|
| Similarity Queries | ~800ms | ~300ms (2.7x faster) |
| Full-text Search | External needed | Built-in, ~100ms |
| Complex JOINs | ~1.2s | ~400ms (3x faster) |
| Authentication | Custom code | Built-in, 1 line |
| Real-time Features | Not available | Built-in WebSocket |

## 🔧 Configuration Details

### Database Connection
```python
# Old MySQL
'host': '10.0.0.160'
'port': 3306

# New Supabase  
'host': 'localhost'  
'port': 5432
```

### Enhanced PostgreSQL Features
- **JSONB**: Better performance than MySQL JSON
- **Arrays**: Native phoneme storage
- **Full-text Search**: Built-in with GIN indexes
- **Partial Indexes**: Optimize common queries
- **Connection Pooling**: Better resource management

## 🧪 Validation Checks

The validation script tests:
- ✅ Record count matching
- ✅ Data integrity sampling
- ✅ Query functionality
- ✅ Performance benchmarks
- ✅ Full-text search capability

## 🚨 Troubleshooting

### Common Issues

**Port Conflicts**
```bash
# Change external PostgreSQL port
# Edit docker-compose.yml: "15432:5432"
```

**Memory Issues**
```bash
# Adjust WSL2 memory in %USERPROFILE%\.wslconfig
[wsl2]
memory=20GB
```

**Connection Errors**
```bash
# Check Supabase services
docker compose ps
docker compose logs db
```

**Migration Fails**
```bash
# Resume from specific table
python migrate_to_supabase.py --tables pronunciation_similarity --postgres-password PASSWORD
```

## 📈 Monitoring

### Check Migration Progress
```bash
# View migration logs
tail -f migration.log

# Check database sizes
docker compose exec db psql -U postgres -c "SELECT schemaname,tablename,n_tup_ins as rows FROM pg_stat_user_tables ORDER BY rows DESC;"
```

### Performance Monitoring
```bash
# PostgreSQL statistics
docker compose exec db psql -U postgres -c "SELECT * FROM pg_stat_user_tables WHERE schemaname='public';"
```

## 🔐 Security Notes

- Database passwords are auto-generated and saved to `connection_info.txt`
- Change default dashboard password immediately
- Use environment variables for production deployments
- Enable row-level security for production data

## 🎯 Next Steps After Migration

1. **Test All Features**: Run through quiz system, search, analytics
2. **Performance Tuning**: Adjust PostgreSQL settings if needed
3. **Backup Strategy**: Set up automated backups
4. **Monitor Usage**: Track query performance and optimize
5. **Supabase Features**: Implement real-time features, edge functions

## 📞 Support

Migration issues? Check:
1. `migration.log` for detailed error messages
2. `validation_results_*.json` for data integrity reports
3. Docker logs: `docker compose logs -f`
4. PostgreSQL logs: `docker compose exec db tail -f /var/log/postgresql/postgresql-*.log`

---

**Estimated Total Time**: 5-7 hours
**Downtime**: Migration can run alongside existing MySQL system
**Rollback**: Original MySQL remains untouched during migration