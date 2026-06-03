"""
Reusable help widget utilities for Streamlit pages.
Uses pure HTML/CSS (no JavaScript) so behavior is reliable in Streamlit markdown.
"""

import html
import streamlit as st

HELP_CONTENT = {
    "dashboard": {
        "title": "Dashboard Guide",
        "icon": "📊",
        "sections": [
            ("Overview", "Dashboard Explore has 3 tabs: Overview and Strategy, Deep Dive Analytics, and Raw Data Audit."),
            (
                "What This Page Calculates",
                [
                    "Star Performer picks the single video with highest view_count",
                    "Top lists rank videos by view_count and like_count (Top 10 each)",
                    "Upload Rhythm deduplicates by video_id, then counts uploads by month and weekday",
                    "Raw Data shows title, date, views, likes, comments, duration in minutes, and direct watch URL",
                ],
            ),
            (
                "Chart Logic",
                "Month pie chart shows upload share across months. Weekday bar chart shows frequency per day. These are upload pattern charts, not engagement efficiency charts.",
            ),
            (
                "How to Use",
                "Use Top Viewed/Liked as creative benchmarks, then check Upload Rhythm to identify your anchor publishing periods, and finally validate assumptions in Raw Data.",
            ),
        ],
    },
    "profile": {
        "title": "Profile Guide",
        "icon": "👤",
        "sections": [
            ("Overview", "Profile computes channel-health KPIs from your current dataset and explains timing plus performance quality distribution."),
            (
                "Profile KPI Meaning",
                [
                    "Engage Rate gauge uses mean engagement_rate with a 0 to 20 percent scale",
                    "Content Score gauge uses mean content_performance_score on a 0 to 100 scale",
                    "Subs per View gauge uses mean sub_to_view_ratio with dynamic max scale (about 1.5x the mean)",
                    "Avg Views gauge uses mean view_count converted to thousands, with max tied to channel peak views",
                ],
            ),
            (
                "Optimal Timing Analysis",
                "It groups data by publish_hour and computes avg_views plus video_count for each hour (0 to 23). It then highlights two different hours: most uploaded hour vs highest average-view hour.",
            ),
            (
                "Performance Distribution Logic",
                "The donut chart is built from performance_rank counts (High Performer, Medium, Low). It shows mix of outcomes, not absolute reach. More High Performer share means stronger consistency of good outcomes.",
            ),
            (
                "How to Interpret Together",
                "If best view hour is different from your most-uploaded hour, shift posting windows. If rank mix is skewed to Medium/Low, improve packaging and retention on topics already proven by top videos.",
            ),
        ],
    },
    "battle": {
        "title": "Battle Arena Guide",
        "icon": "⚔️",
        "sections": [
            ("Overview", "Battle Arena is the single place for rival selection, benchmark setup, and trend comparison. Rival selections are saved in session and reused in PDF reports."),
            (
                "How to Read Metrics",
                [
                    "Audience and Reach bars compare subscribers and total views using log-scale y-axis",
                    "Engagement Matrix bubble chart uses: x=total views, y=avg_engagement percent",
                    "Bubble size equals total engagement (likes+comments), one bubble per channel",
                    "Capabilities chart normalizes views, subscribers, video volume, and engagement depth to 0 to 1 for fair cross-metric comparison",
                    "Benchmark block compares one selected channel against database averages using ratio bars (1.0x baseline)",
                    "Trend Comparison block compares monthly Views/Likes/Comments across selected channels with chart-style controls",
                ],
            ),
            (
                "Battle Workflow",
                "Select 2 to 6 rivals first, then set benchmark and trend filters in Battle sidebar. Generate Battle charts here, then open Exports to include these charts in the PDF report.",
            ),
            (
                "Decision Rule",
                "If a rival is large but low on average engagement, their advantage is mostly scale. If they are strong on both scale and average engagement, their strategy is structurally stronger.",
            ),
        ],
    },
    "visuals": {
        "title": "Visuals Guide",
        "icon": "📈",
        "sections": [
            ("Overview", "Visuals has 3 tabs: Growth Trends, Topic and Stability, and Content Fingerprint."),
            (
                "Growth Trends Tab",
                [
                    "Monthly trend chart aggregates views, likes, comments, and uploads by month",
                    "Trend verdict compares first month vs last month for each metric and outputs growth or decline percent",
                    "Upload Frequency Heatmap builds a 7x12 matrix (day x month) using upload counts",
                    "Darker green means more uploads in that day-month cell; grey means zero uploads",
                ],
            ),
            (
                "Topic and Stability Tab",
                "Stability score uses coefficient of variation formula: score = max(5, 100/(1+cv)). Box plot and histogram then show spread, median, IQR, and outlier behavior.",
            ),
            (
                "How to Use",
                "Use Fingerprint tab to see top 15 videos by selected metric (treemap size), then read conversion funnel to understand views to likes/comments efficiency.",
            ),
        ],
    },
    "compare": {
        "title": "Exports Guide",
        "icon": "📦",
        "sections": [
            ("Overview", "Exports page focuses on leaderboard intelligence, CSV/XLSX downloads, and PDF report generation."),
            (
                "Block Meaning",
                [
                    "Leaderboard ranks all synced channels by sidebar-selected metric (subscribers, views, engagement percent, or videos)",
                    "Analytics Data Hub provides leaderboard CSV/XLSX, Top 10 CSV, and channel deep workbook exports",
                    "PDF Report Builder uses current channel data plus saved Battle rivals (if at least 2 are selected)",
                    "Benchmark Analysis and Trend Comparison controls are on Battle Arena page",
                ],
            ),
            (
                "How to Use",
                "Use Exports to rank channels quickly, download CSV/XLSX files, and generate polished PDF reports. Switch to Battle Arena for benchmark ratios and trend diagnostics.",
            ),
            (
                "Practical Logic",
                "Use leaderboard as the discovery layer. Then open Battle Arena to validate whether top-ranked channels also sustain strong benchmark ratios and trend stability before final export.",
            ),
        ],
    },
}


