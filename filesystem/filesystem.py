import os
import stat
import errno
import fuse
import sys
import requests
import tempfile
import grp
import pwd
from fuse import Fuse

# Declare FUSE API compliance version
fuse.fuse_python_api = (0, 2)

# API Base URL (Adjust this to match the actual API location)
API_BASE_URL = "http://127.0.0.1:8080"  # Assuming FastAPI is running locally
CACHE_DIR = tempfile.gettempdir()  # Use system temp directory for caching
TARGET_GROUP = "test_temp"  # Group required for accessing specific files

class APIFilesystem(Fuse):
    """A read-only FUSE filesystem that fetches files dynamically from an API and caches them locally."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_sizes = {}  # To cache file sizes after fetching
        self.refresh_file_list()

    def refresh_file_list(self):
        """Fetch the list of available files from the API."""
        try:
            response = requests.get(f"{API_BASE_URL}/list")
            response.raise_for_status()
            self.files = response.json().get("files", [])
        except requests.RequestException as e:
            print(f"Error fetching file list: {e}")
            self.files = []

    def readdir(self, path: str, offset: int):
        """Iterate over the contents of the root directory."""
        for entry in ['.', '..'] + self.files:
            yield fuse.Direntry(entry)

    def getattr(self, path: str) -> fuse.Stat:
        """Get file attributes for a given path."""
        st = fuse.Stat()

        if path == '/':  # Root directory
            st.st_mode = stat.S_IFDIR | 0o555
            st.st_nlink = 2
            return st

        filename = path[1:]  # Remove the leading '/'
        if filename in self.files:
            # Enforce group check for specific file
            if filename == "test1.txt" and not self.user_in_group():
                return -errno.EACCES

            # Fetch and cache file size if not already cached
            if filename not in self.file_sizes:
                self.fetch_file_size(filename)

            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = self.file_sizes.get(filename, 0)
            return st

        return -errno.ENOENT

    def user_in_group(self):
        """Check if the current user belongs to the target group."""
        try:
            user_groups = [g.gr_name for g in grp.getgrall() if pwd.getpwuid(os.getuid()).pw_name in g.gr_mem]
            user_groups.append(grp.getgrgid(os.getgid()).gr_name)  # Include primary group
            return TARGET_GROUP in user_groups
        except KeyError:
            return False

    def fetch_file_size(self, filename: str):
        """Fetch the size of the file by downloading its content."""
        cache_path = os.path.join(CACHE_DIR, filename)
        if os.path.exists(cache_path):
            self.file_sizes[filename] = os.path.getsize(cache_path)
            return
        
        try:
            response = requests.get(f"{API_BASE_URL}/download/{filename}", stream=True)
            response.raise_for_status()
            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.file_sizes[filename] = os.path.getsize(cache_path)
        except requests.RequestException as e:
            print(f"Error fetching file size for {filename}: {e}")
            self.file_sizes[filename] = 0

    def read(self, path: str, size: int, offset: int) -> bytes:
        """Read a portion of the file content."""
        filename = path[1:]  # Remove the leading '/'
        if filename not in self.files:
            return -errno.ENOENT

        cache_path = os.path.join(CACHE_DIR, filename)
        if not os.path.exists(cache_path):
            try:
                # Download and cache the file if it does not exist
                response = requests.get(f"{API_BASE_URL}/download/{filename}", stream=True)
                response.raise_for_status()
                with open(cache_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            except requests.RequestException as e:
                print(f"Error downloading file {filename}: {e}")
                return b''

        try:
            # Read the requested portion from the cached file
            with open(cache_path, 'rb') as f:
                f.seek(offset)
                buf = f.read(size)
            return buf
        except OSError as e:
            print(f"Error reading file {filename} from cache: {e}")
            return b''

def main():
    if len(sys.argv) == 1:
        sys.argv.append('--help')

    title = 'Example: API-backed filesystem'
    descr = "Presents a dynamic filesystem with files fetched from an API and cached locally."
    usage = ("\n\n%s\n%s\n%s" % (sys.argv[0], title, descr))

    server = APIFilesystem(version="%prog " + fuse.__version__,
                           usage=usage,
                           dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
