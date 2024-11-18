import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime
from dataclasses import dataclass, asdict

from parse import UnifiedParser
from utils.parse_config import ParserConfig
from batch_processor import BatchURLProcessor, BatchProcessingResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BatchProcessingConfig:
    """Configuration for batch processing jobs"""
    input_file: str
    output_dir: str
    max_concurrent: int = 5
    timeout: int = 30
    min_confidence: float = 0.7
    default_model_number: Optional[str] = None
    parse_description: Optional[str] = None

class BatchProcessingManager:
    """Manages batch processing operations using UnifiedParser"""
    
    def __init__(self, config: ParserConfig):
        """Initialize with parser configuration"""
        self.parser = UnifiedParser(config)
        self.results_dir = Path(config.data_dir) / "batch_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    async def process_batch(self, batch_config: BatchProcessingConfig) -> Dict[str, Any]:
        """Process a batch of URLs from a file"""
        try:
            # Create batch processor
            processor = self.parser.create_batch_processor(
                max_concurrent=batch_config.max_concurrent,
                timeout=batch_config.timeout
            )
            
            # Ensure output directory exists
            output_dir = Path(batch_config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Process URLs
            logger.info(f"Starting batch processing from {batch_config.input_file}")
            results = await self._process_urls(
                processor=processor,
                batch_config=batch_config
            )
            
            # Export results
            result_files = self._export_results(
                results=results,
                output_dir=output_dir,
                batch_config=batch_config
            )
            
            # Generate and save summary
            summary = self._generate_summary(results, result_files)
            
            return summary
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            raise
    
    async def _process_urls(
        self,
        processor: BatchURLProcessor,
        batch_config: BatchProcessingConfig
    ) -> List[BatchProcessingResult]:
        """Process URLs from input file"""
        try:
            # Read URLs from file
            urls = list(processor.read_urls(batch_config.input_file))
            if not urls:
                raise ValueError(f"No valid URLs found in {batch_config.input_file}")
            
            logger.info(f"Found {len(urls)} URLs to process")
            
            # Create progress tracking
            progress_queue = asyncio.Queue()
            
            async def progress_callback(progress: float):
                await progress_queue.put(progress)
                
            # Process URLs with progress tracking
            processing_task = asyncio.create_task(
                processor.process_batch(
                    urls=urls,
                    progress_callback=progress_callback
                )
            )
            
            # Monitor progress
            while True:
                try:
                    progress = await asyncio.wait_for(
                        progress_queue.get(),
                        timeout=0.1
                    )
                    logger.info(f"Processing progress: {progress:.1%}")
                except asyncio.TimeoutError:
                    if processing_task.done():
                        break
            
            results = await processing_task
            return results
            
        except Exception as e:
            logger.error(f"Error processing URLs: {str(e)}")
            raise
            
    def _export_results(
        self,
        results: List[BatchProcessingResult],
        output_dir: Path,
        batch_config: BatchProcessingConfig
    ) -> Dict[str, str]:
        """Export processing results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        results_file = output_dir / f"batch_results_{timestamp}.json"
        detailed_results = [
            {
                **asdict(result),
                'batch_config': asdict(batch_config)
            }
            for result in results
        ]
        
        with open(results_file, 'w') as f:
            json.dump(detailed_results, f, indent=2)
            
        # Save CSV summary for easy viewing
        csv_file = output_dir / f"batch_summary_{timestamp}.csv"
        with open(csv_file, 'w') as f:
            f.write("URL,Status,Model Number,Files Downloaded,Error\n")
            for result in results:
                files_count = sum(len(files) for files in result.downloaded_files.values())
                f.write(f"{result.url},{result.status},{result.model_number},{files_count},{result.error or ''}\n")
                
        return {
            'detailed_results': str(results_file),
            'summary_csv': str(csv_file)
        }
        
    def _generate_summary(
        self,
        results: List[BatchProcessingResult],
        result_files: Dict[str, str]
    ) -> Dict[str, Any]:
        """Generate processing summary"""
        successful = [r for r in results if r.status == 'success']
        failed = [r for r in results if r.status == 'error']
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total_urls': len(results),
            'successful_urls': len(successful),
            'failed_urls': len(failed),
            'success_rate': len(successful) / len(results) if results else 0,
            'downloaded_files': {
                'total': sum(
                    sum(len(files) for files in r.downloaded_files.values())
                    for r in successful
                ),
                'by_type': {
                    file_type: sum(
                        len(r.downloaded_files.get(file_type, []))
                        for r in successful
                    )
                    for file_type in ['pdfs', 'images', 'documents']
                }
            },
            'result_files': result_files,
            'failed_urls_details': [
                {
                    'url': r.url,
                    'model_number': r.model_number,
                    'error': r.error
                }
                for r in failed
            ]
        }