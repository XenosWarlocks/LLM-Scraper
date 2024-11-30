import json
from typing import Union, Dict, List


def get_temperature(task_type: str, creativity_level: float) -> float:
    """Dynamically determine temperature based on task and creativity"""
    task_temperature_map = {
        'content_analysis': 0.2,
        'song_generation': 1.8,
        'poem_generation': 2,
        'story_generation': 2,
        'product_info': 1
    }

    base_temp = task_temperature_map.get(task_type, 1)

    # Adjust temperature with creativity level
    adjusted_temp = base_temp * creativity_level

    return min(max(adjusted_temp, 0), 2) # Clamp between 0 and 2

def get_output_expectations(task_type: str) -> str:
    """Generate dynamic output expectations based on task type"""
    output_expectations_map = {
        'content_analysis': (
            "Provide a concise summary of the website content. "
            "Highlight key themes, insights, and main topics. "
            "Capture the overall tone and intent of the text."
        ),
        'song_generation': (
            "Generate original song lyrics inspired by the website content. "
            "Reflect the themes and emotional tone detected in the text. "
            "Create a structured song with potential verse and chorus elements."
        ),
        'poem_generation': (
            "Create an evocative poem drawing inspiration from the website content. "
            "Use metaphors and imagery derived from the text. "
            "Reflect the emotional and thematic undertones of the source material."
        ),
        'product_info': (
            "Extract precise, structured product information. "
            "Include details such as product name, model number, serial number, "
            "warranty information, and links to relevant documents. "
            "Ensure accuracy and comprehensiveness."
        )
    }

    return output_expectations_map.get(
        task_type,
        "Provide a detailed and accurate response matching the user's request."
    )

def enhance_parse_description(original_description: str, task_type: str) -> str:
    """Enhance the parse description with additional context"""
    task_prefixes = {
        'content_analysis': "Analyze and summarize the content, focusing on: ",
        'song_generation': "Extract themes and inspiration for a song about: ",
        'poem_generation': "Find poetic inspiration in the context of: ",
        'product_info': "Extract detailed product information related to: "
    }
    
    prefix = task_prefixes.get(task_type, "Examine the content with respect to: ")
    return f"{prefix} {original_description}"