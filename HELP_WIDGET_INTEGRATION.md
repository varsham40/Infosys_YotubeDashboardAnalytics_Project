# Help Widget Integration Guide

## Quick Start

### Option 1: Use Pre-defined Content (Easiest)
```python
from streamlit_app.help_widget import render_help_widget

# At the START of each page section, add one line:
render_help_widget('dashboard')  # For Dashboard page
render_help_widget('profile')    # For Profile page
render_help_widget('battle')     # For Battle Arena page
render_help_widget('visuals')    # For Visualizations page
render_help_widget('compare')    # For Compare page
```

### Option 2: Use Custom Content
```python
from streamlit_app.help_widget import render_help_simple

render_help_simple(
    page_name='mypage',
    title='📊 My Custom Page',
    content='This page helps you with X, Y, and Z features.'
)
```

## Integration Steps for app.py

### 1. Add import at the top
```python
from help_widget import render_help_widget
```

### 2. Add one line at the start of each page section

**Dashboard:**
```python
elif page == "🏠 Dashboard":
    render_help_widget('dashboard')  # Add this line
    st.title("📊 Dashboard")
    # ... rest of dashboard code
```

**Profile:**
```python
elif page == "👤 Profile":
    render_help_widget('profile')  # Add this line
    st.title("👤 Channel Profile")
    # ... rest of profile code
```

**Battle Arena:**
```python
elif page == "⚔️ Battle Arena":
    render_help_widget('battle')  # Add this line
    st.title("⚔️ Battle Arena")
    # ... rest of battle code
```

**Visualizations:**
```python
elif page == "📈 Visuals":
    render_help_widget('visuals')  # Add this line
    st.title("📈 Visualizations")
    # ... rest of visuals code
```

**Compare:**
```python
elif page == "🔄 Compare":
    render_help_widget('compare')  # Add this line
    st.title("🔄 Comparison Analysis")
    # ... rest of compare code
```

## Updating Help Content

Edit the `HELP_CONTENT` dictionary in `help_widget.py`:

```python
HELP_CONTENT = {
    'dashboard': {
        'title': '📊 Dashboard Guide',
        'sections': [
            ('Section Title', 'Description text...'),
            ('Another Section', ['Bullet point 1', 'Bullet point 2']),
        ]
    },
    # ... other pages
}
```

## Features

✅ **Floating red question mark icon** - Bottom-right corner, always visible  
✅ **Smooth animations** - Hover scale and slide-up modal  
✅ **Session state managed** - Each page independent  
✅ **Responsive modal** - Works on mobile and desktop  
✅ **Easy to customize** - Just edit HELP_CONTENT dictionary  
✅ **No CSS pollution** - Self-contained, scoped styles  
✅ **Simple integration** - Single function call per page  

## Notes

- Help icon won't interfere with page content (fixed position, high z-index)
- Modal has close button and click outside to close
- Session state prevents modal reappearing on refresh
- Content is HTML-safe with proper styling
