import streamlit as st
from scraper import WebScraper
from bs4 import BeautifulSoup

# Page configuration
st.set_page_config(page_title="LLM Web Scraper", page_icon="🔍")

st.title("LLM Web Scraper")
st.write("Enter a website URL below, and click 'Scrape' to retrieve data from the site.")

# User input
url = st.text_input("Website URL:", placeholder="e.g., https://example.com")

if st.button("Scrape"):
    if url:
        st.info("Starting the scraping process, please wait...")
        scraper = WebScraper()  # Instantiate without passing URL in the constructor
        scraped_data = scraper.scrape_page(url)  # Pass URL to scrape_page method
        
        if scraped_data:
            st.success(f"Successfully scraped data from: {url}")
            
            # Extract the body content and clean it
            body_content = scraper.extract_body_content(scraped_data)  # Correct method call
            cleaned_content = scraper.clean_body_content(body_content)

            st.session_state.dom_content = cleaned_content  # Store cleaned content in session state

            with st.expander("Show DOM Content"):
                # Display the cleaned DOM content inside a text area
                st.text_area("DOM Content", st.session_state.dom_content, height=300)
        else:
            st.error("Failed to scrape data from the website.")
    else:
        st.warning("Please enter a valid URL.")




# streamlit run main.py
