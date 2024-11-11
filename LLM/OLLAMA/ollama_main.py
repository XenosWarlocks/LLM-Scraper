
import streamlit as st
from scraper import WebScraper
from bs4 import BeautifulSoup
from parse import OllamaParser
import os
import tempfile
from document_downloader import DocumentDownloader
import humanize # type: ignore

# Page configuration
st.set_page_config(page_title="LLM Web Scraper", page_icon="🔍", layout="wide")

# Initialize session state
if 'downloaded_files' not in st.session_state:
    st.session_state.downloaded_files = {}

def initialize_parser():
    """Initialize the OllamaParser with a temporary download directory"""
    temp_dir = tempfile.mkdtemp()
    return OllamaParser(model_name="llama3", download_dir=temp_dir)

st.title("LLM Web Scraper")
st.write("Enter a website URL below, and click 'Scrape' to retrieve data and documents from the site.")

# User input
url = st.text_input("Website URL:", placeholder="e.g., https://example.com")

if st.button("Scrape"):
    if url:
        with st.spinner("Starting the scraping process, please wait..."):
            try:
                scraper = WebScraper()
                scraped_data = scraper.scrape_page(url)
                
                if scraped_data:
                    st.success(f"Successfully scraped data from: {url}")
                    
                    # Extract and clean the body content
                    body_content = scraper.extract_body_content(scraped_data)
                    cleaned_content = scraper.clean_body_content(body_content)
                    
                    # Store cleaned content in session state
                    st.session_state.dom_content = cleaned_content
                    
                    # Initialize document downloader
                    download_dir = tempfile.mkdtemp()
                    doc_downloader = DocumentDownloader(url, download_dir)
                    
                    # Find and download documents
                    doc_links = doc_downloader.find_document_links(scraped_data)
                    
                    if doc_links:
                        with st.spinner(f"Downloading {len(doc_links)} documents..."):
                            downloaded_files = doc_downloader.download_documents(doc_links)
                            st.session_state.downloaded_files = downloaded_files
                            
                            # Display downloaded documents by category
                            st.subheader("Downloaded Documents")
                            cols = st.columns(len(downloaded_files))
                            
                            for col, (category, files) in zip(cols, downloaded_files.items()):
                                if files:
                                    with col:
                                        st.markdown(f"**{category.title()}**")
                                        for filepath in files:
                                            filename = os.path.basename(filepath)
                                            file_size = os.path.getsize(filepath)
                                            
                                            st.markdown(f"📄 {filename}")
                                            st.text(f"Size: {humanize.naturalsize(file_size)}")
                                            
                                            with open(filepath, 'rb') as f:
                                                st.download_button(
                                                    label=f"Download {category.title()}",
                                                    data=f,
                                                    file_name=filename,
                                                    mime="application/octet-stream",
                                                    key=filepath
                                                )
                                            st.markdown("---")
                    
                    with st.expander("Show DOM Content"):
                        st.text_area("DOM Content", st.session_state.dom_content, height=300)

                else:
                    st.error("Failed to scrape data from the website.")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
    else:
        st.warning("Please enter a valid URL.")


# Content parsing section
if "dom_content" in st.session_state:
    scraper = WebScraper()
    split_dom = scraper.split_dom_content(st.session_state.dom_content)
    
    # Initialize parser with download capabilities
    parser = initialize_parser()
    
    # Parsing options
    st.subheader("Content Parsing")
    parse_description = st.text_area(
        "Describe what you want to parse",
        help="Describe the specific information you want to extract from the content"
    )
    
    parsing_col1, parsing_col2 = st.columns(2)
    
    with parsing_col1:
        if st.button("Parse Content"):
            if parse_description:
                with st.spinner("Parsing the content..."):
                    try:
                        parsed_result = parser.parse_with_ollama(split_dom, parse_description)
                        
                        if parsed_result.strip():
                            st.success("Parsing completed!")
                            st.write("Parsed Result:")
                            st.write(parsed_result)
                            
                            # Add download button for parsed results
                            st.download_button(
                                label="Download Parsed Results",
                                data=parsed_result,
                                file_name="parsed_results.txt",
                                mime="text/plain"
                            )
                        else:
                            st.info("No matching content found based on your description.")
                    except Exception as e:
                        st.error(f"Error during parsing: {str(e)}")
            else:
                st.warning("Please provide a description of what to parse.")
    
    with parsing_col2:
        if st.button("Clear Results"):
            # Clear session state
            for key in ['dom_content', 'downloaded_files']:
                if key in st.session_state:
                    del st.session_state[key]
            st.experimental_rerun()

# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit and LangChain")

# streamlit run main.py
