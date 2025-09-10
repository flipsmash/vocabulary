#!/bin/bash
set -e

echo "==============================================="
echo "🚀 FINAL WORKING POSTGRES SETUP FOR WSL2"
echo "==============================================="

# Kill any existing containers
echo "🧹 Cleaning up existing containers..."
docker stop vocab_postgres 2>/dev/null || true
docker rm vocab_postgres 2>/dev/null || true
docker volume prune -f

# Create directory
echo "📁 Creating setup directory..."
cd ~/
rm -rf postgres-final
mkdir postgres-final
cd postgres-final

# Create docker-compose.yml using echo (no heredoc bullshit)
echo "📝 Creating docker-compose.yml..."
echo "version: '3.8'" > docker-compose.yml
echo "services:" >> docker-compose.yml
echo "  postgres:" >> docker-compose.yml
echo "    image: postgres:15" >> docker-compose.yml
echo "    container_name: vocab_postgres" >> docker-compose.yml
echo "    restart: unless-stopped" >> docker-compose.yml
echo "    environment:" >> docker-compose.yml
echo "      POSTGRES_DB: postgres" >> docker-compose.yml
echo "      POSTGRES_USER: postgres" >> docker-compose.yml
echo "      POSTGRES_PASSWORD: supabase123" >> docker-compose.yml
echo "    ports:" >> docker-compose.yml
echo "      - \"5432:5432\"" >> docker-compose.yml
echo "    volumes:" >> docker-compose.yml
echo "      - postgres_data:/var/lib/postgresql/data" >> docker-compose.yml
echo "" >> docker-compose.yml
echo "volumes:" >> docker-compose.yml
echo "  postgres_data:" >> docker-compose.yml

# Show what we created
echo "✅ Created docker-compose.yml:"
cat docker-compose.yml

# Start PostgreSQL
echo "🐘 Starting PostgreSQL..."
docker compose up -d

# Wait for it to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec vocab_postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    echo "   Waiting... attempt $i/30"
    sleep 2
done

# Test the connection
echo "🧪 Testing database connection..."
if docker exec vocab_postgres psql -U postgres -d postgres -c "SELECT version();" 2>/dev/null | grep -q "PostgreSQL"; then
    echo "✅ Database connection successful!"
    
    # Show connection info
    echo ""
    echo "==============================================="
    echo "🎉 POSTGRESQL IS READY!"
    echo "==============================================="
    echo "Database: localhost:5432"
    echo "Username: postgres"
    echo "Password: supabase123"
    echo ""
    echo "🚀 NOW RUN THE MIGRATION:"
    echo "cd /mnt/c/Users/Brian/vocabulary"
    echo "python migrate_to_supabase.py --postgres-password supabase123"
    echo "==============================================="
    
    # Save info to file
    echo "localhost:5432 postgres supabase123" > ~/postgres_connection.txt
    echo "📄 Connection info saved to ~/postgres_connection.txt"
    
else
    echo "❌ Database connection failed!"
    echo "Container logs:"
    docker compose logs
    exit 1
fi

# Show running containers
echo ""
echo "🐳 Running containers:"
docker compose ps

echo ""
echo "💡 Management commands:"
echo "Stop:  cd ~/postgres-final && docker compose down"
echo "Start: cd ~/postgres-final && docker compose up -d"
echo "Logs:  cd ~/postgres-final && docker compose logs -f"