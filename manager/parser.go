package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strings"
	"sync"

	"github.com/sashabaranov/go-openai"
	"golang.org/x/net/html"
	"golang.org/x/sync/semaphore"
)

// Configuration for the parser
type ParserConfig struct {
	APIKey        string `json:"api_key"`
	ModelName     string `json:"model_name"`
	DataDir       string `json:"data_dir"`
	MaxConcurrent int    `json:"max_concurrent"`
	Timeout       int    `json:"timeout"`
}

// ParseResult struct to hold the results of parsing a website
type ParseResult struct {
	SiteID            string      `json:"site_id"`
	ContentAnalysis   interface{} `json:"content_analysis"` // Placeholder for ContentAnalyzer results
	ImageMatches      interface{} `json:"image_matches"`    // Placeholder for ImageMatch results
	RawContent        string      `json:"raw_content"`
	GeminiParseResult interface{} `json:"gemini_parse_result"`
	DownloadedFiles   []string    `json:"downloaded_files"`
	PdfLinks          []string    `json:"pdf_links"`
}

// BatchProcessingResult struct for batch processing results
type BatchProcessingResult struct {
	Successful []ParseResult `json:"successful"`
	Failed     []string      `json:"failed"`
}

// UnifiedParser main parsing struct
type UnifiedParser struct {
	config          ParserConfig
	client          *openai.Client
	contentAnalyzer *ContentAnalyzer  // Placeholder
	siteScraper     *SiteScraper      // Placeholder
	imageLoader     *ImageLoader      // Placeholder
	resultManager   *CSVResultManager // Placeholder
	dataDir         string
	resultsDir      string
	docDownloader   *DocumentDownloader // Placeholder

	prompt string

	// Add semaphore for concurrency control
	sem *semaphore.Weighted
}

// NewUnifiedParser creates a new instance of the UnifiedParser.
func NewUnifiedParser(config ParserConfig) (*UnifiedParser, error) {

	client := openai.NewClient(config.APIKey)

	dataDir := config.DataDir
	resultsDir := filepath.Join(config.DataDir, "parse_results")
	if err := os.MkdirAll(resultsDir, os.ModePerm); err != nil {
		return nil, fmt.Errorf("failed to create results directory: %w", err)
	}

	prompt := `
		Analyze the following website content and extract relevant information based on the query.

		Website Content: {dom_content}

		Query: {parse_description}

		For product information queries, include details about:
		- Product name
		- Model number
		- Serial number
		- Warranty information
		- User manuals (with URLs if available)
		- Other relevant documents (with URLs if available)

		For other queries:
		- Provide relevant information from the content
		- Include specific data points when found
		- Return document/image URLs when relevant
		- Indicate if information is not found

		Please provide the information in a clear, structured format.
	`

	// Initialize the semaphore
	sem := semaphore.NewWeighted(int64(config.MaxConcurrent))

	return &UnifiedParser{
		config:          config,
		client:          client,
		contentAnalyzer: NewContentAnalyzer(config.APIKey, config.DataDir), // Initialize placeholder
		siteScraper:     NewSiteScraper(config.DataDir),                    // Initialize placeholder
		imageLoader:     NewImageLoader(),                                  // Initialize placeholder
		resultManager:   NewCSVResultManager(config.DataDir),               // Initialize placeholder
		dataDir:         dataDir,
		resultsDir:      resultsDir,
		docDownloader:   NewDocumentDownloader("", config.DataDir), // Initialize placeholder
		prompt:          prompt,
		sem:             sem,
	}, nil

}

// CreateBatchProcessor creates a BatchURLProcessor.
func (p *UnifiedParser) CreateBatchProcessor(modelNumber string) *BatchURLProcessor {

	return NewBatchURLProcessor(p.siteScraper, p, p.docDownloader, p.config.MaxConcurrent, p.config.Timeout, p.resultManager, modelNumber)
}

