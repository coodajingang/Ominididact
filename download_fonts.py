import sys
import os
import re
import urllib.request

# Force standard streams to use UTF-8 to avoid ASCII encoding errors in minimal environments
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def download_fonts():
    # Establish local folders
    os.makedirs("static/fonts", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)

    # Google Fonts Outfit url requesting weights 300, 400, 500, 600, 700
    url = "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap"
    
    # Needs Chrome user-agent to get standard woff2 files
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    )

    print("Fetching Google Fonts CSS...")
    try:
        with urllib.request.urlopen(req) as response:
            css_content = response.read().decode("utf-8")
    except Exception as e:
        print(f"Error fetching CSS: {e}")
        return

    # Extract all .woff2 font file URLs
    urls = re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+)\)', css_content)
    
    local_css = css_content
    for i, font_url in enumerate(urls):
        filename = font_url.split("/")[-1]
        local_path = os.path.join("static", "fonts", filename)
        
        print(f"Downloading font chunk {i+1}/{len(urls)}: {filename}...")
        try:
            # Fetch raw font file
            urllib.request.urlretrieve(font_url, local_path)
            # Replace online URL references with local path
            local_css = local_css.replace(font_url, f"/static/fonts/{filename}")
        except Exception as e:
            print(f"Failed to download font {font_url}: {e}")

    # Save mapping stylesheet
    css_path = os.path.join("static", "css", "fonts.css")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(local_css)
        
    print(f"=== Successfully generated local fonts stylesheet at {css_path} ===")

if __name__ == "__main__":
    download_fonts()
