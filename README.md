
# LLM Web Scraper with Document Parser

A powerful web scraping and document parsing tool that combines the capabilities of LangChain, Ollama, and Streamlit to create an intuitive interface for extracting, analyzing, and downloading web content and documents.

## ⚠️ Important Notice

## 💻 Class Architecture

1. **WebScraper (scraper.py)**

```python
class WebScraper:
    def scrape_page(self, url: str) -> str
    def extract_body_content(self, html: str) -> str
    def clean_body_content(self, content: str) -> str
    def split_dom_content(self, content: str) -> List[str]
```
- Responsibilities:
    - Web page fetching
    - Content extraction
    - Text cleaning
    - Content splitting

- Scaling Opportunities:
    - Add proxy support
    - Implement rate limiting
    - Add JavaScript rendering support
    - Include sitemap parsing
    - Add support for authentication


2. **OllamaParser (parse.py)**
```python
class OllamaParser:
    def __init__(self, model_name: str, download_dir: str)
    def parse_with_ollama(self, dom_chunks: List[str], parse_description: str) -> str
    def download_file(self, url: str, filename: Optional[str] = None) -> str
    def download_images_from_html(self, html_content: str) -> List[str]
```
- Responsibilities:
    - Content parsing
    - File downloading
    - Image extraction
    - LLM interaction

- Scaling Opportunities:
    - Add model switching
    - Implement caching
    - Add batch processing
    - Include custom prompts
    - Add result validation

3. **DocumentDownloader (document_downloader.py)**
```python
class DocumentDownloader:
    def __init__(self, base_url: str, download_dir: str)
    def find_document_links(self, html_content: str) -> List[DocumentLink]
    def download_documents(self, document_links: List[DocumentLink]) -> Dict[str, List[str]]
```
- Responsibilities:
    - Document detection
    - Link extraction
    - File categorization
    - Parallel downloading

- Scaling Opportunities:
    - Add OCR capabilities
    - Implement file preview
    - Add metadata extraction
    - Include file validation
    - Add compression support


## 🌟 Features

### Web Scraping

- Robust HTML content extraction
- Clean text processing
- Automatic document detection
- Multi-format file downloading
- Parallel processing capabilities

### Document Processing

- Intelligent document categorization
- Support for multiple file types (PDF, DOC, DOCX, etc.)
- Organized downloads by document type
- Size and progress tracking
- Duplicate file handling

### Content Parsing

- LLM-powered content analysis
- Custom parsing instructions
- Batch processing
- Error handling and recovery

### User Interface

- Clean, intuitive Streamlit interface
- Real-time progress tracking
- Expandable content sections
- Download management
- Category-based organization

## 🚀 Installation

### Prerequisites

1. Python 3.8+
```bash
python --version
```
2. Ollama Installation
- For windows:
```link
https://ollama.com/download/windows
```
- For Linux/WSL:
```bash
curl https://ollama.ai/install.sh | sh
```
- For macOS:
```bash
brew install ollama
```
3. Start Ollama Service:
```bash
ollama serve
```
4. Pull Required Model:
```bash
ollama pull llama3
```
```bash
  pip install selenium
```

## Project Setup
1. Clone the Repository
```bash
git clone https://github.com/XenosWarlocks/LLM-Scraper.git
cd llm-web-scraper
```
2. Create Virtual Environment
```bash
python -m venv venv

# For Windows
.\venv\Scripts\activate

# For Linux/macOS
source venv/bin/activate
```

3. Install Dependencies
```bash
pip install -r requirements.txt
```

## Requirements.txt
```text
streamlit==1.27.0
langchain==0.0.300
langchain-ollama==0.0.1
beautifulsoup4==4.12.2
requests==2.31.0
humanize==4.8.0
```


## 🏗️ Project Structure
```bash
llm-web-scraper/
│
├── main.py              # Streamlit application entry point
├── scraper.py          # Web scraping functionality
├── parse.py            # Ollama parsing implementation
├── document_downloader.py  # Document handling
├── requirements.txt    # Project dependencies
└── README.md          # Project documentation
```
## 🎯 Use Cases

1. Content Analysis
- Extract specific information from web pages
- Analyze product specifications
- Gather competitive intelligence

2. Document Management

- Download technical documentation
- Organize user manuals
- Archive installation guides


3. Research

- Extract research papers
- Gather technical specifications
- Collect product documentation


4. Data Mining

- Extract structured data
- Analyze web content
- Generate reports

## 🔄 Usage

1. Start the Application
```bash
streamlit run main.py

```

2. Enter Website URL

- Input the target website URL
- Click "Scrape" to begin extraction


3. Parse Content

- Describe what information to extract
- Review parsed results
- Download extracted content


4. Download Documents

- View categorized documents
- Check file sizes
- Download selected files

## 🚀 Future Improvements

1. Performance Enhancements

- Implement caching
- Add batch processing
- Optimize memory usage
- Add distributed processing


2. Feature Additions

- PDF text extraction
- Document summarization
- Content translation
- API integration


3. UI Improvements

- Dark mode support
- Custom themes
- Mobile optimization
- Advanced filters


4. Integration Options

- Database storage
- Cloud storage support
- Export formats
- API endpoints


5. Security Features

- Rate limiting
- Access control
- Content validation
- Secure storage

## 🤝 Contributing
Feel free to contribute to this project by:

1. Forking the repository
2. Creating a new branch
3. Making your changes
4. Submitting a pull request

