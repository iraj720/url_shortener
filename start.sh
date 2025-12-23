#!/bin/bash

# URL Shortener Service - Startup Script
# This script sets up and runs the FastAPI URL shortener service

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python is installed
check_python() {
    print_info "Checking Python installation..."
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.9 or higher."
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
}

# Check if virtual environment exists
check_venv() {
    print_info "Checking virtual environment..."
    if [ ! -d "venv" ]; then
        print_warning "Virtual environment not found. Creating one..."
        python3 -m venv venv
        print_success "Virtual environment created"
    else
        print_success "Virtual environment found"
    fi
}

# Activate virtual environment
activate_venv() {
    print_info "Activating virtual environment..."
    source venv/bin/activate
    print_success "Virtual environment activated"
}

# Install/upgrade dependencies
install_dependencies() {
    print_info "Installing/upgrading dependencies..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt
    print_success "Dependencies installed"
}

# Check if .env file exists
check_env_file() {
    print_info "Checking environment configuration..."
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from sample.env..."
        if [ -f "sample.env" ]; then
            cp sample.env .env
            print_info "SQLite is used by default (no configuration needed!)"
            print_info "Database file will be created at: ./urlshortener.db"
            print_warning "For PostgreSQL, edit .env and set DATABASE_URL"
            read -p "Press Enter to continue after editing .env file..."
        else
            print_error "sample.env file not found. Cannot create .env file."
            exit 1
        fi
    else
        print_success ".env file found"
    fi
}

# Check database configuration
check_database() {
    print_info "Checking database configuration..."
    # Try to import settings and check database URL
    python3 -c "
from app.core.setting import settings
db_url = settings.DATABASE_URL
if 'sqlite' in db_url:
    print('Database: SQLite (file-based)')
    print('Database file:', db_url.split(':///')[-1] if ':///' in db_url else db_url.split('://')[-1])
else:
    print('Database: PostgreSQL')
    print('Database URL:', db_url[:50] + '...')
" 2>/dev/null || {
        print_warning "Could not verify database configuration."
    }
}

# Run database migrations
run_migrations() {
    print_info "Running database migrations..."
    
    # Check if database exists and has tables but no Alembic version (stale state)
    if python3 -c "
from app.core.setting import settings
import sqlite3
import os

if 'sqlite' in settings.DATABASE_URL:
    db_path = settings.DATABASE_URL.split(':///')[-1] if ':///' in settings.DATABASE_URL else settings.DATABASE_URL.split('://')[-1]
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='short_urls'\")
        has_tables = cursor.fetchone() is not None
        cursor.execute(\"SELECT version_num FROM alembic_version\")
        has_version = cursor.fetchone() is not None
        conn.close()
        if has_tables and not has_version:
            print('STALE_STATE')
        else:
            print('OK')
    else:
        print('NO_DB')
else:
    print('OK')
" 2>/dev/null | grep -q "STALE_STATE"; then
        print_warning "Database tables exist but Alembic version is missing."
        print_info "Stamping database with current migration version..."
        if alembic stamp head 2>/dev/null; then
            print_success "Database stamped successfully"
        else
            print_warning "Could not stamp database, will try to run migrations..."
        fi
    fi
    
    if alembic upgrade head 2>/dev/null; then
        print_success "Database migrations completed"
    else
        print_error "Database migrations failed!"
        print_warning "Make sure:"
        if python3 -c "from app.core.setting import settings; print('sqlite' in settings.DATABASE_URL)" 2>/dev/null | grep -q True; then
            print_warning "  1. You have write permissions in the project directory"
            print_warning "  2. Disk space is available"
            print_warning "  3. Database file is not corrupted"
        else
            print_warning "  1. PostgreSQL is running"
            print_warning "  2. Database exists"
            print_warning "  3. DATABASE_URL in .env is correct"
            print_warning "  4. User has proper permissions"
        fi
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Find an available port between 8000 and 8100
find_available_port() {
    local start_port=8000
    local end_port=8100
    local port=$start_port
    
    # Print info to stderr so it doesn't interfere with stdout (port number)
    print_info "Checking for available port between $start_port and $end_port..." >&2
    
    while [ $port -le $end_port ]; do
        # Check if port is available using netstat (Linux) or lsof (macOS)
        if command -v lsof &> /dev/null; then
            # macOS/Linux with lsof
            if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
                echo $port
                return 0
            fi
        elif command -v netstat &> /dev/null; then
            # Linux with netstat
            if ! netstat -tuln 2>/dev/null | grep -q ":$port "; then
                echo $port
                return 0
            fi
        else
            # Fallback: try to bind to the port using Python
            if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.1)
try:
    s.bind(('127.0.0.1', $port))
    s.close()
    print('$port')
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
                echo $port
                return 0
            fi
        fi
        port=$((port + 1))
    done
    
    print_error "No available port found between $start_port and $end_port" >&2
    return 1
}

# Start the FastAPI server
start_server() {
    # Find an available port
    SERVER_PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        print_error "Failed to find an available port"
        exit 1
    fi
    
    print_success "Found available port: $SERVER_PORT"
    echo ""
    print_info "Starting FastAPI server on port $SERVER_PORT..."
    print_success "Server will be available at:"
    print_success "  - API: http://localhost:$SERVER_PORT"
    print_success "  - Docs: http://localhost:$SERVER_PORT/docs"
    print_success "  - ReDoc: http://localhost:$SERVER_PORT/redoc"
    echo ""
    print_info "Press Ctrl+C to stop the server"
    echo ""
    
    # Start uvicorn with reload for development
    uvicorn app.main:app --host 0.0.0.0 --port $SERVER_PORT --reload
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  URL Shortener Service - Startup"
    echo "=========================================="
    echo ""
    
    # Check prerequisites
    check_python
    check_venv
    activate_venv
    install_dependencies
    check_env_file
    check_database
    
    # Ask about migrations
    echo ""
    read -p "Run database migrations? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        run_migrations
    else
        print_warning "Skipping database migrations"
    fi
    
    # Start server
    echo ""
    start_server
}

# Run main function
main

