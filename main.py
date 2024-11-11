import streamlit as st
from scraper import WebScraper
from parse import OllamaParser
from document_downloader import DocumentDownloader
from batch_processor import BatchURLProcessor
import tempfile
import os
from pathlib import Path
import pandas as pd
import json

st.set_page_config(page_title="LLM Web Scraper", page_icon="🔍", layout="wide")

# Initialize processors
@st.cache_resource
def initialize_processors():
    return {
        'scraper': WebScraper(),
        'parser': OllamaParser(model_name="llama2"),
        'doc_downloader': DocumentDownloader
    }

processors = initialize_processors()

# Create tabs for single URL and batch processing
tab1, tab2 = st.tabs(["Single URL Processing", "Batch Processing"])

with tab1:
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
    pass

with tab2:
    st.header("Batch URL Processing")
    st.write("Upload a file containing URLs to process multiple websites at once.")
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload file containing URLs",
        type=['txt', 'csv', 'xlsx', 'xls', 'json'],
        help="Supported formats: TXT (one URL per line), CSV, Excel (with URL column), JSON"
    )
    
    # Configuration options
    with st.expander("Processing Options"):
        col1, col2 = st.columns(2)
        with col1:
            max_concurrent = st.number_input(
                "Max Concurrent Processes",
                min_value=1,
                max_value=10,
                value=5
            )
        with col2:
            timeout = st.number_input(
                "Timeout (seconds)",
                min_value=10,
                max_value=300,
                value=30
            )
    
    if uploaded_file and st.button("Start Batch Processing"):
        # Create temporary file to process
        temp_dir = tempfile.mkdtemp()
        temp_file = Path(temp_dir) / uploaded_file.name
        
        with open(temp_file, 'wb') as f:
            f.write(uploaded_file.getvalue())
        
        # Initialize batch processor
        batch_processor = BatchURLProcessor(
            scraper=processors['scraper'],
            parser=processors['parser'],
            doc_downloader=processors['doc_downloader'],
            max_concurrent=max_concurrent,
            timeout=timeout
        )
        
        try:
            # Create progress container
            progress_container = st.empty()
            progress_container.info("Starting batch processing...")
            
            # Process URLs
            results = batch_processor.process_file(temp_file)
            
            # Export results
            output_dir = Path(temp_dir) / 'results'
            result_files = batch_processor.export_results(results, output_dir)
            
            # Display results
            st.success("Batch processing completed!")
            
            # Display summary
            with open(result_files['summary'], 'r') as f:
                summary = json.load(f)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total URLs", summary['total_urls'])
            with col2:
                st.metric("Successful", summary['successful'])
            with col3:
                st.metric("Failed", summary['failed'])
            
            # Display detailed results in tabs
            result_tabs = st.tabs(["Successful URLs", "Failed URLs", "Downloaded Files"])
            
            with result_tabs[0]:
                successful = [r for r in summary['urls'] if r['status'] == 'success']
                if successful:
                    st.dataframe(pd.DataFrame(successful))
                else:
                    st.info("No successful URLs")
            
            with result_tabs[1]:
                failed = [r for r in summary['urls'] if r['status'] != 'success']
                if failed:
                    st.dataframe(pd.DataFrame(failed))
                else:
                    st.info("No failed URLs")
            
            with result_tabs[2]:
                # Read detailed results for file information
                with open(result_files['details'], 'r') as f:
                    detailed_results = json.load(f)
                
                for result in detailed_results:
                    if result['downloaded_files']:
                        st.subheader(f"Files from {result['url']}")
                        for category, files in result['downloaded_files'].items():
                            st.write(f"**{category}**")
                            for file_path in files:
                                filename = os.path.basename(file_path)
                                with open(file_path, 'rb') as f:
                                    st.download_button(
                                        label=f"Download {filename}",
                                        data=f,
                                        file_name=filename,
                                        mime="application/octet-stream",
                                        key=file_path
                                    )
            
            # Download complete results
            with open(result_files['details'], 'rb') as f:
                st.download_button(
                    label="Download Complete Results (JSON)",
                    data=f,
                    file_name="batch_processing_results.json",
                    mime="application/json"
                )
            
        except Exception as e:
            st.error(f"Error during batch processing: {str(e)}")
        
        finally:
            # Cleanup temporary files
            for file in temp_file.parent.glob('**/*'):
                if file.is_file():
                    file.unlink()
            temp_file.parent.rmdir()
