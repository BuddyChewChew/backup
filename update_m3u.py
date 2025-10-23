import re
import requests
import os
import time

# --- Configuration ---
PLAYLIST_FILE = 'Backup.m3u'
SERVER_LIST_FILE = 'servers.txt'
TARGET_DOMAIN = 'moveonjoy.com'

# --- Global state variables (Do not change these values directly) ---
TEST_CHANNEL_PATH = ''
INITIAL_SERVER_BASE = ''

def load_servers(filepath):
    """Loads and cleans the list of potential working servers."""
    try:
        with open(filepath, 'r') as f:
            # Read, strip whitespace, and filter out empty lines
            servers = [line.strip().rstrip('/') for line in f if line.strip()]
        return servers
    except FileNotFoundError:
        print(f"Error: Server list file '{filepath}' not found.")
        return []

def get_test_channel_path(playlist_filepath):
    """
    Reads the playlist to determine the path of the first moveonjoy.com link.
    This path will be used to test the health of other servers.
    Example: Extracts '/ABC_EAST/index.m3u8' from 'http://fl1.moveonjoy.com/ABC_EAST/index.m3u8'
    """
    global TEST_CHANNEL_PATH, INITIAL_SERVER_BASE
    
    try:
        with open(playlist_filepath, 'r') as f:
            lines = f.readlines()
            
        # Regex to capture the base URL (Group 1) and the path (Group 2)
        regex_pattern = re.compile(rf'(https?://fl\d+\.{re.escape(TARGET_DOMAIN)})(/.+\.m3u8)')
        
        for line in lines:
            if re.search(TARGET_DOMAIN, line):
                match = regex_pattern.search(line)
                if match:
                    # Group 1 is the base server (e.g., http://fl1.moveonjoy.com)
                    INITIAL_SERVER_BASE = match.group(1).rstrip('/')
                    # Group 2 is the relative path (e.g., /ABC_EAST/index.m3u8)
                    TEST_CHANNEL_PATH = match.group(2)
                    print(f"Found initial server base: {INITIAL_SERVER_BASE}")
                    print(f"Identified test channel path: {TEST_CHANNEL_PATH}")
                    return True
        
        print(f"Error: Could not find a '{TARGET_DOMAIN}' link in the playlist to determine the test channel path.")
        return False
        
    except FileNotFoundError:
        print(f"Error: Playlist file '{playlist_filepath}' not found.")
        return False

def check_server_health(server_list, test_path):
    """
    Checks the health of the servers by attempting to load a specific channel's M3U8 file.
    Returns a list containing ONE working base server URL, or an empty list.
    We stop and return immediately upon finding the first 200 OK response.
    """
    working_servers = []
    print("\nStarting robust server health check (testing a specific channel)...")
    
    for server_url in server_list:
        # Construct the full URL to the M3U8 file
        full_test_url = server_url + test_path
        
        try:
            # Send a GET request to ensure the M3U8 file itself is accessible
            # Use a longer timeout (10 seconds) for this critical check
            response = requests.get(full_test_url, timeout=10, allow_redirects=True)
            
            # We are looking for an HTTP 200 OK status, confirming stream availability
            if response.status_code == 200:
                print(f"SUCCESS: Server {server_url} is live and the test channel is responding.")
                working_servers.append(server_url)
                # Return immediately to save time, as we only need one working server.
                return working_servers 
            else:
                print(f"FAILED: Server {server_url} returned status code {response.status_code} for {full_test_url}.")
        
        except requests.exceptions.RequestException as e:
            # Handle connection errors, DNS failure, timeouts, etc.
            print(f"FAILED: Server {server_url} failed to connect or time out: {e.__class__.__name__}")
        
        # Add a small delay to avoid hammering the servers
        time.sleep(0.5) 
        
    print("No working servers found after checking the entire list.")
    return working_servers

def update_playlist(playlist_filepath, new_base_url):
    """
    Reads the M3U file, replaces the old server base with the new working one,
    and writes the updated content back to the file.
    """
    global INITIAL_SERVER_BASE
    
    if not new_base_url or not INITIAL_SERVER_BASE:
        print("Update aborted: Missing new server URL or initial server base.")
        return False
        
    # The pattern targets the exact server base found in the M3U file.
    # We escape it for safe regex substitution.
    regex_pattern = re.compile(re.escape(INITIAL_SERVER_BASE), re.IGNORECASE)
    
    replacement_made = False
    new_lines = []
    
    try:
        with open(playlist_filepath, 'r') as f:
            lines = f.readlines()
            
        print(f"\nReplacing all instances of '{INITIAL_SERVER_BASE}' with '{new_base_url}'")
        
        for line in lines:
            # Check if the line contains the old base server URL
            if INITIAL_SERVER_BASE in line:
                # Perform the replacement using the new base URL
                new_line = regex_pattern.sub(new_base_url, line)
                
                if new_line != line:
                    channel_name = line.split(',')[-1].strip()
                    print(f"  Updated link for: {channel_name}")
                    replacement_made = True
                    new_lines.append(new_line)
                else:
                     new_lines.append(line)
            else:
                # Keep all non-target lines 
                new_lines.append(line)

        # Write the updated content back to the M3U file
        if replacement_made:
            with open(playlist_filepath, 'w') as f:
                f.writelines(new_lines)
            print(f"\nSuccessfully updated '{playlist_filepath}' to use {new_base_url}.")
            return True
        else:
            print(f"No changes needed or no target links found for replacement in '{playlist_filepath}'.")
            return False

    except FileNotFoundError:
        print(f"Error: Playlist file '{playlist_filepath}' not found.")
        return False
    except Exception as e:
        print(f"An error occurred during playlist processing: {e}")
        return False


def main():
    # 1. First, extract the channel path from the M3U file
    if not get_test_channel_path(PLAYLIST_FILE):
        return
        
    # 2. Load the list of potential servers (fl1.moveonjoy.com, fl2.moveonjoy.com, etc.)
    all_servers = load_servers(SERVER_LIST_FILE)
    if not all_servers:
        print("Script aborted: No servers available.")
        return

    # 3. Check which servers are currently reachable using the specific channel path
    # This will search the entire list until ONE working server is found.
    working_servers = check_server_health(all_servers, TEST_CHANNEL_PATH)

    # 4. Update the playlist file with the first (and best) working server found
    if working_servers:
        new_server = working_servers[0]
        # Check if the new server is different from the one currently in the playlist
        if new_server == INITIAL_SERVER_BASE:
            print(f"\nServer is already using the best working base ({INITIAL_SERVER_BASE}). No update necessary.")
        else:
            update_playlist(PLAYLIST_FILE, new_server)
    else:
        print("\nPlaylist not updated as NO WORKING SERVERS were found in the list.")


if __name__ == "__main__":
    # Note: Requires the 'requests' library (pip install requests) to run successfully.
    main()
