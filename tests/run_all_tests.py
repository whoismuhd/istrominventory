#!/usr/bin/env python3
"""
Comprehensive Test Suite Runner for Istrom Inventory Management System
Run all tests: python tests/run_all_tests.py
Run specific test: pytest tests/test_database.py -v
"""
import sys
import os
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_tests():
    """Run all tests with pytest"""
    print("🧪 Running Istrom Inventory Test Suite")
    print("=" * 60)
    
    # Run pytest with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=istrominventory",
        "--cov=modules",
        "--cov=db",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov"
    ]
    
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("\n" + "=" * 60)
    if result.returncode == 0:
        print("✅ All tests passed!")
        print("📊 Coverage report generated in htmlcov/index.html")
    else:
        print("❌ Some tests failed")
    
    return result.returncode == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