def _render_help_body(page_name: str) -> str:
    if page_name not in HELP_CONTENT:
        return "<p style='margin:0;color:#334155;'>Help content not available for this page.</p>"

    block = HELP_CONTENT[page_name]
    chunks = []
    for section_title, section_content in block["sections"]:
        chunks.append(
            f"<h4 style='margin:14px 0 8px;color:#FF1744;font-size:1rem;font-weight:700;'>{html.escape(section_title)}</h4>"
        )
        if isinstance(section_content, list):
            chunks.append("<ul style='margin:0 0 4px 18px;padding:0;color:#334155;'>")
            for item in section_content:
                chunks.append(
                    f"<li style='margin:4px 0;font-size:0.92rem;line-height:1.45;'>{html.escape(item)}</li>"
                )
            chunks.append("</ul>")
        else:
            chunks.append(
                f"<p style='margin:0 0 2px;color:#475569;font-size:0.92rem;line-height:1.5;'>{html.escape(section_content)}</p>"
            )

    return "".join(chunks)


def render_help_widget(page_name: str, position: str = "bottom-right") -> None:
    """Render a floating '?' button and a modal help card using CSS :target."""
    cfg = HELP_CONTENT.get(page_name, {"title": "Help", "icon": "❓"})
    modal_id = f"help-modal-{page_name}"
    side_css = "right:24px;" if position == "bottom-right" else "left:24px;"

    widget_html = f"""
    <style>
        .help-fab-{page_name} {{
            position: fixed;
            bottom: 24px;
            {side_css}
            width: 56px;
            height: 56px;
            border-radius: 50%;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            font-weight: 800;
            color: #FFFFFF;
            background: linear-gradient(135deg, #FF1744 0%, #D32F2F 100%);
            border: 2px solid rgba(255,255,255,0.18);
            box-shadow: 0 12px 32px rgba(255,23,68,0.34);
            z-index: 2147483000;
            transition: transform 0.25s ease, box-shadow 0.25s ease;
        }}
        .help-fab-{page_name}:hover {{
            transform: translateY(-3px) scale(1.08);
            box-shadow: 0 18px 36px rgba(255,23,68,0.42);
            color: #FFFFFF;
        }}

        .help-modal-{page_name} {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 2147483001;
        }}
        .help-modal-{page_name}:target {{
            display: block;
        }}

        .help-modal-overlay-{page_name} {{
            position: absolute;
            inset: 0;
            background: rgba(15, 23, 42, 0.52);
            backdrop-filter: blur(3px);
        }}

        .help-modal-card-{page_name} {{
            position: relative;
            max-width: 560px;
            width: min(92vw, 560px);
            max-height: 80vh;
            margin: 8vh auto 0 auto;
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid rgba(226,232,240,0.85);
            background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
            box-shadow: 0 24px 64px rgba(15,23,42,0.28);
            animation: help-pop-{page_name} 0.22s ease-out;
        }}

        .help-modal-head-{page_name} {{
            padding: 16px 18px;
            color: #FFFFFF;
            background: linear-gradient(135deg, #FF1744 0%, #F50057 100%);
            font-family: 'Outfit', sans-serif;
            font-size: 1.12rem;
            font-weight: 700;
        }}

        .help-modal-body-{page_name} {{
            padding: 16px 18px;
            overflow-y: auto;
            max-height: calc(80vh - 120px);
            color: #0F172A;
        }}

        .help-modal-foot-{page_name} {{
            padding: 12px 18px;
            border-top: 1px solid #E2E8F0;
            text-align: right;
            background: #FFFFFF;
        }}

        .help-close-btn-{page_name} {{
            display: inline-block;
            text-decoration: none;
            background: #E2E8F0;
            color: #1E293B;
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 0.88rem;
            font-weight: 700;
            border: 1px solid #CBD5E1;
        }}

        @keyframes help-pop-{page_name} {{
            from {{ opacity: 0; transform: translateY(10px) scale(0.985); }}
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
    </style>

    <a href="#{modal_id}" class="help-fab-{page_name}" aria-label="Open help">?</a>

    <div id="{modal_id}" class="help-modal-{page_name}">
        <a href="#" class="help-modal-overlay-{page_name}" aria-label="Close help"></a>
        <div class="help-modal-card-{page_name}">
            <div class="help-modal-head-{page_name}">{html.escape(cfg['icon'])} {html.escape(cfg['title'])}</div>
            <div class="help-modal-body-{page_name}">{_render_help_body(page_name)}</div>
            <div class="help-modal-foot-{page_name}">
                <a href="#" class="help-close-btn-{page_name}">Close</a>
            </div>
        </div>
    </div>
    """

    st.markdown(widget_html, unsafe_allow_html=True)


