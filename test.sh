#!/bin/bash

# URL Shortener Service - Test Runner Script
# This script runs all tests for the URL shortener service

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

# Check if virtual environment exists
check_venv() {
    if [ ! -d "venv" ]; then
        print_error "Virtual environment not found. Please run ./start.sh first."
        exit 1
    fi
}

# Activate virtual environment
activate_venv() {
    source venv/bin/activate
}

# Install test dependencies
install_test_deps() {
    print_info "Installing test dependencies..."
    pip install -q pytest pytest-asyncio httpx pytest-cov pytest-benchmark
    print_success "Test dependencies installed"
}

# Run unit tests
run_unit_tests() {
    print_info "Running unit tests..."
    if pytest tests/ -v --tb=short; then
        print_success "Unit tests passed"
        return 0
    else
        print_error "Unit tests failed"
        return 1
    fi
}

# Run tests with coverage
run_tests_with_coverage() {
    print_info "Running tests with coverage..."
    if pytest tests/ --cov=app --cov-report=html --cov-report=term-missing; then
        print_success "Tests with coverage completed"
        print_info "Coverage report generated in htmlcov/index.html"
        return 0
    else
        print_error "Tests failed"
        return 1
    fi
}

# Run load tests
run_load_tests() {
    print_info "Running load tests..."
    print_warning "Make sure the server is running on http://localhost:8000"
    read -p "Press Enter to continue..."
    
    if pytest tests/test_load.py -v -s; then
        print_success "Load tests completed"
        return 0
    else
        print_error "Load tests failed"
        return 1
    fi
}

# Run all tests
run_all_tests() {
    print_info "Running all tests..."
    run_unit_tests
    local unit_result=$?
    
    if [ $unit_result -eq 0 ]; then
        print_success "All tests passed!"
        return 0
    else
        print_error "Some tests failed"
        return 1
    fi
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  URL Shortener Service - Test Runner"
    echo "=========================================="
    echo ""
    
    check_venv
    activate_venv
    install_test_deps
    
    # Parse command line arguments
    case "${1:-all}" in
        unit)
            run_unit_tests
            ;;
        coverage)
            run_tests_with_coverage
            ;;
        load)
            run_load_tests
            ;;
        all)
            run_all_tests
            ;;
        *)
            echo "Usage: $0 [unit|coverage|load|all]"
            echo ""
            echo "Options:"
            echo "  unit      - Run unit tests only"
            echo "  coverage  - Run tests with coverage report"
            echo "  load      - Run load/performance tests"
            echo "  all       - Run all tests (default)"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"

