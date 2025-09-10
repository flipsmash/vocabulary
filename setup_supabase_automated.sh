#!/bin/bash
set -e

echo "============================================"
echo "🚀 AUTOMATED SUPABASE SETUP FOR WSL2"
echo "============================================"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    echo "⏳ Waiting for $service_name to be ready on port $port..."
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z localhost $port 2>/dev/null; then
            echo "✅ $service_name is ready!"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts - waiting 2 seconds..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name failed to start after $max_attempts attempts"
    return 1
}

echo "🔧 Step 1: Installing required packages..."
# Update system
sudo apt update -qq

# Install required packages
sudo apt install -y curl wget git netcat-openbsd postgresql-client python3-pip

# Install Docker if not present
if ! command_exists docker; then
    echo "📦 Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "⚠️  Docker installed - you may need to restart your WSL2 session after this script"
fi

# Install Docker Compose if not present
if ! command_exists docker-compose; then
    echo "📦 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Install Python packages for migration
echo "🐍 Installing Python packages..."
pip3 install --user psycopg2-binary mysql-connector-python pandas tqdm

echo ""
echo "🗂️  Step 2: Setting up directories..."
# Clean up any existing setup
cd ~/
rm -rf supabase-setup vocabulary-migration 2>/dev/null || true

# Create fresh directories
mkdir -p supabase-setup/volumes/{db,storage,api}
mkdir -p vocabulary-migration
cd supabase-setup

echo ""
echo "🐳 Step 3: Creating Docker configuration..."

# Create docker-compose.yml
cat > docker-compose.yml << 'COMPOSE_EOF'
version: '3.8'

services:
  db:
    image: postgres:15
    container_name: supabase_db
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: supabase123
      POSTGRES_INITDB_ARGS: --auth-host=scram-sha-256 --auth-local=scram-sha-256
    volumes:
      - db_data:/var/lib/postgresql/data
    command: >
      postgres
      -c log_min_messages=WARNING
      -c shared_buffers=1GB
      -c effective_cache_size=3GB
      -c work_mem=64MB
      -c maintenance_work_mem=512MB
      -c max_connections=200
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100
      -c random_page_cost=1.1
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  studio:
    image: supabase/studio:20240101-ce42139
    container_name: supabase_studio
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      SUPABASE_URL: http://localhost:8000
      SUPABASE_PUBLIC_URL: http://localhost:8000
      SUPABASE_ANON_KEY: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIiwiZXhwIjoxOTgzODEyOTk2fQ.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
      SUPABASE_SERVICE_KEY: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJzZXJ2aWNlX3JvbGUiLCJleHAiOjE5ODM4MTI5OTZ9.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
      DEFAULT_ORGANIZATION: Vocabulary App
      DEFAULT_PROJECT: vocabulary-db
    depends_on:
      db:
        condition: service_healthy

  kong:
    image: kong:2.8.1
    container_name: supabase_kong
    restart: unless-stopped
    ports:
      - "8000:8000"
      - "8443:8443"
    environment:
      KONG_DATABASE: "off"
      KONG_DECLARATIVE_CONFIG: /home/kong/kong.yml
      KONG_DNS_ORDER: LAST,A,CNAME
      KONG_PLUGINS: request-transformer,cors,key-auth,acl
      KONG_NGINX_PROXY_PROXY_BUFFER_SIZE: 160k
      KONG_NGINX_PROXY_PROXY_BUFFERS: 64 160k
    volumes:
      - ./volumes/api/kong.yml:/home/kong/kong.yml:ro
    depends_on:
      - rest
      - auth

  rest:
    image: postgrest/postgrest:v10.1.1
    container_name: supabase_rest
    restart: unless-stopped
    environment:
      PGRST_DB_URI: postgres://postgres:supabase123@db:5432/postgres
      PGRST_DB_SCHEMAS: public
      PGRST_DB_ANON_ROLE: anon
      PGRST_JWT_SECRET: your-super-secret-jwt-token-with-at-least-32-characters-long
      PGRST_DB_USE_LEGACY_GUCS: "false"
    depends_on:
      db:
        condition: service_healthy

  auth:
    image: supabase/gotrue:v2.99.0
    container_name: supabase_auth
    restart: unless-stopped
    environment:
      GOTRUE_API_HOST: 0.0.0.0
      GOTRUE_API_PORT: 9999
      GOTRUE_DB_DRIVER: postgres
      GOTRUE_DB_DATABASE_URL: postgres://postgres:supabase123@db:5432/postgres
      GOTRUE_SITE_URL: http://localhost:3000
      GOTRUE_URI_ALLOW_LIST: ""
      GOTRUE_DISABLE_SIGNUP: "false"
      GOTRUE_JWT_ADMIN_ROLES: service_role
      GOTRUE_JWT_AUD: authenticated
      GOTRUE_JWT_DEFAULT_GROUP_NAME: authenticated
      GOTRUE_JWT_EXP: 3600
      GOTRUE_JWT_SECRET: your-super-secret-jwt-token-with-at-least-32-characters-long
      GOTRUE_EXTERNAL_EMAIL_ENABLED: "true"
      GOTRUE_MAILER_AUTOCONFIRM: "true"
    depends_on:
      db:
        condition: service_healthy

