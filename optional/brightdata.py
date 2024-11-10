# scraper.py
from selenium import webdriver
# from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
from selenium.webdriver import Remote
from bs4 import BeautifulSoup
from selenium.webdriver import Remote, ChromeOptions
from selenium.webdriver.chromium.remote_connection import ChromiumRemoteConnection
from selenium.webdriver.common.by import By

AUTH = 'brd-customer-hl_0f17948b-zone-scraping_sites:oyzs5ko3ksd2'
SBR_WEBDRIVER = f'https://{AUTH}@zproxy.lum-superproxy.io:9515' # change it to your own api

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

        # Connect to the remote WebDriver (Scraping Browser endpoint)
        remote_url = SBR_WEBDRIVER
        
        self.driver = Remote(
            command_executor=remote_url,
            options=options
        )
        self.driver.set_page_load_timeout(90) # Timeout for page loading
        return self.driver
    
    def scrape_page(self, url: str):
        """Scrape the page content from the given URL."""
        print('Connecting to Scraping Browser...')
        sbr_connection = ChromiumRemoteConnection(SBR_WEBDRIVER, 'goog', 'chrome')
        with Remote(sbr_connection, options=ChromeOptions()) as driver:
            print('Connected! Navigating...')
        driver.get(url)
        # 
        solve_res = driver.execute('executeCdpCommand', {
            'cmd': 'Captcha.waitForSolve',
            'params': {
                'detectTimeout': 10000
            }
        })
        print('Captcha solve status: ', solve_res['value']['status'])
        print('Navigated! Scraping page content...')
        html = driver.page_source
        return html
    
    def extract_body_content(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        body_content = soup.body
        if body_content:
            return str(body_content)
        return ""

    def clean_body_content(body_content):
        soup = BeautifulSoup(body_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()

        cleaned_content = soup.get_text(separator='\n')
        cleaned_content = '\n'.join(line.strip() for line in cleaned_content.split('\n') if line.strip())
        return cleaned_content
    
    def split_dom_content(dom_content, max_length=4000):
        return [dom_content[i:i + max_length] for i in range(0, len(dom_content), max_length)]
