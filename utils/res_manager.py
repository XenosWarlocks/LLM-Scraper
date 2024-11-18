from contextlib import contextmanager
import shutil
import os

class ResourceManager:
    @contextmanager
    def temporary_site_directory(self, url: str):
        site_dir = None
        try:
            site_dir = self.create_site_folder(url)
            yield site_dir
        finally:
            if site_dir and os.path.exists(site_dir):
                shutil.rmtree(site_dir, ignore_errors=True)