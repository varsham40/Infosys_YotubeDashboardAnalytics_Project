import streamlit as st
import os
import pandas as pd
from dotenv import load_dotenv
from groq import Groq
from database_operations.db_connection import engine
from sqlalchemy import text
import requests
from bs4 import BeautifulSoup
import urllib.parse
import wikipedia  # type: ignore

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        client = None
else:
    client = None

def get_channel_summary(channel_id):
    """Fetch brief channel summary for AI context."""
    if not channel_id:
        return None
    try:
        query = f"""
        SELECT 
            c.channel_name, c.subscribers, c.views, c.total_videos, c.description
        FROM channels c
        WHERE c.channel_id = '{channel_id}'
        """
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            
            # Fetch top 5 videos for quick stats
            videos_query = f"""
            SELECT v.title, v.video_id, vs.view_count, vs.like_count, vs.comment_count
            FROM videos v
            JOIN video_statistics vs ON v.video_id = vs.video_id
            WHERE v.channel_id = '{channel_id}' 
            AND vs.captured_at = (SELECT MAX(captured_at) FROM video_statistics WHERE video_id = v.video_id)
            ORDER BY vs.view_count DESC 
            LIMIT 5
            """
            v_df = pd.read_sql(text(videos_query), conn)
            
            # Fetch catalog of up to 100 videos for search/links
            catalog_query = f"""
            SELECT v.title, v.video_id
            FROM videos v
            JOIN video_statistics vs ON v.video_id = vs.video_id
            WHERE v.channel_id = '{channel_id}'
            AND vs.captured_at = (SELECT MAX(captured_at) FROM video_statistics WHERE video_id = v.video_id)
            ORDER BY vs.view_count DESC
            LIMIT 100
            """
            cat_df = pd.read_sql(text(catalog_query), conn)
            
            # Fetch averages
            agg_query = f"""
            SELECT AVG(vs.view_count) as avg_views, AVG(vs.like_count) as avg_likes, AVG(vs.comment_count) as avg_comments
            FROM videos v
            JOIN video_statistics vs ON v.video_id = vs.video_id
            WHERE v.channel_id = '{channel_id}'
            AND vs.captured_at = (SELECT MAX(captured_at) FROM video_statistics WHERE video_id = v.video_id)
            """
            agg_df = pd.read_sql(text(agg_query), conn)

            # Fetch monthly stats
            monthly_query = f"""
            SELECT DATE_FORMAT(v.published_at, '%Y-%m') as month,
                   COUNT(v.video_id) as videos_uploaded,
                   SUM(vs.view_count) as monthly_views
            FROM videos v
            JOIN video_statistics vs ON v.video_id = vs.video_id
            WHERE v.channel_id = '{channel_id}'
            AND vs.captured_at = (SELECT MAX(captured_at) FROM video_statistics WHERE video_id = v.video_id)
            GROUP BY month
            ORDER BY month DESC
            LIMIT 24
            """
            monthly_df = pd.read_sql(text(monthly_query), conn)

        if not df.empty:
            summary = df.iloc[0].to_dict()
            summary['top_videos'] = v_df.to_dict(orient='records') if not v_df.empty else []
            summary['catalog'] = cat_df.to_dict(orient='records') if not cat_df.empty else []
            summary['averages'] = agg_df.iloc[0].to_dict() if not agg_df.empty else {}
            summary['monthly_stats'] = monthly_df.to_dict(orient='records') if not monthly_df.empty else []
            return summary
    except Exception as e:
        print(f"Error fetching channel data: {e}")
        pass
    return None

def get_web_context(query):
    """Perform a web search using Wikipedia for high accuracy."""
    context = ""
    
    # Wikipedia Entity Extraction
    try:
        wikipedia.set_user_agent('AI_Growth_Assistant/1.0')
        wiki_results = wikipedia.search(query)
        if wiki_results:
            # Try to get the exact match or first match
            try:
                wiki_summary = wikipedia.summary(wiki_results[0], sentences=5, auto_suggest=False)
                context += f"[Wikipedia: {wiki_results[0]}]\n{wiki_summary}\n\n"
            except wikipedia.exceptions.DisambiguationError as e:
                # If ambiguous, grab the first option
                wiki_summary = wikipedia.summary(e.options[0], sentences=5, auto_suggest=False)
                context += f"[Wikipedia: {e.options[0]}]\n{wiki_summary}\n\n"
            except wikipedia.exceptions.PageError:
                pass
    except Exception:
        pass
        
    return context

