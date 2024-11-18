# main.py
import json
import streamlit as st
import os
import tempfile
from dotenv import load_dotenv
from PIL import Image
import requests
from io import BytesIO
import tempfile
import pandas as pd
import asyncio
import aiohttp
from typing import List, Tuple

from parse import UnifiedParser
from batch_processor import BatchURLProcessor, BatchProcessingResult
from loader import ImageLoader
from download_manager import DownloadManager
from result_manager import CSVResultManager

from utils.parse_config import ConfigLoader

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="LLM-Scraper",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'parser' not in st.session_state:
    st.session_state.parser = None
if 'csv_manager' not in st.session_state:
    st.session_state.csv_manager = None
if 'downloaded_files' not in st.session_state:
    st.session_state.downloaded_files = []
if 'last_parsed_result' not in st.session_state:
    st.session_state.last_parsed_result = None
if 'scraping_completed' not in st.session_state:
    st.session_state.scraping_completed = False
if 'site_id' not in st.session_state:
    st.session_state.site_id = None
if 'image_matches' not in st.session_state:
    st.session_state.image_matches = []
if 'pdf_links' not in st.session_state:
    st.session_state.pdf_links = []  # Initialize pdf_links if not present
if 'download_manager' not in st.session_state:
    st.session_state.download_manager = DownloadManager()
if 'model_number' not in st.session_state:
    st.session_state.model_number = ""
    
# Add new session state variables
if 'batch_results' not in st.session_state:
    st.session_state.batch_results = None
if 'batch_processing' not in st.session_state:
    st.session_state.batch_processing = False
# Session state initialization (add batch_urls)
if 'batch_urls' not in st.session_state:
    st.session_state.batch_urls = []    

# if 'batch_progress' not in st.session_state:
#     st.session_state.batch_progress = 0
# if 'batch_total' not in st.session_state:
#     st.session_state.batch_total = 0
if 'batch_completed' not in st.session_state:
    st.session_state.batch_completed = False
    
def initialize_parser(model_number=None):
    config_path = "utils/config.yaml"
    config = ConfigLoader.load_config(config_path)

    base_dir = "data"
    if model_number:
        base_dir = os.path.join(base_dir, model_number)
    os.makedirs(base_dir, exist_ok=True)
    image_loader = ImageLoader(base_dir=base_dir)
    csv_manager = CSVResultManager(base_dir=base_dir)

    parser = UnifiedParser(config=config, image_loader=image_loader)
    return parser, csv_manager

def initialize_parser_for_batch(model_number=None):
    config_path = "utils/config.yaml"
    config = ConfigLoader.load_config(config_path)

    # Define base directory for data storage
    base_dir = "data"
    if model_number:
        base_dir = os.path.join(base_dir, model_number)
    os.makedirs(base_dir, exist_ok=True)  # Create directories if they don't exist

    # Initialize image loader and CSV manager for batch processing
    image_loader = ImageLoader(base_dir=base_dir)
    csv_manager = CSVResultManager(base_dir=base_dir)

    # Initialize UnifiedParser with config and image_loader
    parser = UnifiedParser(config=config, image_loader=image_loader)
    return parser, csv_manager


def reset_session_state():
    """Reset all session state variables"""
    st.session_state.downloaded_files = []
    st.session_state.last_parsed_result = None
    st.session_state.scraping_completed = False
    st.session_state.raw_content = None
    st.session_state.site_id = None
    st.session_state.image_matches = []
    st.session_state.pdf_links = []  # Reset pdf_links
    st.experimental_rerun()

def display_image_from_url(url):
    """Display image from URL without downloading"""
    try:
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        st.error(f"Error loading image: {str(e)}")
        return None

def display_images(show_all_images):
    """Display images based on toggle selection (all images or only matches)"""
    images = st.session_state.downloaded_files if show_all_images else st.session_state.image_matches
    for idx, image_info in enumerate(images):
        with st.container():
            col1, col2 = st.columns([2, 1])
            with col1:
                # Check if image_info is a dictionary or has a 'url' attribute
                if isinstance(image_info, dict) and 'url' in image_info:
                    img_url = image_info['url']
                elif hasattr(image_info, 'url'):
                    img_url = image_info.url
                else:
                    st.warning(f"Image {idx + 1} format is unexpected.")
                    continue
                
                # Display the image if URL is valid
                img = display_image_from_url(img_url)
                if img:
                    st.image(img, caption=f"Image {idx + 1}")
            with col2:
                st.write("All Images" if show_all_images else f"Confidence: {image_info.confidence:.2f}")

