#!/usr/bin/env python3
"""
Script to fix all SQL queries in istrominventory.py to use correct parameter placeholders
"""
import re

def fix_sql_queries():
    """Fix all SQL queries to use correct parameter placeholders"""
    
    # Read the file
    with open('istrominventory.py', 'r') as f:
        content = f.read()
    
    # Pattern to find SQL queries with ? placeholders
    pattern = r'cur\.execute\(["\']([^"\']*\?)["\']'
    
    def replace_query(match):
        query = match.group(1)
        # Replace ? with {placeholder} and add placeholder variable
        new_query = query.replace('?', '{placeholder}')
        return f'placeholder = get_sql_placeholder()\n        cur.execute(f"{new_query}"'
    
    # Replace all occurrences
    new_content = re.sub(pattern, replace_query, content)
    
    # Write back to file
    with open('istrominventory.py', 'w') as f:
        f.write(new_content)
    
    print("✅ Fixed all SQL queries to use correct parameter placeholders")

if __name__ == "__main__":
    fix_sql_queries()

