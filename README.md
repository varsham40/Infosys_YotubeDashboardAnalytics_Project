# 📊 YouTube Analytics Pro

A high-performance research tool for professional content analysis, built with Python and Streamlit. This dashboard allows you to analyze YouTube channels, track video performance, and visualize engagement metrics over time.

## 🚀 Key Features

- **🏠 Dashboard**: Real-time performance auditing with live stats for Subscribers, Total Views, and Engagement Velocity.
- **🏆 Profile**: Deep metadata extraction of channel identity, top uploads, and keyword strategies.
- **⚖️ Battle Arena**: Head-to-head benchmarking against rivals to track "Reach Battle" and "Share of Voice."
- **📈 Visuals**: Pattern recognition through interactive Heatmaps (post-time optimization) and Treemaps (topic distribution).
- **🔍 Search**: Advanced video archive exploration with precision range filters (Views, Duration) and bulk CSV export.
- **📊 Compare**: Strategic reporting center for generating professional PDF intelligence dossiers and stakeholder reports.
- **🗺️ About Hub**: Modular blueprint explaining the app's logical framework, data intelligence mission, and target audience.
- **🛡️ Help & FAQ**: Elite Support Repository with collapsible FAQ categories and real-time system connectivity diagnostics.

## 🛠️ Technology Stack
- **Frontend**: Streamlit
- **Visualizations**: Plotly
- **Data Handling**: Pandas, NumPy
- **Database**: MySQL with SQLAlchemy ORM
- **PDF Generation**: FPDF2
- **Data Export**: Pandas (CSV) & OpenPyXL (Excel)
- **API**: YouTube Data API v3

## 📋 Prerequisites
- Python 3.8 or higher
- A Google Cloud Project with the YouTube Data API v3 enabled
- A YouTube API Key

## ⚙️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Springboard-Internship-2025/YouTube-Channel-Performance-and-Engagement-Analytics-Dashboard_Feb_Batch-8_2026.git
   cd YouTube-Channel-Performance-and-Engagement-Analytics-Dashboard_Feb_Batch-8_2026
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Create a `.env` file in the root directory and add your API credentials:
   ```env
   YT_API_KEY=your_api_key_here
   DB_USER=your_mysql_user
   DB_PASSWORD=your_mysql_password
   DB_HOST=localhost
   DB_NAME=youtube_analytics
   ```

## 🚀 Running the App
To start the dashboard, navigate into the `streamlit_app` directory and run Streamlit:

```bash
cd streamlit_app
streamlit run app.py
```

## 📂 Project Structure
- **`data_processing/`**: Logic for extracting channel/video data and calculating metrics.
- **`database_operations/`**: Database models, configuration, and persistence logic.
- **`streamlit_app/`**: Streamlit interface, theme configuration, and modular pages (About, Help).
- **`tests/`**: Unit tests and database verification scripts.