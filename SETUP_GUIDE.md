# Project Setup Guide

Here is the step-by-step process to set up this project from scratch in VS Code.

## 1. Create the Folder Structure
1.  Open your project folder in VS Code.
2.  Create the following new folders:
    *   `data_processing`
    *   `database_operations`
    *   `streamlit_app`

## 2. Create Configuration Files
Create these files in the **root** directory (outside the folders you just created):

**File: `requirements.txt`**
(This lists all the Python libraries we need)
```text
streamlit
google-api-python-client
pandas
sqlalchemy
pymysql
python-dotenv
plotly
```

**File: `.env`**
(This keeps your secrets safe)
```text
YOUTUBE_API_KEY=put_your_api_key_here
```

**File: `.gitignore`**
(This tells Git what to ignore)
```text
venv/
.env
__pycache__/
*.pyc
```

## 3. Create the Application File
Inside the `streamlit_app` folder, create a file named `app.py`:
```python
import streamlit as st

st.title("YouTube Analytics Dashboard")
st.write("Hello, World! The setup is working.")
```

## 4. Run Terminal Commands
Open a new Terminal in VS Code (`Ctrl` + `` ` ``) and run these commands one by one:

**Step A: Initialize Git**
```bash
git init
```

**Step B: Create Virtual Environment**
(This creates an isolated folder `venv` for your libraries)
```bash
python -m venv venv
```

**Step C: Activate Virtual Environment and Install Libraries**
(It might take a minute)
```bash
venv\Scripts\pip install -r requirements.txt
```

**Step D: Run the App**
```bash
venv\Scripts\streamlit run streamlit_app/app.py
```
