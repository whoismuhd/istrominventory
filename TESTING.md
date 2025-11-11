# Testing Guide for Istrom Inventory Management System

## 🧪 Test Suite Overview

The application now includes a comprehensive test suite with unit tests and integration tests.

### Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures and configuration
├── test_database.py         # Database operation tests
├── test_auth.py             # Authentication tests
├── test_inventory.py        # Inventory management tests
├── test_requests.py         # Request management tests
├── test_notifications.py    # Notification system tests
├── test_integration.py      # Integration tests
├── test_utils.py            # Utility function tests
├── run_tests.py             # Test runner
└── run_all_tests.py         # Comprehensive test runner with coverage
```

## 📦 Installation

Install test dependencies:

```bash
pip install -r requirements.txt
```

This will install:
- `pytest>=7.4.0` - Testing framework
- `pytest-cov>=4.1.0` - Coverage reporting

## 🚀 Running Tests

### Run All Tests

```bash
# Using pytest directly
pytest tests/ -v

# Using the test runner script
python tests/run_all_tests.py

# With coverage report
pytest tests/ --cov=istrominventory --cov-report=html
```

### Run Specific Test Files

```bash
# Database tests
pytest tests/test_database.py -v

# Authentication tests
pytest tests/test_auth.py -v

# Integration tests
pytest tests/test_integration.py -v
```

### Run Tests by Category

```bash
# Unit tests only
pytest tests/ -m unit -v

# Integration tests only
pytest tests/ -m integration -v
```

### Generate Coverage Report

```bash
pytest tests/ --cov=istrominventory --cov=modules --cov=db --cov-report=html
# Open htmlcov/index.html in browser
```

## 📊 Test Coverage

Current test coverage includes:

### ✅ Unit Tests
- **Database Operations**: Connection, initialization, table existence
- **Authentication**: Access codes, user authentication, session management
- **Inventory**: Item retrieval, summary data, constants validation
- **Requests**: Request CRUD operations, status management
- **Notifications**: Notification retrieval and management
- **Utilities**: Time functions, cache management, helper functions

### ✅ Integration Tests
- Database-Authentication integration
- Inventory-Request integration
- Notification-Request integration
- Budget-Actuals integration
- User-Project Site integration
- Complete request lifecycle
- Notification flow

## 🎯 Test Categories

### Unit Tests (`@pytest.mark.unit`)
- Test individual functions in isolation
- Fast execution
- No external dependencies

### Integration Tests (`@pytest.mark.integration`)
- Test component interactions
- May require database connection
- Verify data flow between components

## 📝 Writing New Tests

### Example Unit Test

```python
def test_function_name():
    """Test description"""
    import istrominventory
    
    # Test code
    result = istrominventory.some_function()
    assert result is not None
```

### Example Integration Test

```python
@pytest.mark.integration
def test_component_integration():
    """Test component integration"""
    from db import get_engine
    import istrominventory
    
    # Test integration
    engine = get_engine()
    # ... test code
```

## 🔍 Continuous Integration

Tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: pytest tests/ -v --cov=istrominventory
```

## 📈 Test Metrics

- **Total Test Files**: 7
- **Test Categories**: Unit, Integration
- **Coverage Target**: 70%+
- **Test Execution**: Fast (< 30 seconds)

## 🐛 Troubleshooting

### Tests fail with import errors
- Ensure you're in the project root directory
- Check that all dependencies are installed: `pip install -r requirements.txt`

### Database connection errors
- Ensure database is initialized: `python schema_init.py`
- Check DATABASE_URL environment variable (for PostgreSQL)

### Streamlit context errors
- Tests use mocks for Streamlit session state
- Some tests may need `@patch('streamlit.session_state')` decorator

## ✅ Test Checklist

Before committing code:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Coverage is above 70%
- [ ] No new warnings introduced
- [ ] Test documentation updated

