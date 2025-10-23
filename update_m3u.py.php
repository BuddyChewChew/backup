import re
import requests
import os
import time

# --- Configuration ---
PLAYLIST_FILE = 'Backup.m3u'
SERVER_LIST_FILE = 'servers.txt'
TARGET_DOMAIN = 'moveonjoy.com'
TARGET_PREFIX = 'http://fl1.' # The base URL prefix to replace

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

def check_server_health(server_list):
    """
    Checks the health of the servers by attempting a simple HEAD request.
    Returns a list of working base server URLs.
    """
    working_servers = []
    print("Starting server health check...")
    
    # We only need the domain name, not the full path like http://flX.moveonjoy.com
    # We will use the prefix 'fl' to test reachability.
    
    # For this script, we assume the server list contains the base addresses (e.g., http://fl1.moveonjoy.com)
    # The actual M3U channels append a path (e.g., /ABC_EAST/index.m3u8).
    
    # A simple way to check is to try to connect to the base server path.
    # However, since we are only concerned with the domain part in the M3U8, 
    # and the user provides a list of *potential* servers, we will assume the 
    # first few that respond are good candidates.
    
    # A simple connection check is performed, though a true "working" check 
    # would involve a specific M3U8 file test, which is more complex and slow.
    
    for server_url in server_list:
        try:
            # Send a HEAD request for speed, with a short timeout
            response = requests.head(server_url, timeout=5, allow_redirects=True)
            # A 200 (OK) or 300-399 (redirect success) is often a sign of life
            if 200 <= response.status_code < 400:
                print(f"Server {server_url} is reachable (Status: {response.status_code}).")
                working_servers.append(server_url)
                # We often only need one or two working servers. Let's find a few
                if len(working_servers) >= 5: 
                    break # Stop after finding 5 good servers to save time
            else:
                print(f"Server {server_url} returned status code {response.status_code}.")
        except requests.exceptions.RequestException as e:
            print(f"Server {server_url} failed to connect: {e.__class__.__name__}")
        
        # Add a small delay to avoid hammering the servers
        time.sleep(0.5) 
        
    print(f"Found {len(working_servers)} working servers.")
    return working_servers

def update_playlist(playlist_filepath, working_servers):
    """
    Reads the M3U file, replaces the moveonjoy.com server with a working one,
    and writes the updated content back to the file.
    """
    if not working_servers:
        print("No working servers found. Playlist will not be updated.")
        return False

    # Use the first reliable server found for replacements
    # We need the base server URL to replace the flX part
    
    # Extract the base domain part of the working server (e.g., http://flN.moveonjoy.com)
    # The M3U lines start with http://fl1.moveonjoy.com/
    
    # The new base URL to use for replacements
    new_base_url = working_servers[0].rstrip('/') 
    
    # The pattern to find lines we need to change. 
    # It looks for http://fl[any digit].moveonjoy.com
    # We make the regex generic to catch all flX domains that might be in the playlist already.
    # We need to capture the path part so we can re-append it.
    
    # Regex to capture the full URL and separate the path
    # Example: http://fl1.moveonjoy.com/ABC_EAST/index.m3u8
    # Group 1: The full flX.moveonjoy.com part to be replaced
    # Group 2: The rest of the path (/ABC_EAST/index.m3u8)
    
    # NOTE: The provided sample playlist uses 'http://fl1.moveonjoy.com/...' 
    # We'll target the whole prefix to be safe, but use a more robust regex.
    
    # Regex targets: http(s)://fl[digits].moveonjoy.com
    # It will capture the path (e.g., /ABC_EAST/index.m3u8)
    
    # The core domain pattern: (https?://fl\d+\.moveonjoy\.com)
    regex_pattern = re.compile(rf'(https?://fl\d+\.{re.escape(TARGET_DOMAIN)})')
    
    replacement_made = False
    new_lines = []
    
    try:
        with open(playlist_filepath, 'r') as f:
            lines = f.readlines()
            
        print(f"Replacing links using new base server: {new_base_url}")
        
        for line in lines:
            if re.search(TARGET_DOMAIN, line):
                # This line contains a target link, attempt replacement
                match = regex_pattern.search(line)
                if match:
                    # The full path suffix remains the same
                    # line.replace(match.group(1), new_base_url) 
                    
                    # We want to perform the substitution on the whole line
                    # using the specific matched group (match.group(1) is the old server URL)
                    new_line = line.replace(match.group(1), new_base_url)
                    
                    if new_line != line:
                        print(f"  Updated link for: {line.split(',')[-1].strip()}")
                        replacement_made = True
                        new_lines.append(new_line)
                    else:
                         # This shouldn't happen if regex matches, but keep original if no change
                         new_lines.append(line)
                else:
                    # If it has the domain but doesn't match the specific flX pattern, keep original
                    new_lines.append(line)
            else:
                # Keep all non-target lines (EXTINF headers, non-moveonjoy links)
                new_lines.append(line)

        # Write the updated content back to the M3U file
        if replacement_made:
            with open(playlist_filepath, 'w') as f:
                f.writelines(new_lines)
            print(f"Successfully updated '{playlist_filepath}' with a working server.")
            return True
        else:
            print(f"No changes needed or no target links found in '{playlist_filepath}'.")
            return False

    except FileNotFoundError:
        print(f"Error: Playlist file '{playlist_filepath}' not found.")
        return False
    except Exception as e:
        print(f"An error occurred during playlist processing: {e}")
        return False


def main():
    # 1. Load the list of potential servers
    all_servers = load_servers(SERVER_LIST_FILE)
    if not all_servers:
        print("Script aborted: No servers available.")
        return

    # 2. Check which servers are currently reachable
    working_servers = check_server_health(all_servers)

    # 3. Update the playlist file with the best working server
    if working_servers:
        update_playlist(PLAYLIST_FILE, working_servers)
    else:
        print("Playlist not updated as no working servers were found.")


if __name__ == "__main__":
    # Ensure 'requests' library is installed and available in the GitHub Action environment
    main()
