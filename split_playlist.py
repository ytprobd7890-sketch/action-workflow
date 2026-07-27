import os
import re
import requests

# ==============================================================================
# Boss Kobir - IPTV Playlist Category Splitter & Alphabetical Sorter
# ==============================================================================
# This Python script downloads your master M3U from Railway, parses every channel
# along with its associated #KODIPROP and #EXTVLCOPT DRM tags, groups them by 
# group-title (Category), sorts them alphabetically, and writes them into 
# separate, highly optimized M3U files in the "playlists/" directory.
# ==============================================================================

RAILWAY_PLAYLIST_URL = os.environ.get(
    "RAILWAY_PLAYLIST_URL", 
    "https://tatatv.kobir26.qzz.io/playlist.php?token=kobir26tata27"
)
OUTPUT_DIR = "playlists"

# Create playlists directory
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def sanitize_filename(name):
    """Sanitizes category names to be valid safe filenames."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name).strip('_')

def parse_and_split_m3u():
    print(f"[Splitter] Downloading master playlist from Railway: {RAILWAY_PLAYLIST_URL}")
    try:
        r = requests.get(RAILWAY_PLAYLIST_URL, timeout=30)
        if r.status_code != 200:
            print(f"[Error] Failed to download playlist. Status: {r.status_code}")
            return
        playlist_content = r.text
    except Exception as e:
        print(f"[Error] Failed to connect: {e}")
        return

    print("[Splitter] Parsing and sorting channels...")
    
    # We parse the file line-by-line while preserving associated preceding headers
    lines = playlist_content.split('\n')
    
    categories = {} # group_title -> [ { name, block_content } ]
    
    current_props = [] # Buffer for #KODIPROP or #EXTVLCOPT
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Capture adaptive DRM props preceding the channel
        if line.startswith("#KODIPROP") or line.startswith("#EXTVLCOPT"):
            current_props.append(line)
            continue
            
        # Parse EXTINF to extract group-title and tvg-name
        if line.startswith("#EXTINF"):
            extinf_line = line
            
            # Extract group-title using regex
            group_match = re.search(r'group-title="([^"]+)"', extinf_line)
            group_title = group_match.group(1).strip() if group_match else "General"
            
            # Extract channel display name
            name_parts = extinf_line.split(',')
            ch_name = name_parts[-1].strip() if len(name_parts) > 1 else "Unknown Channel"
            
            continue
            
        # If it's the stream URL, compile the channel block
        if line.startswith("http"):
            stream_url = line
            
            # Build the complete channel block preserving its headers
            block = []
            if current_props:
                block.extend(current_props)
            block.append(extinf_line)
            block.append(stream_url)
            block_str = "\n".join(block) + "\n"
            
            if group_title not in categories:
                categories[group_title] = []
                
            categories[group_title].append({
                'name': ch_name.lower(),
                'content': block_str
            })
            
            # Reset buffers for next channel
            current_props = []

    print(f"[Splitter] Successfully parsed {len(categories)} unique categories!")

    # Write each group to a separate M3U file, sorted alphabetically by name
    for group, channels in categories.items():
        # Sort channels alphabetically by name
        channels.sort(key=lambda x: x['name'])
        
        safe_name = sanitize_filename(group)
        output_file_path = os.path.join(OUTPUT_DIR, f"{safe_name}.m3u")
        
        print(f"  -> Writing sorted category file: {output_file_path} ({len(channels)} channels)")
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            # Header with standard EPG integrated
            f.write('#EXTM3U x-tvg-url="https://avkb.short.gy/epg.xml.gz" url-tvg="https://avkb.short.gy/epg.xml.gz"\n')
            f.write(f"# Category: {group}\n")
            f.write(f"# Total Channels: {len(channels)}\n")
            f.write("# Specially Sorted & Upgraded for Boss : Kobir\n\n")
            
            for ch in channels:
                f.write(ch['content'])

    print("\n🎉 SUCCESS! All playlists successfully split, sorted, and saved in the 'playlists/' directory!")

if __name__ == "__main__":
    parse_and_split_m3u()
