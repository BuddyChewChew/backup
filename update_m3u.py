import re
import requests
import os
import time

# --- Configuration ---
PLAYLIST_FILE = 'Backup.m3u'
SERVER_LIST_FILE = 'servers.txt'
TARGET_DOMAIN = 'moveonjoy.com'
# --- New Configuration: Maximum number of fully working servers to find before stopping ---
MAX_WORKING_SERVERS_TO_FIND = 10 

# --- Global state variables (Do not change these values directly) ---
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

def extract_channel_paths(playlist_filepath):
    """
    Reads the playlist to find the initial server base and extract all unique 
    channel paths for the TARGET_DOMAIN.
    Returns: (list of unique paths, initial server base URL)
    """
    global INITIAL_SERVER_BASE
    
    unique_paths = set()
    server_base = ''
    
    try:
        with open(playlist_filepath, 'r') as f:
            lines = f.readlines()
            
        # Regex to capture the base URL (Group 1) and the path (Group 2)
        regex_pattern = re.compile(rf'(https?://fl\d+\.{re.escape(TARGET_DOMAIN)})(/.+\.m3u8)')
        
        for line in lines:
            if re.search(TARGET_DOMAIN, line):
                match = regex_pattern.search(line)
                if match:
                    # Capture the initial server base only once
                    if not server_base:
                        server_base = match.group(1).rstrip('/')
                        INITIAL_SERVER_BASE = server_base
                    
                    # Capture the relative path
                    unique_paths.add(match.group(2))
        
        if not server_base:
            print(f"Error: Could not find any '{TARGET_DOMAIN}' links in the playlist.")
            return [], ''
            
        print(f"Found initial server base: {INITIAL_SERVER_BASE}")
        print(f"Identified {len(unique_paths)} unique channel paths to test.")
        return list(unique_paths), server_base
        
    except FileNotFoundError:
        print(f"Error: Playlist file '{playlist_filepath}' not found.")
        return [], ''

def check_server_health(server_list, test_paths):
    """
    Checks the health of the servers by attempting to load ALL unique M3U8 files 
    for each server. A server is only 'working' if all test paths return 200 OK.
    Returns a list of working base server URLs, up to MAX_WORKING_SERVERS_TO_FIND.
    """
    working_servers = []
    num_paths = len(test_paths)
    print(f"\nStarting exhaustive server health check: Testing {num_paths} channels per server.")
    
    # Iterate over all potential servers from servers.txt
    for server_url in server_list:
        is_server_working = True
        
        # Iterate over all unique channels we extracted
        for i, test_path in enumerate(test_paths):
            full_test_url = server_url + test_path
            
            try:
                # Send a GET request to ensure the M3U8 file itself is accessible
                # Using a 5-second timeout for this individual path check
                response = requests.get(full_test_url, timeout=5, allow_redirects=True) 
                
                # If status is not 200 (e.g., 404, 500, etc.), the server fails
                if response.status_code != 200:
                    print(f"  -> FAIL: Server {server_url} failed on path {i+1}/{num_paths} ({test_path}) with status {response.status_code}.")
                    is_server_working = False
                    break # Stop checking paths for this server and move to the next server
                
            except requests.exceptions.RequestException as e:
                # Connection error (timeout, DNS failure, etc.), the server fails
                print(f"  -> FAIL: Server {server_url} failed on path {i+1}/{num_paths} ({test_path}) due to connection error.")
                is_server_working = False
                break # Stop checking paths for this server and move to the next server
            
            # Small delay between checking individual channel paths on the same server
            time.sleep(0.1) 

        # Only add the server if ALL paths passed the check
        if is_server_working:
            print(f"SUCCESS: Server {server_url} is fully live (all {num_paths} channels OK).")
            working_servers.append(server_url)
            
            # Check if we have found enough servers to stop early
            if len(working_servers) >= MAX_WORKING_SERVERS_TO_FIND:
                print(f"Found {MAX_WORKING_SERVERS_TO_FIND} fully working servers. Stopping search.")
                break
        
        # Add a slightly longer delay between checking different servers
        time.sleep(0.5) 
        
    if not working_servers:
        print("No fully working servers found after checking the entire list.")
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
    # 1. Extract all unique channel paths and the initial server base
    all_paths, initial_server_base = extract_channel_paths(PLAYLIST_FILE)
    if not all_paths:
        return
        
    # 2. Load the list of potential servers
    all_servers = load_servers(SERVER_LIST_FILE)
    if not all_servers:
        print("Script aborted: No servers available.")
        return

    # 3. Check which servers are currently reachable using ALL channel paths
    working_servers = check_server_health(all_servers, all_paths)

    # 4. Update the playlist file with the first (and best) fully working server found
    if working_servers:
        new_server = working_servers[0]
        # Check if the new server is different from the one currently in the playlist
        if new_server == initial_server_base:
            print(f"\nServer is already using the best working base ({initial_server_base}). No update necessary.")
        else:
            update_playlist(PLAYLIST_FILE, new_server)
    else:
        print("\nPlaylist not updated as NO FULLY WORKING SERVERS were found in the list.")


if __name__ == "__main__":
    # Note: Requires the 'requests' library (pip install requests) to run successfully.
    main()