def render_ai_assistant():
    """Render a floating AI chatbot button and interface."""
    
    # Initialize chat history in session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hi! I'm your AI YouTube Growth Advisor. How can I help you analyze your channel today?"}
        ]

    # Inject CSS for the floating chat button and popover body
    st.markdown("""
        <style>
            /* ── Floating Chat Button ── */
            div[data-testid="stPopover"] {
                position: fixed !important;
                bottom: 24px !important;
                right: 24px !important;
                z-index: 2147483000 !important;
                width: 56px !important;
                height: 56px !important;
            }
            div[data-testid="stPopover"] button {
                width: 56px !important;
                height: 56px !important;
                border-radius: 50% !important;
                background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
                color: white !important;
                border: 2px solid rgba(255,255,255,0.18) !important;
                box-shadow: 0 8px 24px rgba(99,102,241,0.35) !important;
                padding: 0 !important;
                font-size: 1.7rem !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            div[data-testid="stPopover"] button:hover {
                box-shadow: 0 14px 32px rgba(99,102,241,0.45) !important;
            }
            div[data-testid="stPopover"] button svg {
                display: none !important;
            }

            /* ── Chatbot Popup Window ── */
            div[data-testid="stPopoverBody"] {
                width: 380px !important;
                max-width: 92vw !important;
                max-height: 75vh !important;
                border-radius: 18px !important;
                border: 1px solid #E2E8F0 !important;
                box-shadow: 0 16px 48px rgba(15,23,42,0.18) !important;
                background: #FFFFFF !important;
                padding: 16px !important;
                overflow-y: auto !important;
            }

            /* Hide border on inner chat scroll container */
            div[data-testid="stPopoverBody"] div[data-testid="stVerticalBlockBorderWrapper"] {
                border: none !important;
            }

            /* Thin scrollbar inside chat area */
            div[data-testid="stPopoverBody"] div[data-testid="stVerticalBlockBorderWrapper"] > div {
                scrollbar-width: thin;
                scrollbar-color: #CBD5E1 transparent;
            }
            div[data-testid="stPopoverBody"] div[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar {
                width: 4px;
            }
            div[data-testid="stPopoverBody"] div[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar-thumb {
                background: #CBD5E1;
                border-radius: 4px;
            }

            /* Chat message styling */
            div[data-testid="stPopoverBody"] div[data-testid="stChatMessage"] {
                padding: 8px 10px !important;
                font-size: 0.88rem !important;
            }

            /* Chat input - make sure it stays visible */
            div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] textarea {
                font-size: 0.88rem !important;
            }

            /* ── Mobile ── */
            @media (max-width: 768px) {
                div[data-testid="stPopoverBody"] {
                    width: 94vw !important;
                    height: 60vh !important;
                }
            }
        </style>
    """, unsafe_allow_html=True)

    # Render the popover
    with st.popover("🤖"):
        st.markdown("<h4 style='text-align: center; color: #4F46E5; margin-top: 0;'>AI Growth Assistant</h4>", unsafe_allow_html=True)
        
        if not client:
            st.error("Groq API Key not found or invalid. Please check your .env file.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        # Render Chat History
        chat_container = st.container(height=300)
        with chat_container:
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # Mode Toggle right above the chat input
        is_channel_specific = st.toggle("📈 Channel Specific Mode", value=True, help="Toggle off to ask general YouTube questions without channel context.")

        if is_channel_specific and not st.session_state.get('active_channel_id'):
            st.warning("⚠️ Please select and analyse a channel first to get channel-specific data in the chatbot.")

        # Chat Input
        if prompt := st.chat_input("Ask about YouTube strategy..."):
            # Append user message
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            # Render immediately
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

            # Prepare context
            if is_channel_specific:
                system_prompt = (
                    "You are an expert YouTube Growth Advisor and Data Analyst. "
                    "CRITICAL INSTRUCTIONS: "
                    "1. DO NOT hallucinate or invent fake links. If a user asks for a video on their channel, check the 'CHANNEL VIDEO CATALOG'. If they ask for general links, use the 'LIVE WEB SEARCH RESULTS'. "
                    "2. NEVER apologize for being an AI. YOU DO HAVE REAL-TIME INFORMATION via the live search context provided to you. "
                    "3. Format your advice clearly with markdown, focusing primarily on YouTube strategy, analytics, and content optimization."
                )
            else:
                system_prompt = (
                    "You are a highly capable, versatile, and intelligent AI assistant powered by Groq. "
                    "Your behavior should be just like Gemini or ChatGPT: deeply helpful, conversational, and extremely knowledgeable. "
                    "CRITICAL INSTRUCTIONS: "
                    "1. Base your answers strictly on factual data and the provided 'LIVE WEB SEARCH RESULTS'. "
                    "2. DO NOT hallucinate, guess, or invent facts. If the user asks about future events, recent releases (like movies in a specific year), or specific data that is NOT in the search results or your internal knowledge base, honestly state that you do not have that exact information rather than making it up. "
                    "3. Format your responses beautifully using rich Markdown (bolding, headers, bullet points) so they are easy to read."
                )
            
            # Fetch real-time web context
            with chat_container:
                with st.spinner("🤖 Doing research..."):
                    try:
                        # Generate optimal search query based on context
                        query_messages = st.session_state.chat_history[-5:] + [
                            {"role": "user", "content": "Based on our conversation, what is the single best Wikipedia search query to answer my latest request? Reply with ONLY the raw search query text. Do NOT wrap it in quotes. Do NOT explain. Just the exact keywords."}
                        ]
                        query_response = client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=query_messages,
                            temperature=0.1,
                            max_tokens=30
                        )
                        search_query = query_response.choices[0].message.content.strip(' "\'')
                        web_context = get_web_context(search_query)
                        
                        if web_context:
                            system_prompt += (
                                f"\n\n--- LIVE WEB SEARCH RESULTS (Query: '{search_query}') ---\n"
                                f"Use these real-time search results to answer accurately:\n{web_context}\n"
                            )
                    except Exception:
                        pass

            # Inject active channel context if toggled on
            if is_channel_specific:
                active_channel_id = st.session_state.get('active_channel_id')
                if active_channel_id:
                    ch_data = get_channel_summary(active_channel_id)
                    if ch_data:
                        # Format top videos
                        top_vids_text = ""
                        for idx, v in enumerate(ch_data.get('top_videos', [])):
                            top_vids_text += f"   {idx+1}. '{v.get('title')}' (Views: {v.get('view_count'):,}, Likes: {v.get('like_count'):,})\n"
                        
                        # Format catalog
                        catalog_text = ""
                        for v in ch_data.get('catalog', []):
                            catalog_text += f"- '{v.get('title')}' -> https://youtube.com/watch?v={v.get('video_id')}\n"
                            
                        avgs = ch_data.get('averages', {})
                        avg_views = avgs.get('avg_views', 0)
                        
                        monthly_text = ""
                        for m in ch_data.get('monthly_stats', []):
                            monthly_text += f"- Month: {m.get('month')}, Views: {m.get('monthly_views',0):,}, Uploads: {m.get('videos_uploaded',0)}\n"
                        
                        system_prompt += (
                            f"\n\n--- CHANNEL CONTEXT ---\n"
                            f"The user is currently analyzing their channel: '{ch_data['channel_name']}'.\n"
                            f"Channel Stats: {ch_data['subscribers']:,} subscribers, {ch_data['views']:,} total views, {ch_data['total_videos']} videos.\n"
                            f"Average Views per Video: {avg_views:,.0f} \n\n"
                            f"--- RECENT MONTHLY PERFORMANCE ---\n"
                            f"{monthly_text}\n\n"
                            f"Top 5 Best Performing Videos:\n{top_vids_text}\n\n"
                            f"--- CHANNEL VIDEO CATALOG ---\n"
                            f"Use this catalog to find and recommend specific videos when the user asks for topics or links:\n"
                            f"{catalog_text}\n"
                            f"CRITICAL RULE: If the user asks for videos about a topic, search the catalog above. IF found, provide the exact 'https://youtube.com/watch?v=...' links from the catalog. DO NOT guess or hallucinate any links."
                        )
                else:
                    system_prompt += "\n\n(Note: The user has selected Channel Specific Mode, but no channel is currently active. Provide general advice, but mention that they should sync a channel to get specific insights.)"

            messages = [{"role": "system", "content": system_prompt}]
            # Only send the last 10 messages to save context window and avoid bloat
            messages.extend(st.session_state.chat_history[-10:])

            with chat_container:
                with st.chat_message("assistant"):
                    message_placeholder = st.empty()
                    full_response = ""
                    
                    try:
                        # Use powerful llama-3.3-70b-versatile for high accuracy and anti-hallucination
                        stream = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=messages,
                            temperature=0.4,
                            max_tokens=2048,
                            stream=True
                        )
                        
                        for chunk in stream:
                            if chunk.choices[0].delta.content is not None:
                                full_response += chunk.choices[0].delta.content
                                message_placeholder.markdown(full_response + "▌")
                                
                        message_placeholder.markdown(full_response)
                        st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                        
                    except Exception as e:
                        st.error(f"Error communicating with AI: {e}")
