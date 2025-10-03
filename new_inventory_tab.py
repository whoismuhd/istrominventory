# -------------------------------- Tab 2: Inventory --------------------------------
with tab2:
    st.subheader("📦 Current Inventory")
    st.caption("View and manage all inventory items with comprehensive filtering")
    
    # Check permissions for inventory management
    if not is_admin():
        st.warning("🔒 **Read-Only Access**: You can view inventory but cannot modify items.")
        st.info("💡 Contact an administrator if you need to make changes to the inventory.")
    
    # Filters (matching manual entry tab structure)
    st.markdown("### 🔍 Filters")
    colf1, colf2, colf3 = st.columns([2,2,2])
    with colf1:
        f_budget = st.text_input("🏷️ Budget Filter", "", help="Filter by budget name", key="inv_budget_filter")
    with colf2:
        f_section = st.text_input("📂 Section Filter", "", help="Filter by section", key="inv_section_filter")
    with colf3:
        f_bt = st.selectbox("🏠 Building Type Filter", PROPERTY_TYPES, index=0, help="Filter by building type", key="inv_bt_filter")

    # Smart filtering for budget
    budget_filter_value = None
    if f_budget:
        if "(" in f_budget and ")" in f_budget:
            # Specific subgroup search
            budget_filter_value = f_budget
        else:
            # General search - use base budget
            budget_filter_value = f_budget.split("(")[0].strip()
    
    filters = {
        "budget": budget_filter_value,
        "section": f_section or None,
        "building_type": f_bt or None,
    }
    
    # Get filtered items
    items = df_items(filters=filters)
    
    if not items.empty:
        items["Amount"] = (items["qty"].fillna(0) * items["unit_cost"].fillna(0)).round(2)
        
        # Display table
        st.dataframe(
            items[["budget","section","grp","building_type","name","qty","unit","unit_cost","Amount"]],
            use_container_width=True,
            column_config={
                "unit_cost": st.column_config.NumberColumn("Unit Cost", format="₦%,.2f"),
                "Amount": st.column_config.NumberColumn("Amount", format="₦%,.2f"),
            }
        )
        
        # Show total
        total_amount = float(items["Amount"].sum())
        st.metric("💰 Total Amount", f"₦{total_amount:,.2f}")
        
        # Export
        csv_data = items.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv_data, "inventory_view.csv", "text/csv")
        
        # Quick Edit & Delete section
        st.markdown("### ✏️ Quick Edit & Delete")
        require_confirm = st.checkbox("Require confirmation for deletes", value=True, key="inv_confirm")
        
        for _, r in items.iterrows():
            c1, c2, c3 = st.columns([6,1,1])
            c1.write(f"[{int(r['id'])}] {r['name']} — {r['qty']} {r['unit']} @ ₦{r['unit_cost']:,.2f}")
            if c2.button("✏️ Edit", key=f"edit_{int(r['id'])}"):
                st.session_state[f"edit_item_{int(r['id'])}"] = True
            if c3.button("🗑️ Delete", key=f"del_{int(r['id'])}", disabled=not is_admin()):
                if require_confirm:
                    st.session_state[f"confirm_del_{int(r['id'])}"] = True
                else:
                    delete_item(int(r['id']))
                    st.success(f"Deleted item {int(r['id'])}")
                    st.rerun()
            
            # Edit form
            if st.session_state.get(f"edit_item_{int(r['id'])}", False):
                with st.form(f"edit_form_{int(r['id'])}"):
                    new_qty = st.number_input("New Quantity", value=float(r['qty']), key=f"new_qty_{int(r['id'])}")
                    new_cost = st.number_input("New Unit Cost", value=float(r['unit_cost']), key=f"new_cost_{int(r['id'])}")
                    if st.form_submit_button("Update"):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE items SET qty=?, unit_cost=? WHERE id=?", (new_qty, new_cost, int(r['id'])))
                            conn.commit()
                        st.success(f"Updated item {int(r['id'])}")
                        st.session_state[f"edit_item_{int(r['id'])}"] = False
                        st.rerun()
            
            # Delete confirmation
            if st.session_state.get(f"confirm_del_{int(r['id'])}", False):
                st.warning(f"⚠️ Are you sure you want to delete item {int(r['id'])}: {r['name']}?")
                col1, col2 = st.columns([1,1])
                with col1:
                    if st.button("✅ Yes, Delete", key=f"yes_del_{int(r['id'])}"):
                        delete_item(int(r['id']))
                        st.success(f"Deleted item {int(r['id'])}")
                        st.session_state[f"confirm_del_{int(r['id'])}"] = False
                        st.rerun()
                with col2:
                    if st.button("❌ Cancel", key=f"no_del_{int(r['id'])}"):
                        st.session_state[f"confirm_del_{int(r['id'])}"] = False
                        st.rerun()

    else:
        st.info("No items found. Add some items in the Manual Entry tab first.")
    
    # Bulk operations
    st.markdown("### 🗑️ Bulk Operations")
    if st.button("🗑️ Delete ALL inventory and requests", type="secondary", disabled=not is_admin()):
        st.session_state["confirm_clear_all"] = True
    
    if st.session_state.get("confirm_clear_all", False):
        st.error("⚠️ **DANGER**: This will delete ALL inventory items and requests. This action cannot be undone!")
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("✅ Yes, Delete Everything", type="primary"):
                clear_inventory(include_logs=True)
                st.success("All inventory and requests cleared.")
                st.session_state["confirm_clear_all"] = False
                st.rerun()
        with col2:
            if st.button("❌ Cancel", type="secondary"):
                st.session_state["confirm_clear_all"] = False
                st.rerun()