def process_uploaded_file(uploaded_file):
    """Process uploaded file and return list of URLs"""
    try:
        # Create a temporary file with the correct extension
        suffix = os.path.splitext(uploaded_file.name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_file_path = tmp_file.name
            
        return temp_file_path, suffix
        
    except Exception as e:
        st.error(f"Error processing uploaded file: {str(e)}")
        return None, None

async def process_single_url_in_batch(parser, model_number, url, session, progress_bar, total_urls, current_index):
    """Process a single URL within batch processing, mirroring single URL functionality"""
    try:
        # Generate unique site ID for this URL in the batch
        site_id = f"batch_{model_number}_{current_index}"
        
        # Parse website using same function as single URL processing
        parse_result = await parser.parse_website_async(
            site_id=site_id,
            url=url,
            parse_description="general",
            session=session
        )
        
        # Mirror single URL processing steps
        result = {
            'url': url,
            'model_number': model_number,
            'status': 'success',
            'site_id': site_id,
            'raw_content': parse_result.raw_content,
            'downloaded_files': parse_result.downloaded_files or [],
            'image_matches': parse_result.image_matches if hasattr(parse_result, 'image_matches') else [],
            'pdf_links': parse_result.pdf_links if hasattr(parse_result, 'pdf_links') else [],
            'content_analysis': parse_result.content_analysis if hasattr(parse_result, 'content_analysis') else {},
            'error': None
        }
        
        # Update progress
        progress = (current_index + 1) / total_urls
        progress_bar.progress(progress)
        
        return result
        
    except Exception as e:
        return {
            'url': url,
            'model_number': model_number,
            'status': 'error',
            'site_id': None,
            'raw_content': None,
            'downloaded_files': [],
            'image_matches': [],
            'pdf_links': [],
            'content_analysis': {},
            'error': str(e)
        }

async def process_batch_urls(urls, parser, progress_bar):
    """Process multiple URLs asynchronously using consistent parsing approach"""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, (model_number, url) in enumerate(urls):
            task = asyncio.create_task(
                process_single_url_in_batch(
                    parser=parser,
                    model_number=model_number,
                    url=url,
                    session=session,
                    progress_bar=progress_bar,
                    total_urls=len(urls),
                    current_index=idx
                )
            )
            tasks.append(task)
        return await asyncio.gather(*tasks, return_exceptions=True)

# Main title and description
st.title("🔍 LLM Scraper")
st.write("Enter a website URL below to scrape, analyze, and parse its content using advanced AI.")

# Create two columns for main layout
left_col, right_col = st.columns([1.5, 2])

# Left column - input fields and analysis initiation
with left_col:
    
    # Add tabs for single/batch processing
    tab1, tab2 = st.tabs(["Single URL", "Batch Processing"])
    
    with tab1:
        # URL input and scrape button
        url = st.text_input(
            "Website URL:",
            placeholder="e.g., https://example.com",
            help="Enter the full URL including https:// or http://"
        )
        # Model Number input
        model_number = st.text_input(
            "Model Number:",
            placeholder="e.g., ABC-123",
            help="Enter the product model number"
        )
        if model_number:  # Initialize/re-initialize if model number changes
            st.session_state.parser, st.session_state.csv_manager = initialize_parser(model_number=model_number)
        elif st.session_state.parser is None: # Initialize if not already initialized
            st.session_state.parser, st.session_state.csv_manager = initialize_parser()

        # Confidence threshold slider
        min_confidence = st.slider(
            "Minimum Confidence Threshold",
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.05,
            help="Set the minimum confidence threshold for image matching"
        )

        # Checkbox to toggle showing all images or only related images
        show_all_images = st.checkbox(
            "Show All Images",
            value=False,
            help="Check to display all images regardless of confidence level."
        )

        # Optional main category input
        main_category = st.text_input(
            "Main Category (optional):",
            placeholder="e.g., electronics, furniture",
            help="Specify a main category to guide the content analysis"
        )

        # Analysis initiation button
        if st.button("🚀 Start Analysis"):
            if url:
                with st.spinner("Analyzing website content..."):
                    try:
                        parser = initialize_parser(model_number=model_number)
                        parse_result = st.session_state.parser.parse_website(
                            site_id="example_site", # Or dynamically generate site_id
                            url=url,
                            parse_description=main_category if main_category else "general" # Or use main_category
                        )

                        # Update session state with parse result data
                        st.session_state.scraping_completed = True
                        st.session_state.raw_content = parse_result.raw_content
                        st.session_state.downloaded_files = parse_result.downloaded_files or []
                        st.session_state.site_id = parse_result.site_id
                        st.session_state.image_matches = parse_result.image_matches
                        st.session_state.content_analysis = parse_result.content_analysis

                        # Handle PDF links
                        if hasattr(parse_result, 'pdf_links') and parse_result.pdf_links:
                            st.session_state.pdf_links = parse_result.pdf_links
                            st.write(f"Found {len(st.session_state.pdf_links)} PDF links.")  # Debugging

                        st.success("✅ Analysis completed successfully!")
                    except Exception as e:
                        st.error(f"❌ An error occurred: {str(e)}")
            else:
                st.warning("⚠️ Please enter a valid URL.")
    
    with tab2:
        st.subheader("Batch URL Processing")
        uploaded_file = st.file_uploader(
            "Upload file containing URLs",
            type=['txt', 'csv', 'xlsx', 'json'],
            help="Supported formats: TXT (one URL per line), CSV, Excel, or JSON"
        )
        
        max_concurrent = st.slider(
            "Max Concurrent Processes",
            min_value=1,
            max_value=10,
            value=5,
            help="Maximum number of URLs to process simultaneously"
        )
        
        timeout = st.slider(
            "Timeout (seconds)",
            min_value=10,
            max_value=120,
            value=30,
            help="Maximum time to spend on each URL"
        )
        
        uploaded_file = st.file_uploader(
            "Upload file containing URLs",
            type=['txt', 'csv', 'xlsx', 'json'],
            help="Supported formats: TXT (one URL per line), CSV (with 'Model Number' and 'URL' columns), Excel, or JSON"
        )
        
        if uploaded_file:
            temp_file_path, suffix = process_uploaded_file(uploaded_file)
            if temp_file_path and suffix in BatchURLProcessor.SUPPORTED_FORMATS:
                try:
                    # 1. Initialize BatchURLProcessor
                    # Initialize batch processor with correct parameters
                    batch_processor = BatchURLProcessor(
                        unified_parser=st.session_state.parser,  # Pass the UnifiedParser instance
                        max_concurrent=max_concurrent,
                        timeout=timeout,
                        result_manager=st.session_state.csv_manager,
                        default_model_number=model_number
                    )
                    
                    async def process_batch_async(urls: List[Tuple[str, str]], progress_bar) -> List[BatchProcessingResult]:
                        """Process URLs asynchronously with progress tracking"""
                        timeout = aiohttp.ClientTimeout(total=batch_processor.timeout)
                        connector = aiohttp.TCPConnector(limit=batch_processor.max_concurrent)
                        results = []
                        total_urls = len(urls)
                        
                        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                            for i, (model_number, url) in enumerate(urls):
                                try:
                                    # Use the batch processor's process_url method
                                    result = await batch_processor.process_url(
                                        model_number=model_number,
                                        url=url,
                                        session=session
                                    )
                                    results.append(result)
                                    
                                    # Update progress
                                    progress = (i + 1) / total_urls
                                    progress_bar.progress(progress)
                                    
                                except Exception as e:
                                    results.append(BatchProcessingResult(
                                        url=url,
                                        status='error',
                                        downloaded_files={},
                                        parsed_content='',
                                        raw_content='',
                                        error=str(e),
                                        model_number=model_number
                                    ))
                        
                        return results
                    
                    # 2. Read URLs from the temporary file
                    urls = list(batch_processor.read_urls(temp_file_path))
                    if urls:
                        st.session_state.batch_urls = urls
                        st.write(f"✅ Successfully loaded {len(urls)} URLs from file.")
                                            
                    # 3. Delete the temporary file
                    os.remove(temp_file_path)
                except Exception as e:
                    st.error(f"Error loading URLs: {e}")
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            else:
                st.error(f"Unsupported file format. Please upload a file with one of these extensions: {', '.join(BatchURLProcessor.SUPPORTED_FORMATS)}")
        
        if st.session_state.batch_urls:  # Check if URLs are loaded
            # Button should be at the same level as the URL loading logic
            if st.button("🚀 Start Batch Processing"):
                st.session_state.batch_processing = True
                with st.spinner("Processing URLs in batch..."):
                    try:
                        progress_bar = st.progress(0)
            
                        # Process URLs asynchronously
                        results = asyncio.run(process_batch_async(
                            urls=st.session_state.batch_urls,
                            progress_bar=progress_bar
                        ))
                        
                        st.session_state.batch_results = results
                        
                        # Count successful and failed results
                        successful = len([r for r in results if r.status == 'success'])
                        failed = len([r for r in results if r.status == 'error'])
                        
                        st.success(f"✅ Batch processing completed! Successfully processed {successful} URLs with {failed} failures.")
                        
                    except Exception as e:
                        st.error(f"❌ Batch processing error: {str(e)}")
                    finally:
                        st.session_state.batch_processing = False
        else:
            st.info("Please upload a file with URLs first.")

# Right column - display results after analysis
with right_col:
    if not st.session_state.batch_processing:
        # Single URL processing results
        if st.session_state.scraping_completed:
            st.subheader("📑 Analysis Results")
            
            with st.expander("📚 Document Links", expanded=True):
                # Check and display PDF links if available
                if st.session_state.pdf_links:
                    st.write(f"Found {len(st.session_state.pdf_links)} document(s):")
                    for i, doc_link in enumerate(st.session_state.pdf_links, 1):
                        file_type = "DOCX" if doc_link.lower().endswith('.docx') else "PDF"
                        icon = "📄" if file_type == "DOCX" else "📝"
                        st.markdown(f"{i}. {icon} [{os.path.basename(doc_link)}]({doc_link})")
                else:
                    st.warning("No PDF links found.")

            if 'content_analysis' in st.session_state:
                with st.expander("📊 Content Analysis"):
                    st.json(st.session_state.content_analysis)

            if st.session_state.image_matches or st.session_state.downloaded_files:
                st.subheader("🖼️ Images")
                display_images(show_all_images)

            if hasattr(st.session_state, 'raw_content'):
                with st.expander("🔍 Raw Content"):
                    st.text_area(
                        "Scraped Content",
                        st.session_state.raw_content,
                        height=400,
                        disabled=True
                    )
            elif st.session_state.batch_results:
                st.subheader("Batch Processing Results")
                
                results = st.session_state.batch_results
                successful = len([r for r in results if r.status == 'success'])
                failed = len([r for r in results if r.status != 'success'])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total URLs", len(results))
                col2.metric("Successful", successful)
                col3.metric("Failed", failed)
                
                # Convert results to DataFrame for download
                
                report = pd.DataFrame([{
                    'URL': r.url,
                    'Status': r.status,
                    'Error': r.error,
                    'Files Downloaded': sum(len(files) for files in r.downloaded_files.values()),
                    'Content Length': len(r.parsed_content) if r.parsed_content else 0
                } for r in results])
                
                csv_data = report.to_csv(index=False)
                json_data = report.to_json(orient='records')
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📥 Download CSV",
                        csv_data,
                        "batch_results.csv",
                        "text/csv",
                        key='download-csv'
                    )
                with col2:
                    st.download_button(
                        "📥 Download JSON",
                        json_data,
                        "batch_results.json",
                        "application/json",
                        key='download-json'
                    )
                st.write(f"Processed {len(st.session_state.batch_results)} URLs.")
                st.write(st.session_state.batch_results)

            parse_description = st.text_area(
                "What specific information would you like to extract?",
                placeholder="Example: 'Give me all of the information available' 'Find the product main title AND model number'",
                help="Describe the specific information you want to extract"
            )
        

            if st.button("🔍 Parse Content"):
                if parse_description:
                    with st.spinner("Parsing content..."):
                        try:
                            if st.session_state.parser is None:
                                st.error("Parser not initialized. Please provide a model number.")
                            else:
                                parser = st.session_state.parser
                                processed_chunks = parser.preprocess_content(st.session_state.raw_content)
                                parsed_result = parser.parse_with_gemini(processed_chunks, parse_description)
                            
                            st.session_state.last_parsed_result = parsed_result
                            
                            if parsed_result != "NO_MATCH":
                                st.success("✨ Parsing completed!")
                                st.write(parsed_result)
                                
                                # Process and save results
                                try:
                                    csv_path, json_path = st.session_state.download_manager.process_parse_result(
                                        parsed_result=parsed_result,
                                        model_number=model_number,  # Using the input model_number directly
                                        url=url,  # Using the input URL directly
                                        raw_content=st.session_state.raw_content,
                                        site_id=st.session_state.site_id,
                                        image_matches=st.session_state.image_matches,
                                        pdf_links=st.session_state.pdf_links,
                                        html_content=None  # Add if you have HTML content in session state
                                    )
                                
                                # Create download buttons
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        csv_data = st.session_state.download_manager.get_download_data(csv_path)
                                        st.download_button(
                                            label="📥 Download CSV",
                                            data=csv_data,
                                            file_name=f"results_{model_number}.csv",
                                            mime="text/csv"
                                        )
                                    with col2:
                                        json_data = st.session_state.download_manager.get_download_data(json_path)
                                        st.download_button(
                                            label="📥 Download JSON",
                                            data=json_data,
                                            file_name=f"results_{model_number}.json",
                                            mime="application/json"
                                        )
                                except Exception as e:
                                    st.error(f"❌ Error saving results: {str(e)}")
                            else:
                                st.info("ℹ️ No matching information found.")
                        except Exception as e:
                            st.error(f"❌ Error during parsing: {str(e)}")
    else:
        # Batch processing results
        if st.session_state.batch_results:
            st.subheader("📊 Batch Processing Results")
            
            # Summary metrics
            successful = len([r for r in st.session_state.batch_results if r['status'] == 'success'])
            failed = len([r for r in st.session_state.batch_results if r['status'] == 'error'])
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total URLs", len(st.session_state.batch_results))
            col2.metric("Successful", successful)
            col3.metric("Failed", failed)
            
            # Detailed results in expandable sections
            for result in st.session_state.batch_results:
                with st.expander(f"Results for {result['url']}", expanded=False):
                    st.markdown(f"**Model Number:** {result['model_number']}")
                    st.markdown(f"**Status:** {result['status']}")
                    
                    if result['error']:
                        st.error(f"Error: {result['error']}")
                    else:
                        # Display same information as single URL processing
                        if result['pdf_links']:
                            st.markdown("**📑 Documents Found:**")
                            for link in result['pdf_links']:
                                st.markdown(f"- [{os.path.basename(link)}]({link})")
                        
                        if result['image_matches']:
                            st.markdown("**🖼️ Matched Images:**")
                            for img in result['image_matches']:
                                st.image(display_image_from_url(img.url), width=200)
                        
                        if result['content_analysis']:
                            with st.expander("📊 Content Analysis"):
                                st.json(result['content_analysis'])
                        
                        with st.expander("🔍 Raw Content"):
                            st.text_area(
                                "Scraped Content",
                                result['raw_content'],
                                height=200,
                                disabled=True
                            )
                    
                    st.markdown("---")
            
            # Download results
            if st.button("📥 Download Results Report"):
                report = pd.DataFrame([{
                    'URL': r.url,
                    'Status': r.status,
                    'Error': r.error,
                    'Files Downloaded': sum(len(files) for files in r.downloaded_files.values()),
                    'Content Length': len(r.parsed_content) if r.parsed_content else 0
                } for r in results])
                
                csv = report.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv,
                    "batch_results.csv",
                    "text/csv",
                    key='download-csv'
                )

# Footer
st.markdown("---")
footer_col1, footer_col2 = st.columns(2)
with footer_col1:
    st.markdown("Made with ❤️ using Streamlit and Google Gemini")
with footer_col2:
    st.markdown("🛠️ Version 2.1 - Enhanced with UnifiedParser")

# streamlit run main.py