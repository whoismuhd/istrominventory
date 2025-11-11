"""
Comprehensive test runner for all tests
Run with: pytest tests/ -v
"""
import pytest
import sys
import os

if __name__ == "__main__":
    # Run all tests
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    sys.exit(exit_code)

