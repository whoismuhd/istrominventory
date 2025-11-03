# Functionality Fixes Applied

## Critical Bug Fixed: Cache Key Issue in df_requests()

### Problem
The `df_requests()` function was cached, but when called without explicit `user_type` and `project_site` parameters, it would read these from `st.session_state` inside the function. However, Streamlit's cache key is based on function parameters, not session state values accessed inside.

**Impact:**
- Admin calls `df_requests(status=None)` → caches result with key `(None, None, None)`
- Project site user calls `df_requests(status=None)` → cache hit returns admin's data (ALL requests) instead of just their project site's requests
- This caused incorrect data to be displayed to project site users

### Solution
1. Updated `df_requests()` to always explicitly use `user_type` and `project_site` in cache keys
2. Fixed all calls to `df_requests()` to explicitly pass `user_type` and `project_site` parameters:
   - Review & History tab statistics (line ~8275, ~8281)
   - Status-filtered requests display (line ~8386)
   - Approved requests display (line ~8581)
   - Rejected requests display (line ~8646)

### Files Modified
- `istrominventory.py` - Fixed cache key handling in `df_requests()` and all its calls

## Other Checks Performed

### ✅ Form Variable Scoping
- Verified `section`, `building_type`, `budget`, and `selected_item` are accessible in form submission handlers
- Variables defined in tab scope are accessible inside form blocks

### ✅ Error Handling
- All database operations have try/except blocks
- Form submissions have proper error handling
- Validation checks before database operations

### ✅ Cache Management
- `clear_cache()` properly clears all relevant caches
- Cache TTLs are appropriate (1-10 minutes depending on data volatility)

## Testing Recommendations

1. **Test cache fix:**
   - Login as admin → view Review & History → verify all requests shown
   - Login as project site user → view Review & History → verify only their project site's requests shown
   - Both should see correct data without cache conflicts

2. **Test form submissions:**
   - Make Request form → submit → verify tab persists
   - Approve/Reject form → submit → verify tab persists and data refreshes
   - Add Item form → submit → verify tab persists

3. **Test data filtering:**
   - Filter requests by status → verify correct results
   - Switch between admin and project site views → verify data isolation

