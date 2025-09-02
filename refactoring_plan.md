# Vocabulary System Refactoring Plan

## Priority 1: Critical Maintenance Issues

### 1. Consolidate Duplicate CLIs
**Problem:** Multiple CLI implementations cause confusion
- `main_cli.py` (primary)
- `vocabulary_cli.py` (unified interface)
- `simple_cli.py` 
- `custom_pronunciation_cli.py`
- `cuda_enhanced_cli.py`

**Solution:** Keep `main_cli.py` as the primary interface, archive others

### 2. Remove Test/Debug Files
**Files to remove:**
- `cuda_import_tester.py`
- `temp_db_debug.py` 
- `test_cuda_only.py`
- `run_system.py`
- `setup_script_for_pronunciation_similarity.py`

### 3. Standardize Package Structure
**Current:** Mixed flat files + package structure
**Solution:** Move to consistent package structure or flatten completely

## Priority 2: Code Organization

### 4. Create Shared Base Classes
**Problem:** Duplicate code across similarity calculators
**Solution:** Abstract base class for similarity calculations

### 5. Centralize Logging Configuration
**Problem:** Logging setup scattered across files
**Solution:** Move logging setup to `config.py`

### 6. Error Handling Standardization
**Problem:** Inconsistent error handling patterns
**Solution:** Create common exception classes and handlers

## Priority 3: Performance & Maintainability

### 7. Database Connection Management
**Problem:** Connection creation scattered throughout
**Solution:** Database connection factory/pool manager

### 8. Configuration Validation
**Problem:** No validation of configuration completeness
**Solution:** Startup configuration validation (already in progress)

### 9. Type Hints and Documentation
**Problem:** Inconsistent type annotations
**Solution:** Add comprehensive type hints for better IDE support

### 10. Unit Testing Infrastructure
**Problem:** No systematic testing
**Solution:** Add pytest framework with core functionality tests

## Implementation Priority

**Phase 1 (Immediate):**
1. Remove dead/test files
2. Choose single CLI implementation
3. Consolidate duplicate calculators

**Phase 2 (Short term):**
4. Create shared base classes
5. Centralize logging
6. Standardize error handling

**Phase 3 (Medium term):**
7. Database connection refactoring
8. Add comprehensive type hints
9. Build testing infrastructure

## Benefits
- Reduced code duplication
- Easier maintenance and debugging
- Better IDE support with type hints
- Consistent error handling
- Single source of truth for configurations