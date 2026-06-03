import sys
filename = r"e:\InfosysVirtual\streamlit_app\app.py"
with open(filename, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. Remove the line 'with st.container(border=True):' and unindent subsequent lines
for i, line in enumerate(lines):
    if "with st.container(border=True):" in line and i > 1620 and i < 1650:
        lines.pop(i)
        j = i
        while j < len(lines):
            if lines[j].strip() == "":
                j += 1
                continue
            if lines[j].startswith("    "):
                lines[j] = lines[j][4:]
            if "elif st.session_state['page'] == 'profile':" in lines[j]:
                break
            j += 1
        break

# 2. Replace the buttons logic
btn_code_old_start = -1
btn_code_old_end = -1
for i, line in enumerate(lines):
    if "btn_col1, btn_col2, _ = st.columns([1.6, 1.6, 5])" in line and i > 1600:
        btn_code_old_start = i
        break

if btn_code_old_start != -1:
    for j in range(btn_code_old_start, btn_code_old_start + 20):
        if "st.rerun()" in lines[j] and j < btn_code_old_start + 20:
            btn_code_old_end = j
            break
            
    if btn_code_old_end != -1:
        new_btn_code = """            if st.session_state['gp_explore']:
                btn_col1, _ = st.columns([1.5, 8.5])
                with btn_col1:
                    if st.button("⬅️  Back", use_container_width=True, key="btn_explore_analytics"):
                        st.session_state['gp_explore'] = False
                        st.rerun()
            else:
                btn_col1, btn_col2, _ = st.columns([1.6, 1.6, 5])
                with btn_col1:
                    st.link_button("▶  See Channel on YouTube", f"https://www.youtube.com/channel/{ch_id}", use_container_width=True, type="primary")
                with btn_col2:
                    if st.button("🔭  Explore Analytics", use_container_width=True, key="btn_explore_analytics"):
                        st.session_state['gp_explore'] = True
                        st.rerun()
"""
        lines[btn_code_old_start:btn_code_old_end+1] = [new_btn_code]

with open(filename, "w", encoding="utf-8") as f:
    f.writelines(lines)
print("SUCCESS!")
