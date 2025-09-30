#!/usr/bin/env python3
"""
Update vocabulary applications to use Supabase instead of MySQL
This script updates the existing applications with minimal changes
"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime

class SupabaseAppUpdater:
    """Updates existing vocabulary apps to use Supabase"""
    
    def __init__(self, backup=True):
        self.backup = backup
        self.base_dir = Path(__file__).parent
        self.backup_dir = self.base_dir / f"mysql_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def create_backup(self, file_path: Path):
        """Create backup of original file"""
        if not self.backup:
            return
            
        if not self.backup_dir.exists():
            self.backup_dir.mkdir()
            
        backup_file = self.backup_dir / file_path.name
        shutil.copy2(file_path, backup_file)
        print(f"Backed up {file_path.name} to {backup_file}")
        
    def update_imports(self, content: str) -> str:
        """Update database imports from MySQL to PostgreSQL"""
        replacements = [
            # MySQL connector to psycopg2
            (r'import mysql\.connector', 'import psycopg2\nimport psycopg2.extras'),
            (r'from mysql\.connector import Error', 'from psycopg2 import Error'),
            (r'mysql\.connector\.connect', 'psycopg2.connect'),
            (r'mysql\.connector\.Error', 'psycopg2.Error'),
            
            # Update config imports
            (r'from config import', 'from config_supabase import'),
        ]
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
            
        return content
        
    def update_queries(self, content: str) -> str:
        """Update SQL queries from MySQL to PostgreSQL syntax"""
        replacements = [
            # AUTO_INCREMENT to SERIAL (handled in migration, but for any CREATE statements)
            (r'AUTO_INCREMENT', 'GENERATED ALWAYS AS IDENTITY'),
            
            # MySQL specific functions
            (r'NOW\(\)', 'NOW()'),  # Same in both, but ensure consistency
            (r'CURRENT_TIMESTAMP', 'NOW()'),
            
            # LIMIT/OFFSET syntax (should be compatible)
            # MySQL: LIMIT offset, count -> PostgreSQL: LIMIT count OFFSET offset
            (r'LIMIT (\d+), (\d+)', r'LIMIT \2 OFFSET \1'),
            
            # Placeholder syntax (MySQL: %s, PostgreSQL: %s - same, no change needed)
        ]
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            
        return content
        
    def update_connection_handling(self, content: str) -> str:
        """Update connection handling for PostgreSQL"""
        replacements = [
            # Cursor dictionary mode
            (r'cursor\(dictionary=True\)', 'cursor(cursor_factory=psycopg2.extras.RealDictCursor)'),
            
            # Connection autocommit
            (r'conn\.autocommit = True', 'conn.autocommit = True'),  # Same syntax
            
            # Error handling
            (r'except mysql\.connector\.Error', 'except psycopg2.Error'),
        ]
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
            
        return content
        
    def update_file(self, file_path: Path) -> bool:
        """Update a single Python file"""
        if not file_path.exists():
            print(f"⚠️  File not found: {file_path}")
            return False
            
        print(f"📝 Updating {file_path.name}...")
        
        # Create backup
        self.create_backup(file_path)
        
        # Read current content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Apply updates
        original_content = content
        content = self.update_imports(content)
        content = self.update_queries(content)
        content = self.update_connection_handling(content)
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated {file_path.name}")
            return True
        else:
            print(f"ℹ️  No changes needed for {file_path.name}")
            return False
            
    def update_config_references(self):
        """Update all files to use config_supabase instead of config"""
        files_to_update = [
            'vocabulary_web_app.py',
            'simple_vocab_app.py', 
            'custom_database_manager.py',
            'quiz_system.py',
            'enhanced_quiz_system.py',
            'definition_similarity_calculator.py',
            'modern_pronunciation_system.py',
            'domain_classifier.py',
            'independent_frequency_calculator.py'
        ]
        
        updated_files = []
        
        for filename in files_to_update:
            file_path = self.base_dir / filename
            if self.update_file(file_path):
                updated_files.append(filename)
                
        return updated_files
        
    def create_requirements_update(self):
        """Create updated requirements.txt for PostgreSQL"""
        requirements_content = """# PostgreSQL/Supabase Requirements
psycopg2-binary>=2.9.0
supabase>=1.0.0

# Existing requirements (unchanged)
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
jinja2>=3.1.0
python-multipart>=0.0.6
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
tqdm>=4.65.0
requests>=2.31.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6

# Optional CUDA support (unchanged)
cupy-cuda11x>=12.0.0; platform_system != "Darwin"
cupy-cuda12x>=12.0.0; platform_system != "Darwin"

# Development dependencies
pytest>=7.4.0
black>=23.7.0
isort>=5.12.0
mypy>=1.5.0
flake8>=6.0.0
"""

        requirements_file = self.base_dir / 'requirements_supabase.txt'
        with open(requirements_file, 'w') as f:
            f.write(requirements_content)
            
        print(f"✅ Created {requirements_file}")
        
    def create_environment_template(self):
        """Create .env template for Supabase configuration"""
        env_content = """# Supabase Configuration
# Copy this to .env and fill in your actual values

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-supabase-db-password

# Alternative: Full database URL
# DATABASE_URL=postgresql://postgres:password@localhost:5432/postgres

# Supabase API Configuration
SUPABASE_URL=http://localhost:8000
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# JWT Configuration
JWT_SECRET=your-jwt-secret-here

# Application Settings
APP_ENV=development
DEBUG=true
"""

        env_file = self.base_dir / '.env.template'
        with open(env_file, 'w') as f:
            f.write(env_content)
            
        print(f"✅ Created {env_file}")
        print("   Copy this to .env and update with your Supabase credentials")
        
    def run_update(self):
        """Run the complete update process"""
        print("🚀 Starting Supabase migration for vocabulary apps")
        print("=" * 50)
        
        # Update application files
        updated_files = self.update_config_references()
        
        # Create new requirements
        self.create_requirements_update()
        
        # Create environment template
        self.create_environment_template()
        
        print("\n" + "=" * 50)
        print("✅ Migration preparation complete!")
        print("=" * 50)
        
        if updated_files:
            print(f"📝 Updated files ({len(updated_files)}):")
            for file in updated_files:
                print(f"   • {file}")
        else:
            print("ℹ️  No files needed updates")
            
        if self.backup:
            print(f"\n💾 Backup created in: {self.backup_dir}")
            
        print("\n📋 Next steps:")
        print("1. Install new requirements: pip install -r requirements_supabase.txt")
        print("2. Copy .env.template to .env and configure your Supabase credentials")
        print("3. Run the migration script: python migrate_to_supabase.py --postgres-password YOUR_PASSWORD")
        print("4. Test the applications with: python config_supabase.py")
        print("5. Start your web app: python vocabulary_web_app.py")

def main():
    updater = SupabaseAppUpdater(backup=True)
    updater.run_update()

if __name__ == '__main__':
    main()