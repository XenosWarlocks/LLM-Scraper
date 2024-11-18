package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
)

// BatchJob represents a single URL processing job
type BatchJob struct {
	ModelNumber      string  `json:"model_number"`
	URL              string  `json:"url"`
	Status           string  `json:"status"`
	Error            string  `json:"error,omitempty"`
	Progress         int     `json:"progress"`
	ParseDescription *string `json:"parse_description,omitempty"`
}

// BatchProcess represents the entire batch processing request
type BatchProcess struct {
	ID        string      `json:"id"`
	Jobs      []BatchJob  `json:"jobs"`
	Status    string      `json:"status"`
	Progress  int         `json:"progress"`
	StartTime time.Time   `json:"start_time"`
	EndTime   time.Time   `json:"end_time,omitempty"`
	mu        sync.Mutex  // For thread-safe updates
	clients   []chan bool // For WebSocket updates
}

type ParseRequest struct {
	URL              string  `json:"url"`
	ModelNumber      string  `json:"model_number"`
	ParseDescription *string `json:"parse_description,omitempty"`
	MinConfidence    float64 `json:"min_confidence,omitempty"`
	ShowAllImages    bool    `json:"show_all_images,omitempty"`
}

type ImageMatch struct {
	URL        string  `json:"url"`
	Confidence float64 `json:"confidence"`
	Context    string  `json:"context"`
}

type ParseResponse struct {
	SiteID          string                 `json:"site_id"`
	ContentAnalysis map[string]interface{} `json:"content_analysis"`
	ImageMatches    []ImageMatch           `json:"image_matches"`
	DownloadedFiles []string               `json:"downloaded_files"`
	PDFLinks        []string               `json:"pdf_links"`
	GeminiResult    interface{}            `json:"gemini_result"`
	Status          string                 `json:"status"`
	Error           string                 `json:"error,omitempty"`
}

var (
	processes = make(map[string]*BatchProcess)
	upgrader  = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool {
			return true // Allow all origins for development
		},
	}
)

// processURL processes a single URL and integrates with Python functions
func (job *BatchJob) processURL(baseDir string) error {
	// Create model number directory
	modelDir := filepath.Join(baseDir, job.ModelNumber)
	if err := os.MkdirAll(modelDir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %v", err)
	}

	// Prepare request data
	request := ParseRequest{
		URL:           job.URL,
		ModelNumber:   job.ModelNumber,
		MinConfidence: 0.7,
		ShowAllImages: false,
	}

	// Add optional parse description if provided
	if job.ParseDescription != nil && *job.ParseDescription != "" {
		request.ParseDescription = job.ParseDescription
	}

	// Convert request to JSON
	jsonData, err := json.Marshal(request)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %v", err)
	}

	// Create HTTP client with timeout
	client := &http.Client{
		Timeout: time.Second * 180, // 3 minutes timeout
	}

	// Retry configuration
	maxRetries := 3
	retryDelay := time.Second * 5
	var resp *http.Response
	var lastErr error

	// Retry loop for HTTP requests
	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(retryDelay)
			log.Printf("Retrying request (attempt %d/%d) for URL: %s", attempt+1, maxRetries, job.URL)
		}

		// Make request to Python service
		resp, err = client.Post("http://your-python-service/parse", "application/json", strings.NewReader(string(jsonData)))
		if err == nil {
			break
		}
		lastErr = err
		log.Printf("Request failed (attempt %d/%d): %v", attempt+1, maxRetries, err)
	}

	if resp == nil {
		return fmt.Errorf("failed after %d attempts: %v", maxRetries, lastErr)
	}
	defer resp.Body.Close()

	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response: %v", err)
	}

	// Check status code
	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.Unmarshal(body, &errorResp); err != nil {
			return fmt.Errorf("server error (status %d): %s", resp.StatusCode, string(body))
		}
		return fmt.Errorf("server error (status %d): %s", resp.StatusCode, errorResp.Error)
	}

	// Parse response
	var parseResponse ParseResponse
	if err := json.Unmarshal(body, &parseResponse); err != nil {
		return fmt.Errorf("failed to parse response: %v", err)
	}

	// Handle successful response
	if parseResponse.Status != "success" {
		return fmt.Errorf("processing failed: %s", parseResponse.Error)
	}

	// Process and save results
	if err := job.saveResults(modelDir, &parseResponse); err != nil {
		return fmt.Errorf("failed to save results: %v", err)
	}

	// Log success with details
	log.Printf("Successfully processed URL %s for model %s:", job.URL, job.ModelNumber)
	log.Printf("- Site ID: %s", parseResponse.SiteID)
	log.Printf("- Downloaded Files: %d", len(parseResponse.DownloadedFiles))
	log.Printf("- PDF Links: %d", len(parseResponse.PDFLinks))
	log.Printf("- Image Matches: %d", len(parseResponse.ImageMatches))

	return nil
}