func (p *UnifiedParser) preprocessContent(htmlContent string) []string {
	doc, err := html.Parse(strings.NewReader(htmlContent))
	if err != nil {
		log.Printf("Error parsing HTML: %v", err)
		return nil
	}

	var texts []string
	var f func(*html.Node)
	f = func(n *html.Node) {
		if n.Type == html.TextNode && strings.TrimSpace(n.Data) != "" {
			texts = append(texts, strings.TrimSpace(n.Data))
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			f(c)
		}
	}
	f(doc)
	return texts
}

// parseWithGemini sends a request to Gemini and parses the response.
func (p *UnifiedParser) parseWithGemini(ctx context.Context, domChunks []string, parseDescription string) (interface{}, error) {
	if err := p.sem.Acquire(ctx, 1); err != nil {
		return nil, fmt.Errorf("failed to acquire semaphore: %w", err)
	}
	defer p.sem.Release(1)

	foundResults := []interface{}{}
	isProductInfo := containsAny(strings.ToLower(parseDescription), []string{"extract product", "product information", "product details"})

	chunkSize := 3
	for i := 0; i < len(domChunks); i += chunkSize {
		chunkGroup := strings.Join(domChunks[i:min(i+chunkSize, len(domChunks))], " ")

		req := openai.ChatCompletionRequest{
			Model: p.config.ModelName,
			Messages: []openai.ChatCompletionMessage{
				{
					Role:    openai.ChatMessageRoleUser,
					Content: strings.ReplaceAll(strings.ReplaceAll(p.prompt, "{dom_content}", chunkGroup), "{parse_description}", parseDescription),
				},
			},
		}

		resp, err := p.client.CreateChatCompletion(ctx, req)
		if err != nil {

			return nil, fmt.Errorf("gemini request failed: %w", err)

		}
		content := resp.Choices[0].Message.Content

		content = strings.TrimSpace(content)

		if content == "" || strings.ToLower(content) == "no match" || strings.ToLower(content) == "not found" || strings.ToLower(content) == "no information" {
			continue
		}

		if isProductInfo {
			var result map[string]interface{}
			if err := json.Unmarshal([]byte(content), &result); err == nil {

				ensureKeyExists(result, "name", "NO_MATCH")
				ensureKeyExists(result, "model_number", "NO_MATCH")
				ensureKeyExists(result, "serial_number", "NO_MATCH")
				ensureKeyExists(result, "warranty_info", "NO_MATCH")
				ensureKeyExists(result, "user_manual", []string{})
				ensureKeyExists(result, "other_documents", []string{})

				for _, key := range []string{"user_manual", "other_documents"} {

					if val, ok := result[key].(string); ok && val != "NO_MATCH" {
						result[key] = []string{val}
					}
				}

				foundResults = append(foundResults, result)
			} else {
				foundResults = append(foundResults, map[string]interface{}{"raw_content": content})
			}
		} else {
			foundResults = append(foundResults, content)
		}

	}

	if len(foundResults) == 0 {
		return "NO_MATCH", nil
	}

	if isProductInfo {
		combinedResults := map[string]interface{}{
			"name":            "NO_MATCH",
			"model_number":    "NO_MATCH",
			"serial_number":   "NO_MATCH",
			"warranty_info":   "NO_MATCH",
			"user_manual":     []string{},
			"other_documents": []string{},
			"additional_info": []string{},
		}
		for _, result := range foundResults {
			if rawContent, ok := result.(map[string]interface{})["raw_content"]; ok {

				combinedResults["additional_info"] = append(combinedResults["additional_info"].([]string), rawContent.(string))
				continue

			}

			for k, v := range result.(map[string]interface{}) {
				switch k {

				case "user_manual", "other_documents":
					if list, ok := v.([]string); ok {
						combinedResults[k] = append(combinedResults[k].([]string), list...)
					} else if str, ok := v.(string); ok && str != "NO_MATCH" {
						combinedResults[k] = append(combinedResults[k].([]string), str)
					}

				default:
					if str, ok := v.(string); ok && str != "NO_MATCH" {

						if _, ok := combinedResults[k].(string); ok && combinedResults[k].(string) == "NO_MATCH" {
							combinedResults[k] = str
						}
					}
				}
			}
		}
		dedupeStringSlice(combinedResults, "user_manual")
		dedupeStringSlice(combinedResults, "other_documents")
		dedupeStringSlice(combinedResults, "additional_info")

		return combinedResults, nil
	}
	combinedContent := strings.Join(interfaceSliceToStringSlice(foundResults), "\n")
	return combinedContent, nil

}

