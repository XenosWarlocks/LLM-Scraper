import streamlit as st
from scraper import WebScraper
from parse import GeminiParser
import os
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="LLM Web Scraper",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'downloaded_files' not in st.session_state:
    st.session_state.downloaded_files = []
if 'last_parsed_result' not in st.session_state:
    st.session_state.last_parsed_result = None
if 'scraping_completed' not in st.session_state:
    st.session_state.scraping_completed = False

def initialize_parser():
    """Initialize the GeminiParser with API key and a temporary download directory"""
    temp_dir = tempfile.mkdtemp()
    return GeminiParser(
        api_key=os.getenv('GOOGLE_API_KEY'),
        model_name="gemini-pro",
        download_dir=temp_dir
    )

def reset_session_state():
    """Reset all session state variables"""
    st.session_state.downloaded_files = []
    st.session_state.last_parsed_result = None
    st.session_state.scraping_completed = False
    st.session_state.dom_content = None
    st.experimental_rerun()

# Main title and description
st.title("🔍 LLM Web Scraper")
st.write("Enter a website URL below to scrape and analyze its content using advanced AI.")

# Create two columns for the main layout
left_col, right_col = st.columns([2, 1])

with left_col:
    # URL input and scrape button
    url = st.text_input(
        "Website URL:",
        placeholder="e.g., https://example.com",
        help="Enter the full URL including https:// or http://"
    )
    
    if st.button("🚀 Start Scraping", use_container_width=True):
        if url:
            with st.spinner("Starting the scraping process..."):
                try:
                    # Initialize scraper and parser
                    scraper = WebScraper()
                    parser = initialize_parser()
                    
                    # Scrape the webpage
                    scraped_data = scraper.scrape_page(url)
                    
                    if scraped_data:
                        st.session_state.scraping_completed = True
                        
                        # Extract and clean content
                        body_content = scraper.extract_body_content(scraped_data)
                        cleaned_content = scraper.clean_body_content(body_content)
                        st.session_state.dom_content = cleaned_content
                        
                        # Process PDF links
                        pdf_links = parser.find_pdf_links(scraped_data)
                        if pdf_links:
                            st.session_state.pdf_links = pdf_links
                        
                        # Download images
                        downloaded_images = parser.download_images_from_html(scraped_data)
                        if downloaded_images:
                            st.session_state.downloaded_files.extend(downloaded_images)
                        
                        st.success("✅ Scraping completed successfully!")
                    else:
                        st.error("❌ Failed to scrape data from the website.")
                        
                except Exception as e:
                    st.error(f"❌ An error occurred: {str(e)}")
        else:
            st.warning("⚠️ Please enter a valid URL.")

    # Content parsing section
    if st.session_state.scraping_completed and "dom_content" in st.session_state:
        st.subheader("📑 Content Analysis")
        
        # Parse description input
        parse_description = st.text_area(
            "What information would you like to extract?",
            placeholder="Example: 'What is the product model number?' or 'Find the main title of the page'",
            help="Describe the specific information you want to extract from the content"
        )
        
        # Create columns for parse and clear buttons
        parse_col1, parse_col2 = st.columns([3, 1])
        
        with parse_col1:
            if st.button("🔍 Parse Content", use_container_width=True):
                if parse_description:
                    with st.spinner("Analyzing content..."):
                        try:
                            parser = initialize_parser()
                            # Preprocess the content
                            processed_chunks = parser.preprocess_content(st.session_state.dom_content)
                            parsed_result = parser.parse_with_gemini(processed_chunks, parse_description)
                            
                            st.session_state.last_parsed_result = parsed_result
                            
                            if parsed_result != "NO_MATCH":
                                st.success("✨ Analysis completed!")
                                st.write("📝 Results:")
                                st.write(parsed_result)
                                
                                # Add download button for parsed results
                                st.download_button(
                                    label="📥 Download Results",
                                    data=parsed_result,
                                    file_name="parsed_results.txt",
                                    mime="text/plain",
                                    key="download_parsed_results"
                                )
                            else:
                                st.info("ℹ️ No matching information found for your query.")
                        except Exception as e:
                            st.error(f"❌ Error during analysis: {str(e)}")
                else:
                    st.warning("⚠️ Please describe what information you want to extract.")
        
        with parse_col2:
            if st.button("🗑️ Clear All", use_container_width=True):
                reset_session_state()

with right_col:
    # Display scraped content and resources
    if st.session_state.scraping_completed:
        # PDF Links Section
        if hasattr(st.session_state, 'pdf_links') and st.session_state.pdf_links:
            with st.expander("📚 PDF Documents"):
                st.write(f"Found {len(st.session_state.pdf_links)} PDF files:")
                for i, pdf_link in enumerate(st.session_state.pdf_links, 1):
                    st.markdown(f"{i}. [{os.path.basename(pdf_link)}]({pdf_link})")
        
        # Downloaded Files Section
        if st.session_state.downloaded_files:
            with st.expander("📁 Downloaded Files"):
                st.write(f"Downloaded {len(st.session_state.downloaded_files)} files:")
                for i, file_path in enumerate(st.session_state.downloaded_files):
                    filename = os.path.basename(file_path)
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            st.download_button(
                                label=f"📥 {filename}",
                                data=f,
                                file_name=filename,
                                mime="application/octet-stream",
                                key=f"download_file_{i}"
                            )
        
        # Raw Content Viewer
        if "dom_content" in st.session_state:
            with st.expander("🔍 Raw Content"):
                st.text_area(
                    "Scraped Content",
                    st.session_state.dom_content,
                    height=400,
                    disabled=True
                )

# Footer
st.markdown("---")
footer_col1, footer_col2 = st.columns(2)
with footer_col1:
    st.markdown("Made with ❤️ using Streamlit and LangChain")
with footer_col2:
    st.markdown("🛠️ Powered by Google's Gemini Pro")

# streamlit run main.py