// saveResults handles saving the parsed results to the appropriate location
func (job *BatchJob) saveResults(modelDir string, result *ParseResponse) error {
	resultsDir := filepath.Join(modelDir, "results")
	if err := os.MkdirAll(resultsDir, 0755); err != nil {
		return fmt.Errorf("failed to create results directory: %v", err)
	}

	// Save main results as JSON
	resultsFile := filepath.Join(resultsDir, "parse_results.json")
	resultData, err := json.MarshalIndent(result, "", "    ")
	if err != nil {
		return fmt.Errorf("failed to marshal results: %v", err)
	}

	if err := os.WriteFile(resultsFile, resultData, 0644); err != nil {
		return fmt.Errorf("failed to write results file: %v", err)
	}

	// Save image matches to separate file
	if len(result.ImageMatches) > 0 {
		imagesFile := filepath.Join(resultsDir, "image_matches.csv")
		imageData, err := json.MarshalIndent(result.ImageMatches, "", "    ")
		if err != nil {
			return fmt.Errorf("failed to marshal image matches: %v", err)
		}
		if err := os.WriteFile(imagesFile, imageData, 0644); err != nil {
			return fmt.Errorf("failed to write image matches file: %v", err)
		}
	}

	// Save PDF links to text file
	if len(result.PDFLinks) > 0 {
		pdfFile := filepath.Join(resultsDir, "pdf_links.txt")
		pdfData := strings.Join(result.PDFLinks, "\n")
		if err := os.WriteFile(pdfFile, []byte(pdfData), 0644); err != nil {
			return fmt.Errorf("failed to write PDF links file: %v", err)
		}
	}
	return nil
}

type Config struct {
    MaxConcurrent int           `json:"max_concurrent"`
    Timeout       int           `json:"timeout"`
}

// handleFileUpload processes the uploaded CSV file
func handleFileUpload(w http.ResponseWriter, r *http.Request) {
    // Parse the multipart form
    if err := r.ParseMultipartForm(10 << 20); err != nil {
        http.Error(w, "File too large", http.StatusBadRequest)
        return
    }

    // Get config file from form if provided
    configFile, _, err := r.FormFile("config")
    if err == nil {
        defer configFile.Close()
        var config Config
        if err := json.NewDecoder(configFile).Decode(&config); err == nil {
            // Update worker pool size if provided
            if config.MaxConcurrent > 0 {
                numWorkers = config.MaxConcurrent
            }
            // Update timeout if provided
            if config.Timeout > 0 {
                // Convert seconds to duration
                timeout = time.Duration(config.Timeout) * time.Second
            }
        }
    }

    // Get the CSV file
    file, _, err := r.FormFile("file")
    if err != nil {
        http.Error(w, "Failed to retrieve the file", http.StatusBadRequest)
        return
    }
    defer file.Close()

    // Process CSV
    reader := csv.NewReader(file)
    // Skip header
    headers, err := reader.Read()
    if err != nil {
        http.Error(w, "Failed to read CSV header", http.StatusBadRequest)
        return
    }

    // Validate required columns
    requiredColumns := map[string]int{
        "url":          -1,
        "model_number": -1,
    }

    for i, header := range headers {
        header = strings.ToLower(strings.TrimSpace(header))
        if _, exists := requiredColumns[header]; exists {
            requiredColumns[header] = i
        }
    }

    // Check if all required columns are present
    for column, idx := range requiredColumns {
        if idx == -1 {
            http.Error(w, fmt.Sprintf("Missing required column: %s", column), http.StatusBadRequest)
            return
        }
    }

    // Create new batch process
    batchID := fmt.Sprintf("batch_%d", time.Now().UnixNano())
    process := &BatchProcess{
        ID:        batchID,
        Status:    "pending",
        StartTime: time.Now(),
        clients:   make([]chan bool, 0, 10), // Initialize with 0 length and capacity of 10
        Jobs:      make([]BatchJob, 0),      // Initialize empty jobs slice
    }

    // Read and process each record
    for {
        record, err := reader.Read()
        if err == io.EOF {
            break
        }
        if err != nil {
            http.Error(w, "Error reading CSV file", http.StatusBadRequest)
            return
        }

        // Create job from CSV record
        job := BatchJob{
            ModelNumber: record[requiredColumns["model_number"]],
            URL:         record[requiredColumns["url"]],
            Status:      "pending",
            Progress:    0,
        }

        // Optional: Parse description if present
        descriptionIdx := getColumnIndex(headers, "parse_description")
        if descriptionIdx != -1 && descriptionIdx < len(record) {
            description := record[descriptionIdx]
            if description != "" {
                job.ParseDescription = &description
            }
        }
        process.Jobs = append(process.Jobs, job)
    }

    // Validate that we have at least one job
    if len(process.Jobs) == 0 {
        http.Error(w, "No valid jobs found in the CSV file", http.StatusBadRequest)
        return
    }

    // Store the process
    processes[process.ID] = process

    // Return the batch ID
    response := map[string]string{
        "batch_id": process.ID,
        "status":   "pending",
        "message":  fmt.Sprintf("Successfully queued %d jobs", len(process.Jobs)),
    }
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}

