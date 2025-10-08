#!/usr/bin/env python3

# Read the main file
with open('istrominventory.py', 'r') as f:
    content = f.read()

# Read the new actuals tab
with open('actuals_tab_new.py', 'r') as f:
    new_actuals = f.read()

# Find the start and end of the actuals tab
start_marker = "# -------------------------------- Tab 6: Actuals --------------------------------"
end_marker = "# -------------------------------- Tab 7: Admin Settings (Admin Only) --------------------------------"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    # Replace the actuals tab
    new_content = content[:start_idx] + new_actuals + "\n\n" + content[end_idx:]
    
    # Write the new content
    with open('istrominventory.py', 'w') as f:
        f.write(new_content)
    
    print("✅ Successfully replaced the actuals tab!")
else:
    print("❌ Could not find the actuals tab markers")
