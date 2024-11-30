# unused
# scraper.py
from selenium.webdriver import Remote, ChromeOptions
from selenium import webdriver
from selenium.webdriver.chromium.remote_connection import ChromiumRemoteConnection
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import time

class WebScraper:
    def __init__(self):
        self.driver = None
        
    def setup_driver(self):
        """Setup and return Chrome WebDriver with some basic options"""
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless")  # Run in headless mode, no UI
        options.add_argument('--disable-gpu') # Disable GPU acceleration
        options.add_argument('--no-sandbox') # Disable sandbox for Linux-based systems
        options.add_argument('--disable-dev-shm-usage') # Solve issues with shared memory in Docker
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(90) # Timeout for page loading
        return self.driver
    
    def scrape_page(self, url: str):
        """Scrape the page content from the given URL."""
        try:
            if not self.driver:
                self.setup_driver()

            # Open the URL
            self.driver.get(url)
            page_source = self.driver.page_source
            time.sleep(3)

            # Pass the page source to BeautifulSoup for parsing
            soup = BeautifulSoup(page_source, 'html.parser')
            return soup.prettify()
        except Exception as e:
            print(f"Error scraping website: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()
    
    def extract_body_content(self, html_content):
        """Extract the body content from the HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        body_content = soup.body
        if body_content:
            return str(body_content)
        return ""
    
    def clean_body_content(self, body_content):
        """Clean the body content by removing scripts, styles, and unwanted tags."""
        soup = BeautifulSoup(body_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()

        cleaned_content = soup.get_text(separator='\n')
        cleaned_content = '\n'.join(line.strip() for line in cleaned_content.split('\n') if line.strip())
        return cleaned_content
    
    def split_dom_content(self, dom_content, max_length=4000):
        """Split the DOM content into chunks."""
        return [dom_content[i:i + max_length] for i in range(0, len(dom_content), max_length)]