volumes:
  db_data:
COMPOSE_EOF

# Create Kong configuration
mkdir -p volumes/api
cat > volumes/api/kong.yml << 'KONG_EOF'
_format_version: "1.1"

consumers:
  - username: anon
    keyauth_credentials:
      - key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIiwiZXhwIjoxOTgzODEyOTk2fQ.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
  - username: service_role
    keyauth_credentials:
      - key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJzZXJ2aWNlX3JvbGUiLCJleHAiOjE5ODM4MTI5OTZ9.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU

acls:
  - consumer: anon
    group: anon
  - consumer: service_role
    group: admin

services:
  - name: auth-v1
    url: http://auth:9999/
    routes:
      - name: auth-v1-all
        strip_path: true
        paths:
          - /auth/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: rest-v1
    url: http://rest:3000/
    routes:
      - name: rest-v1-all
        strip_path: true
        paths:
          - /rest/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: true
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon
KONG_EOF

echo ""
echo "🚀 Step 4: Starting Supabase services..."

# Stop any existing containers
docker-compose down 2>/dev/null || true
docker system prune -f

# Start services
echo "   Starting containers..."
docker-compose up -d

echo ""
echo "⏳ Step 5: Waiting for services to start..."

# Wait for PostgreSQL
wait_for_service "PostgreSQL" 5432

# Wait for API Gateway
wait_for_service "Kong API Gateway" 8000

# Wait for Studio
wait_for_service "Supabase Studio" 3000

echo ""
echo "🧪 Step 6: Testing database connection..."
if docker exec supabase_db psql -U postgres -d postgres -c "SELECT version();" > /dev/null 2>&1; then
    echo "✅ Database connection successful!"
else
    echo "❌ Database connection failed!"
    exit 1
fi

echo ""
echo "📝 Step 7: Creating connection info file..."
cat > ~/vocabulary-migration/connection_info.txt << 'INFO_EOF'
================================================
🎉 SUPABASE SETUP COMPLETE!
================================================

🌐 Access URLs:
   Supabase Studio: http://localhost:3000
   API Gateway:     http://localhost:8000
   PostgreSQL:      localhost:5432

🔑 Database Credentials:
   Host:     localhost
   Port:     5432
   Database: postgres
   Username: postgres
   Password: supabase123

🔧 API Keys:
   Anon Key:     eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIiwiZXhwIjoxOTgzODEyOTk2fQ.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
   Service Key:  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJzZXJ2aWNlX3JvbGUiLCJleHAiOjE5ODM4MTI5OTZ9.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU

📋 Next Steps:
   1. Run the migration: 
      python migrate_to_supabase.py --postgres-password supabase123
   
   2. Validate the migration:
      python validate_migration.py --postgres-password supabase123

💡 Management Commands:
   Stop:    cd ~/supabase-setup && docker-compose down
   Start:   cd ~/supabase-setup && docker-compose up -d
   Logs:    cd ~/supabase-setup && docker-compose logs -f
   Status:  cd ~/supabase-setup && docker-compose ps

Generated: $(date)
INFO_EOF

# Display the connection info
cat ~/vocabulary-migration/connection_info.txt

echo ""
echo "============================================"
echo "✅ SUPABASE IS READY FOR MIGRATION!"
echo "============================================"
echo ""
echo "🎯 Run this command to start the migration:"
echo "   python migrate_to_supabase.py --postgres-password supabase123"
echo ""