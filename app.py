import os
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from maps_extractor import GoogleMapsExtractor

# Page configuration
st.set_page_config(
    page_title="Google Maps Address Extractor",
    page_icon="🗺️",
    layout="wide"
)

CACHE_DIR = os.getcwd()

# Custom CSS
st.markdown("""
    <style>
    :root {
        --accent: #1e88e5;
        --accent-2: #6c5ce7;
        --bg: #f6f8fb;
        --text: #1f2933;
        --muted: #62707c;
    }
    .main-header {
        font-size: 2.6rem;
        color: var(--accent);
        text-align: center;
        margin-bottom: 1rem;
        letter-spacing: -0.02em;
    }
    .subhead {
        color: var(--muted);
        text-align: center;
        margin-bottom: 2rem;
    }
    .info-box {
        background: linear-gradient(135deg, #ffffff, #eef3ff);
        padding: 1.4rem;
        border-radius: 14px;
        margin-bottom: 1.2rem;
        border: 1px solid #e3e8f0;
        box-shadow: 0 6px 18px rgba(17, 24, 39, 0.06);
    }
    .success-box {
        background: #e8f7ef;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #28a745;
    }
    .warning-box {
        background: #fff7e6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #ffa000;
    }
    .error-box {
        background: #ffecef;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #e53935;
    }
    .download-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1rem 0;
        box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
    }
    .stButton>button {
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
        color: #fff;
        border: none;
        border-radius: 10px;
        height: 3rem;
        font-weight: 600;
        box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 24px rgba(76,110,245,0.25);
    }
    .download-section {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1.5rem 0;
        border: 2px solid #667eea;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">🗺️ Google Maps Address Extractor</h1>', unsafe_allow_html=True)
st.markdown('<p class="subhead">Upload, dedupe by search query, and standardize addresses via Google Maps</p>', unsafe_allow_html=True)

# Information section
with st.expander("ℹ️ How to Use This Tool", expanded=False):
    st.markdown("""
    ### Instructions:
    1. Upload your Excel/CSV with columns: `ID, Customer Code, Display Partner, Email, Phone, Mobile, Street, Street2, City, State, Zip, Country` (Country not used in lookup).
    2. We create `street_` (Street or Street2) and build the search query as:
       - `<Display Partner> in <street_> <City> <State> <Zip>` when Display Partner exists
       - `<street_> <City> <State> <Zip>` otherwise
    3. Choose headless/non-headless Chrome, set the random delay (2–10s), and pick batch size (5–20 rows per batch).
    4. Click **Start Processing** to scrape Google Maps for the first address element.
    5. Download the output with new columns: `street_`, `search_query`, `standard_address`.
    
    ### Notes:
    - Uses undetected Chrome + human-like pauses to reduce captchas; headless optional; forces English locale for Maps.
    - Leaves `street_` blank if both Street and Street2 are blank; `standard_address` is `N/A` when not found.
    - A working copy named `<original>_working.<ext>` is saved in this folder and updated after each batch; on re-uploading the same file name, processing resumes from already-processed rows (even if they were `N/A`). Use **Clear saved progress** to reset.
    - Chrome must be installed locally.
    """)

# Initialize session state
for key, default in [
    ("processing", False),
    ("processed_df", None),
    ("output_filename", None),
    ("work_path", None),
    ("output_extension", None),
    ("batch_size", 10),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Main content
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.subheader("📁 Upload Your File")
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=['csv', 'xlsx', 'xls'],
        help="Upload a file containing Street/Street2/City/State/Zip/Display Partner"
    )
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.subheader("📊 File Information")
    headless_mode = st.toggle("Hide Chrome window", value=True, help="Run Chrome off-screen (no visible browser window)")
    delay_seconds = st.slider(
        "Delay between lookups (seconds)",
        min_value=1.0,
        max_value=4.0,
        value=2.0,
        step=0.5,
        help="Pause between lookups; higher is safer (jitter ±0.5s applied)"
    )
    batch_size = st.slider(
        "Batch size",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
        help="Process rows in batches; progress is saved after each batch"
    )
    st.session_state.batch_size = batch_size
    st.caption(f"Using delay: {delay_seconds:.1f}s | Batch size: {batch_size}")
    if uploaded_file:
        st.write(f"**Filename:** {uploaded_file.name}")
        st.write(f"**Size:** {uploaded_file.size / 1024:.2f} KB")
        file_extension = uploaded_file.name.split('.')[-1]
        st.write(f"**Type:** {file_extension.upper()}")
    else:
        st.write("No file uploaded yet")
    st.markdown('</div>', unsafe_allow_html=True)

# Preview uploaded file
if uploaded_file:
    try:
        # Read the file
        if uploaded_file.name.endswith('.csv'):
            df_preview = pd.read_csv(uploaded_file)
        else:
            df_preview = pd.read_excel(uploaded_file)
        
        # Reset file pointer
        uploaded_file.seek(0)

        # Prepare cache paths
        extension = uploaded_file.name.rsplit('.', 1)[-1]
        base_name = uploaded_file.name.rsplit('.', 1)[0]
        work_filename = f"{base_name}_working.{extension}"
        work_path = os.path.join(CACHE_DIR, work_filename)
        st.session_state.work_path = work_path
        st.session_state.output_extension = extension
        
        # Check required columns exist
        required_cols = ['ID', 'Customer Code', 'Display Partner', 'Email', 'Phone', 'Mobile', 'Street', 'Street2', 'City', 'State', 'Zip', 'Country']
        missing = [col for col in required_cols if col not in df_preview.columns]
        if missing:
            st.markdown('<div class="error-box">', unsafe_allow_html=True)
            st.error("❌ Error: The uploaded file is missing required columns.")
            st.markdown('</div>', unsafe_allow_html=True)
            st.info("**Missing:** " + ", ".join(missing))
            st.info("**Available columns:** " + ", ".join(df_preview.columns.tolist()))
        else:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success(f"✅ File validated successfully! Found {len(df_preview)} rows to process.")
            st.markdown('</div>', unsafe_allow_html=True)

            st.info(f"Working copy will be stored at: `{work_path}` (used for resume)")

            if os.path.exists(work_path):
                try:
                    if extension == 'csv':
                        df_existing = pd.read_csv(work_path)
                    else:
                        df_existing = pd.read_excel(work_path)
                    processed_col = df_existing.get('processed')
                    if processed_col is not None:
                        processed_mask = processed_col.astype(bool)
                        completed = processed_mask.sum()
                        remaining = len(df_existing) - completed
                    else:
                        remaining = (df_existing['standard_address'].astype(str).str.strip().fillna("N/A") == "N/A").sum()
                        completed = len(df_existing) - remaining
                    st.info(f"📂 Found saved progress in working copy: {completed} done, {remaining} remaining. Resume will continue from that file.")
                except Exception:
                    st.warning("⚠️ Found saved file but could not read it; a new working copy will be created on start.")
            
            # Show preview
            st.subheader("📋 Data Preview")
            st.dataframe(df_preview.head(10), width='stretch')
            st.caption(f"Showing first 10 rows of {len(df_preview)} total rows")
            
            # Processing section
            st.markdown("---")
            st.subheader("🚀 Start Processing")
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
            
            with col_btn1:
                start_button = st.button(
                    "▶️ Start Processing",
                    type="primary",
                    disabled=st.session_state.processing,
                    width='stretch'
                )
            
            with col_btn2:
                clear_cache = st.button(
                    "🧹 Clear saved progress",
                    width='stretch',
                    disabled=not os.path.exists(work_path)
                )
                if clear_cache:
                    try:
                        if os.path.exists(work_path):
                            os.unlink(work_path)
                        st.session_state.processed_df = None
                        st.session_state.output_filename = None
                        st.success("Cleared saved progress.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not clear saved progress: {e}")
            
            # Download section - Show if working file exists OR processing is complete
            if os.path.exists(work_path) or st.session_state.processed_df is not None:
                st.markdown("---")
                st.markdown('<div class="download-section">', unsafe_allow_html=True)
                st.subheader("📥 Download Results")
                
                # Try to load the latest data
                try:
                    if st.session_state.processed_df is not None:
                        current_df = st.session_state.processed_df
                    elif os.path.exists(work_path):
                        if extension == 'csv':
                            current_df = pd.read_csv(work_path)
                        else:
                            current_df = pd.read_excel(work_path)
                    else:
                        current_df = None
                    
                    if current_df is not None:
                        # Show statistics
                        total = len(current_df)
                        if 'standard_address' in current_df.columns:
                            found = len(current_df[current_df['standard_address'] != 'N/A'])
                            not_found = total - found
                            processed_col = current_df.get('processed')
                            if processed_col is not None:
                                actually_processed = processed_col.astype(bool).sum()
                            else:
                                actually_processed = found + not_found
                        else:
                            found = 0
                            not_found = 0
                            actually_processed = 0
                        
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                        col_stat1.metric("Total Rows", total)
                        col_stat2.metric("Processed", actually_processed)
                        col_stat3.metric("✅ Found", found)
                        col_stat4.metric("❌ Not Found", not_found)
                        
                        # Download buttons
                        st.markdown("### Choose Download Format:")
                        col_dl1, col_dl2 = st.columns(2)
                        
                        # Generate filenames
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        excel_filename = f"{base_name}_standardized_{timestamp}.xlsx"
                        csv_filename = f"{base_name}_standardized_{timestamp}.csv"
                        
                        with col_dl1:
                            # Excel download
                            from io import BytesIO
                            excel_buffer = BytesIO()
                            current_df.to_excel(excel_buffer, index=False, engine='openpyxl')
                            excel_data = excel_buffer.getvalue()
                            
                            st.download_button(
                                label="📊 Download as Excel (.xlsx)",
                                data=excel_data,
                                file_name=excel_filename,
                                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                width='stretch',
                                type="primary"
                            )
                        
                        with col_dl2:
                            # CSV download
                            csv_data = current_df.to_csv(index=False).encode('utf-8')
                            
                            st.download_button(
                                label="📄 Download as CSV (.csv)",
                                data=csv_data,
                                file_name=csv_filename,
                                mime='text/csv',
                                width='stretch'
                            )
                        
                        st.info("💡 **Tip:** Download anytime to save your progress, even if processing isn't complete!")
                        
                except Exception as e:
                    st.error(f"Error preparing download: {e}")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Processing logic
            if start_button:
                st.session_state.processing = True
                
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(current, total):
                    progress = current / total
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {current}/{total} addresses ({progress*100:.1f}%)")
                
                try:
                    status_text.text("🔧 Initializing Chrome driver...")
                    resume_run = os.path.exists(work_path)
                    if not resume_run:
                        with open(work_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        status_text.text("📄 Created working copy...")
                    
                    extractor = GoogleMapsExtractor(
                        headless=headless_mode,
                        sleep_range=(delay_seconds - 0.5, delay_seconds + 0.5)
                    )
                    success, result = extractor.process_file(
                        input_file=work_path,
                        output_file=work_path,
                        progress_callback=update_progress,
                        resume=resume_run,
                        batch_size=st.session_state.batch_size
                    )
                    
                    if success:
                        # Read the processed file
                        if extension == 'csv':
                            st.session_state.processed_df = pd.read_csv(work_path)
                        else:
                            st.session_state.processed_df = pd.read_excel(work_path)
                        
                        status_text.empty()
                        progress_bar.empty()
                        
                        st.markdown('<div class="success-box">', unsafe_allow_html=True)
                        st.success("✅ Processing completed successfully!")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Show results preview
                        st.subheader("📊 Results Preview")
                        st.dataframe(st.session_state.processed_df.head(20), width='stretch')
                        
                        st.balloons()
                        st.rerun()
                        
                    else:
                        status_text.empty()
                        progress_bar.empty()
                        st.markdown('<div class="error-box">', unsafe_allow_html=True)
                        st.error(f"❌ Error during processing: {result}")
                        st.markdown('</div>', unsafe_allow_html=True)
                
                except Exception as e:
                    status_text.empty()
                    progress_bar.empty()
                    st.markdown('<div class="error-box">', unsafe_allow_html=True)
                    st.error(f"❌ An error occurred: {str(e)}")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                finally:
                    st.session_state.processing = False
    
    except Exception as e:
        st.markdown('<div class="error-box">', unsafe_allow_html=True)
        st.error(f"❌ Error reading file: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
    <div style='text-align: center; color: #666; padding: 1rem;'>
        <p>🗺️ Google Maps Address Extractor | Built with Streamlit & Selenium</p>
        <p style='font-size: 0.8rem;'>⚠️ This tool uses web scraping. Use responsibly and respect Google's Terms of Service.</p>
    </div>
""", unsafe_allow_html=True)