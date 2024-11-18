import requests
from io import BytesIO
from PIL import Image
import numpy as np
from transformers import VisionEncoderDecoderModel, ViTFeatureExtractor, TrOCRProcessor

class ImageProcessing:
    def __init__(self):
        # Load the pre-trained vision-language model
        self.model = VisionEncoderDecoderModel.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.feature_extractor = ViTFeatureExtractor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.processor = TrOCRProcessor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")

    def process_image(self, image_url):
        # Fetch the image from the URL
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))

        # Preprocess the image for the model
        pixel_values = self.feature_extractor(images=image, return_tensors="pt").pixel_values

        # Generate caption and extract text
        output_ids = self.model.generate(pixel_values, max_length=50, num_beams=4, early_stopping=True)[0]
        caption = self.processor.decode(output_ids, skip_special_tokens=True)

        # Perform OCR on the image
        ocr_output = self.processor(images=image, return_tensors="pt").text

        return caption, ocr_output