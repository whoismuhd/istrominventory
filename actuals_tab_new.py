# -------------------------------- Tab 6: Actuals --------------------------------
with tab6:
    st.subheader("📊 Actuals")
    
    # Get current project site
    project_site = st.session_state.get('current_project_site', 'Not set')
    st.write(f"**Project Site:** {project_site}")
    
    # Get all items for current project site
    items_df = df_items_cached(project_site)
    
    if not items_df.empty:
        # Budget Selection Dropdown
        st.markdown("#### 📊 Select Budget to View")
        
        # Simple budget options
        budget_options = [
            "Budget 1 - Flats",
            "Budget 1 - Terraces", 
            "Budget 1 - Semi Detached",
            "Budget 1 - Detached"
        ]
        
        selected_budget = st.selectbox(
            "Choose a budget to view:",
            options=budget_options,
            key="budget_selector"
        )
        
        if selected_budget:
            # Parse the selected budget
            budget_part, building_part = selected_budget.split(" - ", 1)
            
            # Get all items for this budget (all categories)
            budget_items = items_df[
                items_df['budget'].str.contains(f"{budget_part} - {building_part}", case=False, na=False)
            ]
            
            if not budget_items.empty:
                st.markdown(f"##### 📊 {selected_budget}")
                st.markdown("**📊 BUDGET vs ACTUAL COMPARISON**")
                
                # Create simple comparison table
                comparison_data = []
                idx = 1
                
                # Group by category
                categories = {}
                for _, item in budget_items.iterrows():
                    category = item.get('category', 'General Materials')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(item)
                
                # Create table data
                for category in ['General Materials', 'Woods', 'Plumbings', 'Irons', 'Labour']:
                    if category in categories:
                        # Add category header
                        comparison_data.append({
                            'S/N': '',
                            'MATERIALS': f"**{category.upper()}**",
                            'PLANNED QTY': '',
                            'PLANNED UNIT': '',
                            'PLANNED RATE': '',
                            'PLANNED AMOUNT': '',
                            'ACTUAL QTY': '',
                            'ACTUAL UNIT': '',
                            'ACTUAL RATE': '',
                            'ACTUAL AMOUNT': ''
                        })
                        
                        # Add items in this category
                        for item in categories[category]:
                            qty = item['qty'] if pd.notna(item['qty']) else 0
                            unit_cost = item['unit_cost'] if pd.notna(item['unit_cost']) else 0
                            amount = qty * unit_cost
                            
                            comparison_data.append({
                                'S/N': idx,
                                'MATERIALS': item['name'],
                                'PLANNED QTY': qty,
                                'PLANNED UNIT': item['unit'],
                                'PLANNED RATE': unit_cost,
                                'PLANNED AMOUNT': amount,
                                'ACTUAL QTY': 0,
                                'ACTUAL UNIT': item['unit'],
                                'ACTUAL RATE': 0,
                                'ACTUAL AMOUNT': 0
                            })
                            idx += 1
                
                if comparison_data:
                    comparison_df = pd.DataFrame(comparison_data)
                    
                    # Format currency columns
                    currency_cols = ['PLANNED RATE', 'PLANNED AMOUNT', 'ACTUAL RATE', 'ACTUAL AMOUNT']
                    for col in currency_cols:
                        if col in comparison_df.columns:
                            comparison_df[col] = comparison_df[col].apply(lambda x: f"₦{x:,.2f}")
                    
                    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
                    
                    # Calculate totals
                    total_planned = sum(item['qty'] * item['unit_cost'] for _, item in budget_items.iterrows() 
                                       if pd.notna(item['qty']) and pd.notna(item['unit_cost']))
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total Planned", f"₦{total_planned:,.2f}")
                    with col2:
                        st.metric("Total Actual", "₦0.00")
            else:
                st.info("No items found for this budget")
    else:
        st.info("📦 No items found for this project site.")
        st.markdown("""
        **How to get started:**
        1. Add items to your inventory in the Manual Entry tab
        2. Create requests in the Make Request tab
        3. Approve requests in the Review & History tab
        4. Approved requests will automatically appear here as actuals
        """)
