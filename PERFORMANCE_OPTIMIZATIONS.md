# Performance Optimizations to Prevent Lag and Refreshing

## Changes Made

### 1. **Added Caching to Expensive Functions**
   - `get_budget_options()` - Cached for 10 minutes (budget options rarely change)
   - `get_section_options()` - Cached for 10 minutes (section options rarely change)
   - `df_requests()` - Cached for 1 minute (requests change but not constantly)
   - `_get_over_planned_requests()` - Cached for 2 minutes (reduces database queries)
   - `df_items_cached()` - Already cached for 5 minutes

### 2. **Reduced Unnecessary Cache Clearing**
   - The `clear_cache()` function is already optimized to only clear specific caches
   - It doesn't trigger automatic reruns, which prevents lag

### 3. **Optimized Query Parameters**
   - Functions now accept parameters explicitly for proper cache key generation
   - This ensures caches work correctly across different users/project sites

## Additional Recommendations

### To Further Reduce Lag:

1. **Reduce Widget Interactions**
   - Use `st.session_state` to track widget values instead of reading them on every rerun
   - Group related widgets in forms to prevent reruns on each change

2. **Disable Auto-Refresh for Filters**
   - If filters are causing too many reruns, consider using a "Apply Filter" button
   - Use `st.form()` to batch filter changes

3. **Database Connection Pooling**
   - Already implemented in `db.py` with connection pooling
   - Pool size is optimized for performance

4. **Reduce Print Statements**
   - Debug prints can slow down execution
   - Most have been removed or commented out

5. **Pagination for Large Tables**
   - Already implemented in inventory display
   - Consider adding pagination to requests table if it gets large

## How Caching Works

- **Cache TTL (Time To Live)**: Determines how long data stays cached
  - Long TTL (10 min): For data that rarely changes (budget options, sections)
  - Medium TTL (1-2 min): For data that changes occasionally (requests, items)
  - Short TTL (30 sec): For frequently changing data

- **Cache Keys**: Based on function parameters
  - Same parameters = same cache (no recalculation)
  - Different parameters = new cache entry

## Monitoring Performance

If you still experience lag:

1. Check which operations are slow by adding timing logs
2. Increase cache TTL for rarely changing data
3. Reduce cache TTL for frequently changing data
4. Check database query performance
5. Monitor memory usage

## Testing

After these changes:
- Page should load faster on initial load
- Filter changes should be smoother (cached options)
- Dashboard should refresh less frequently
- Request table should load faster (cached queries)

