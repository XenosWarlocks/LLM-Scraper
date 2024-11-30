import os

# Path to the main data directory
data_directory = 'data'

# List of file extensions to delete
extensions_to_delete = {".svg", ".gif", ".txt"}

def delete_files_in_directory(directory):
    """Delete specified file types in a given directory."""
    for root, _, files in os.walk(directory):
        for file_name in files:
            # Check file extension and delete if it matches
            if any(file_name.endswith(ext) for ext in extensions_to_delete):
                file_path = os.path.join(root, file_name)
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

# Iterate through each subfolder in the data directory
if os.path.exists(data_directory):
    for folder_name in os.listdir(data_directory):
        folder_path = os.path.join(data_directory, folder_name)
        if os.path.isdir(folder_path):
            delete_files_in_directory(folder_path)
else:
    print(f"The directory '{data_directory}' does not exist.")