func containsAny(s string, substrings []string) bool {
	for _, substr := range substrings {
		if strings.Contains(s, substr) {
			return true
		}
	}
	return false
}

func interfaceSliceToStringSlice(in []interface{}) []string {
	out := make([]string, len(in))
	for i, v := range in {
		out[i] = v.(string)
	}
	return out
}

func ensureKeyExists(m map[string]interface{}, key string, defaultValue interface{}) {
	if _, ok := m[key]; !ok {
		m[key] = defaultValue
	}
}

func dedupeStringSlice(m map[string]interface{}, key string) {
	if slice, ok := m[key].([]string); ok {
		allKeys := make(map[string]bool)
		list := []string{}
		for _, item := range slice {
			if _, value := allKeys[item]; !value {
				allKeys[item] = true
				list = append(list, item)
			}
		}
		m[key] = list
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// findPdfLinks extracts PDF links from the provided HTML content.
func (p *UnifiedParser) findPdfLinks(htmlContent string) ([]string, error) {
	doc, err := html.Parse(strings.NewReader(htmlContent))
	if err != nil {
		return nil, fmt.Errorf("failed to parse HTML content: %w", err)
	}

	allowedExtensions := []string{".pdf", ".docx"}
	var links []string
	var f func(*html.Node)
	f = func(n *html.Node) {
		if n.Type == html.ElementNode && n.Data == "a" {
			for _, a := range n.Attr {
				if a.Key == "href" {
					href := strings.TrimSpace(a.Val)
					if href != "" {
						if strings.HasPrefix(href, "#") {
							continue
						}

						if hasSuffix(href, allowedExtensions) {
							u, err := url.Parse(href)
							if err != nil {
								continue
							}
							if !u.IsAbs() {
								base, err := url.Parse(p.siteScraper.baseURL)
								if err != nil {
									continue
								}
								u = base.ResolveReference(u)
							}
							links = append(links, u.String())
						}
					}
				}
			}
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			f(c)
		}
	}

	f(doc)
	return removeDuplicates(links), nil
}

// Updated function with a comparable constraint
func removeDuplicates[T comparable](slice []T) []T {
	allKeys := make(map[T]bool)
	list := []T{}

	for _, item := range slice {
		if _, exists := allKeys[item]; !exists {
			allKeys[item] = true
			list = append(list, item)
		}
	}
	return list
}

func hasSuffix(s string, suffixes []string) bool {
	s = strings.ToLower(s)
	for _, suffix := range suffixes {
		if strings.HasSuffix(s, strings.ToLower(suffix)) {
			return true
		}
	}
	return false
}

// downloadDocuments downloads documents from the provided links.
func (p *UnifiedParser) downloadDocuments(ctx context.Context, docLinks []string, siteID string) (map[string][]string, error) {

	docDir := filepath.Join(p.dataDir, siteID, "documents")

	if err := os.MkdirAll(docDir, os.ModePerm); err != nil {
		return nil, fmt.Errorf("failed to create documents directory: %w", err)
	}

	p.docDownloader.baseURL = p.siteScraper.baseURL
	p.docDownloader.downloadDir = docDir
	return p.docDownloader.downloadDocumentsAsync(ctx, docLinks)
}

func (p *UnifiedParser) parseWebsiteBatch(ctx context.Context, urls []string, parseDescription string, modelNumber string) (BatchProcessingResult, error) {
	var result BatchProcessingResult
	var wg sync.WaitGroup
	var mutex sync.Mutex // Add mutex for thread safety

	for _, u := range urls {
		wg.Add(1)
		go func(url string) {
			defer wg.Done()

			parseResult, err := p.parseWebsite(ctx, url, 0.7, false, parseDescription, modelNumber)
			mutex.Lock()
			if err != nil {
				result.Failed = append(result.Failed, url)
			} else {
				result.Successful = append(result.Successful, parseResult)
			}
			mutex.Unlock()
		}(u)
	}

	wg.Wait() // Wait for all goroutines to finish
	return result, nil
}

func (p *UnifiedParser) parseWebsite(ctx context.Context, websiteURL string, minConfidence float64, showAllImages bool, parseDescription string, modelNumber string) (ParseResult, error) {

	normalizedURL, err := validateAndNormalizeURL(websiteURL)
	if err != nil {
		return ParseResult{}, err
	}

	siteDir, siteID, err := p.siteScraper.createSiteFolder(websiteURL)
	if err != nil {
		return ParseResult{}, err
	}
	log.Printf("Site directory created: %s", siteDir)

	htmlContent, err := p.siteScraper.scrapeWebsite(ctx, normalizedURL)
	if err != nil {

		return ParseResult{}, fmt.Errorf("failed to scrape website: %w", err)
	}

	cleanedContent := cleanContent(htmlContent) // Implement cleanContent

	images, err := extractImages(htmlContent, websiteURL)

	if err != nil {
		return ParseResult{}, fmt.Errorf("failed to extract images: %w", err)
	}

	imageURLs := make([]string, len(images))
	for i, img := range images {
		imageURLs[i] = resolveRelativeURL(normalizedURL, img["url"])
	}

	downloadedImages, err := p.imageLoader.downloadImages(ctx, imageURLs, normalizedURL)

	if err != nil {
		log.Printf("Failed to download images: %v", err)

	}

	downloadedFiles := make([]string, len(downloadedImages))
	for i, img := range downloadedImages {
		downloadedFiles[i] = img
	}

	p.siteScraper.baseURL = websiteURL
	pdfLinks, err := p.findPdfLinks(htmlContent)
	if err != nil {
		return ParseResult{}, fmt.Errorf("failed to find PDF links: %w", err)
	}

	contentAnalysis := p.contentAnalyzer.analyzeContent(cleanedContent)

	imageMatches := p.contentAnalyzer.findMatchingImages(contentAnalysis, imageURLs, minConfidence, showAllImages) // Implement image matching

	var geminiResult interface{}
	if parseDescription != "" {

		geminiResult, err = p.parseWithGemini(ctx, p.preprocessContent(cleanedContent), parseDescription)
		if err != nil {
			return ParseResult{}, fmt.Errorf("failed to parse with Gemini: %w", err)
		}
	}

	result := ParseResult{
		SiteID:            siteID,
		ContentAnalysis:   contentAnalysis,
		ImageMatches:      imageMatches,
		RawContent:        cleanedContent,
		GeminiParseResult: geminiResult,
		DownloadedFiles:   downloadedFiles,
		PdfLinks:          pdfLinks,
	}

	if p.resultManager != nil && modelNumber != "" {

		p.resultManager.saveResult(result, modelNumber, websiteURL)
	}

	if err := p.saveParseResult(result); err != nil {
		return ParseResult{}, fmt.Errorf("failed to save parse result: %w", err)
	}

	return result, nil
}

// saveParseResult saves the parse result to a JSON file.
func (p *UnifiedParser) saveParseResult(result ParseResult) error {
	resultPath := filepath.Join(p.resultsDir, fmt.Sprintf("%s.json", result.SiteID))
	jsonData, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal JSON: %w", err)
	}

	if err := ioutil.WriteFile(resultPath, jsonData, 0644); err != nil {
		return fmt.Errorf("failed to write JSON file: %w", err)
	}
	return nil

}

// Placeholder functions to be implemented
func cleanContent(html string) string {
	return html
}
func NewImageLoader() *ImageLoader {

	return &ImageLoader{}
}

func (l *ImageLoader) downloadImages(ctx context.Context, urls []string, normalizedURL string) ([]string, error) {
	// Placeholder logic to use the parameters
	if len(urls) == 0 {
		log.Printf("No images to download from: %s", normalizedURL)
	}
	return []string{}, nil
}

func extractImages(content string, websiteURL string) ([]map[string]string, error) {
	// Placeholder logic to use the parameters
	log.Printf("Extracting images from website: %s", websiteURL)
	return []map[string]string{}, nil
}

func resolveRelativeURL(baseURL, relativeURL string) string {

	base, err := url.Parse(baseURL)
	if err != nil {
		return relativeURL // Handle error as needed
	}

	relative, err := url.Parse(relativeURL)
	if err != nil {
		return relativeURL // Handle error as needed
	}

	return base.ResolveReference(relative).String()

}

type ContentAnalyzer struct {
	apiKey  string
	dataDir string
}

func NewContentAnalyzer(apiKey, dataDir string) *ContentAnalyzer {
	return &ContentAnalyzer{apiKey: apiKey, dataDir: dataDir}
}

func (ca *ContentAnalyzer) analyzeContent(content string) interface{} {

	return nil
}

func (ca *ContentAnalyzer) findMatchingImages(contentAnalysis interface{}, availableImages []string, minConfidence float64, showAllImages bool) []map[string]interface{} {
	// Placeholder for image matching logic
	return nil
}

type ImageLoader struct {
}

type SiteScraper struct {
	baseURL     string
	downloadDir string
}

func NewSiteScraper(downloadDir string) *SiteScraper {

	return &SiteScraper{downloadDir: downloadDir}
}

func (s *SiteScraper) createSiteFolder(websiteURL string) (string, string, error) {
	parsedURL, err := url.Parse(websiteURL)
	if err != nil {
		return "", "", fmt.Errorf("failed to parse URL: %w", err)
	}

	siteDir := filepath.Join(s.downloadDir, parsedURL.Host) // Use hostname for the folder name
	if err := os.MkdirAll(siteDir, os.ModePerm); err != nil {
		return "", "", fmt.Errorf("failed to create site directory: %w", err)
	}
	siteId := path.Base(siteDir)
	return siteDir, siteId, nil

}

func (s *SiteScraper) scrapeWebsite(ctx context.Context, url string) (string, error) {

	return "", nil
}

type DocumentDownloader struct {
	baseURL     string
	downloadDir string
}

func NewDocumentDownloader(baseURL, downloadDir string) *DocumentDownloader {
	return &DocumentDownloader{baseURL: baseURL, downloadDir: downloadDir}
}

func (d *DocumentDownloader) downloadDocumentsAsync(ctx context.Context, docLinks []string) (map[string][]string, error) {

	return make(map[string][]string), nil
}

type CSVResultManager struct {
	dataDir string
}

func NewCSVResultManager(dataDir string) *CSVResultManager {
	return &CSVResultManager{dataDir: dataDir}
}

func (rm *CSVResultManager) saveResult(result ParseResult, modelNumber string, url string) {

}

func validateAndNormalizeURL(u string) (string, error) {

	return u, nil
}

// BatchURLProcessor handles batch processing of URLs.
type BatchURLProcessor struct {
	scraper       *SiteScraper
	parser        *UnifiedParser
	docDownloader *DocumentDownloader
	maxConcurrent int
	timeout       int
	resultManager *CSVResultManager
	modelNumber   string
}

func NewBatchURLProcessor(scraper *SiteScraper, parser *UnifiedParser, docDownloader *DocumentDownloader, maxConcurrent int, timeout int, resultManager *CSVResultManager, modelNumber string) *BatchURLProcessor {
	return &BatchURLProcessor{scraper: scraper, parser: parser, docDownloader: docDownloader, maxConcurrent: maxConcurrent, timeout: timeout, resultManager: resultManager, modelNumber: modelNumber}
}

// ProcessURLs processes a batch of URLs.
func (p *BatchURLProcessor) ProcessURLs(ctx context.Context, urls []string, parseDescription string) (BatchProcessingResult, error) {
	return p.parser.parseWebsiteBatch(ctx, urls, parseDescription, p.modelNumber)

}