def render_help_simple(page_name: str, title: str, content: str) -> None:
    """Simplified floating help widget with custom text."""
    modal_id = f"help-simple-{page_name}"
    safe_title = html.escape(title)
    safe_content = html.escape(content)

    simple_html = f"""
    <style>
        .help-simple-fab-{page_name} {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            font-weight: 800;
            color: #FFFFFF;
            background: linear-gradient(135deg, #FF1744 0%, #D32F2F 100%);
            border: 2px solid rgba(255,255,255,0.18);
            box-shadow: 0 12px 32px rgba(255,23,68,0.34);
            z-index: 2147483000;
        }}
        .help-simple-modal-{page_name} {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 2147483001;
        }}
        .help-simple-modal-{page_name}:target {{
            display: block;
        }}
    </style>

    <a href="#{modal_id}" class="help-simple-fab-{page_name}" aria-label="Open help">?</a>
    <div id="{modal_id}" class="help-simple-modal-{page_name}">
        <a href="#" style="position:absolute;inset:0;background:rgba(15,23,42,0.52);"></a>
        <div style="position:relative;max-width:520px;width:min(92vw,520px);margin:10vh auto 0 auto;background:#FFFFFF;border-radius:12px;border:1px solid #E2E8F0;box-shadow:0 24px 64px rgba(15,23,42,0.28);overflow:hidden;">
            <div style="padding:16px 18px;background:linear-gradient(135deg,#FF1744 0%,#F50057 100%);color:#FFFFFF;font-weight:700;">{safe_title}</div>
            <div style="padding:16px 18px;color:#334155;line-height:1.55;">{safe_content}</div>
            <div style="padding:12px 18px;border-top:1px solid #E2E8F0;text-align:right;"><a href="#" style="text-decoration:none;background:#E2E8F0;color:#1E293B;border-radius:8px;padding:7px 14px;font-size:0.88rem;font-weight:700;">Close</a></div>
        </div>
    </div>
    """

    st.markdown(simple_html, unsafe_allow_html=True)