// getColumnIndex helper function to find column index by name
func getColumnIndex(headers []string, columnName string) int {
	for i, header := range headers {
		if strings.ToLower(strings.TrimSpace(header)) == strings.ToLower(columnName) {
			return i
		}
	}
	return -1
}

// // updateJob updates a job in the batch process
//
//	func (bp *BatchProcess) updateJob(updatedJob BatchJob){
//		bp.mu.Lock()
//		defer bp.mu.Unlock()
//		// Find and update the job
//		for i := range bp.Jobs {
//			if bp.Jobs[i].URL == updatedJob.URL && bp.Jobs[i].ModelNumber == updatedJob.ModelNumber {
//				bp.Jobs[i] = updatedJob
//				break
//			}
//		}
//	}
//
// notifyClients sends updates to all connected WebSocket clients

	func (bp *BatchProcess) notifyClients() {
		bp.mu.Lock()
		defer bp.mu.Unlock()
		// Create status update
		update := map[string]interface{}{
			"id":       bp.ID,
			"status":   bp.Status,
			"progress": bp.Progress,
			"jobs":     bp.Jobs,
		}
		// Notify all clients
		for _, client := range bp.clients {
			select {
			case client <- true:
				// Successfully sent update
			default:
				// Channel is full or closed, skip
		}
	}

// startProcessing handles the batch processing with a worker pool
func (bp *BatchProcess) startProcessing() {
	bp.Status = "processing"
	numWorkers := 5 // Adjust based on your needs

	// Create channels for jobs and results
	jobs := make(chan BatchJob, len(bp.Jobs))
	results := make(chan BatchJob, len(bp.Jobs))
	var wg sync.WaitGroup

	// Start workers
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for job := range jobs {
				// Process each job's URL
				err := job.processURL("./data")
				if err != nil {
					job.Status = "failed"
					job.Error = err.Error()
				} else {
					job.Status = "completed"
				}
				results <- job
			}
		}()
	}

	// Send jobs to workers
	go func() {
		for _, job := range bp.Jobs {
			jobs <- job
		}
		close(jobs)
	}()

	// Collect results and update progress
	go func() {
		completed := 0
		total := len(bp.Jobs)
		for job := range results {
			completed++
			bp.updateJob(job)
			bp.Progress = (completed * 100) / total
			bp.notifyClients()

			if completed == total {
				close(results)
				bp.Status = "completed"
				bp.EndTime = time.Now()
				bp.notifyClients()
			}
		}
	}()

	wg.Wait()
}

// updateJob updates the status of a single job
func (bp *BatchProcess) updateJob(job BatchJob) {
	bp.mu.Lock()
	defer bp.mu.Unlock()
	for i, j := range bp.Jobs {
		if j.ModelNumber == job.ModelNumber && j.URL == job.URL {
			bp.Jobs[i] = job
			break
		}
	}
}
// handleWebSocket handles WebSocket connections for real-time updates
func handleWebSocket(w http.ResponseWriter, r *http.Request) {
	batchID := r.URL.Query().Get("batch_id")
	process, exists := processes[batchID]
	if !exists {
		http.Error(w, "Batch not found", http.StatusNotFound)
		return
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	updates := make(chan bool)
	process.mu.Lock()
	process.clients = append(process.clients, updates)
	process.mu.Unlock()

	defer func() {
		process.mu.Lock()
		for i, ch := range process.clients {
			if ch == updates {
				process.clients = append(process.clients[:i], process.clients[i+1:]...)
				break
			}
		}
		process.mu.Unlock()
		close(updates)
	}()

	// Send initial state
	if err := conn.WriteJSON(process); err != nil {
		return
	}

	// Listen for updates
	for range updates {
		if err := conn.WriteJSON(process); err != nil {
			return
		}
	}
}
func main() {
	router := mux.NewRouter()

	// Routes
	router.HandleFunc("/upload", handleFileUpload).Methods("POST")
	router.HandleFunc("/ws", handleWebSocket)

	// Start server
	log.Printf("Starting server on :8080")
	log.Fatal(http.ListenAndServe(":8080", router))
}
