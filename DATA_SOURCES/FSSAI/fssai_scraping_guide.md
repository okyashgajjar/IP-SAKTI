# Comprehensive Scraping Guide: FSSAI Website

## 1. Introduction
The **Food Safety and Standards Authority of India (FSSAI)** is the apex food regulatory body in India. Its official website ([https://fssai.gov.in/](https://fssai.gov.in/)) serves as the primary portal for food business operators (FBOs), consumers, testing laboratories, and government authorities to access critical food safety information, guidelines, and compliance requirements.

## 2. Website's Usecase
The FSSAI website is a central hub for food regulation and compliance in India. Its primary use cases include:
*   **Regulatory Compliance:** Providing FBOs with access to food safety laws, regulations, and gazette notifications.
*   **Licensing & Registration:** Acting as a gateway to the Food Safety Compliance System (FoSCoS) for acquiring and renewing food business licenses.
*   **Standards & Testing:** Hosting manuals, testing methodologies, and lists of approved food testing laboratories.
*   **Consumer Awareness:** Offering platforms for consumer grievances, safety tips (e.g., Check Adulteration), and health initiatives (e.g., Eat Right India).

## 3. What it Has
The website hosts a vast repository of public data, primarily categorized into structured HTML pages and downloadable PDFs. Key content includes:
*   **Food Regulations & Laws:** The Food Safety and Standards Act (2006), Rules (2011), and comprehensive Regulations.
*   **Ayurveda Aahara:** Specific regulations and approved recipes under the *Food Safety and Standards (Ayurveda Aahara) Regulations, 2022*. This includes guidelines, approved product categories (Category A), and labeling norms for Ayurveda Aahara.
*   **Licensing & Compliance:** Hygiene rating guidelines, inspection matrices, conditions of license, and third-party audit details.
*   **Labeling \u0026 Display:** Guidelines on packaging, nutritional labeling, advertising claims, and specific rules for vegan and organic foods.
*   **Amendments & Notifications:** A chronological archive of gazette notifications, draft regulations, and advisories for various food categories.

## 4. API Routings and Structured Retrievals
The newly revamped FSSAI website operates as a **React Single Page Application (SPA)** using Vite. Unlike traditional websites where each page load fetches new HTML, this SPA loads a bundled JavaScript file that handles internal routing and dynamically fetches data. 

### Frontend Routing Structure
The website's content is organized into logical frontend routes. To scrape specific sections, you must target these paths:
*   **Food Laws & Notifications:**
    *   `/food-law/act-2006` (The main Act)
    *   `/food-law/rules-2011` (FSS Rules)
    *   `/food-law/regulations` (FSS Regulations)
    *   `/food-law/notifications` (Gazette Notifications)
    *   `/food-law/advisories` (Advisories and Orders)
*   **Business & Licensing:**
    *   `/business/licensing` (Licensing Details)
    *   `/business/registration` (Registration Details)
    *   `/business/hygiene-rating` (Hygiene Rating)
*   **Standards \u0026 Ayurveda Aahara:**
    *   `/standards/product-standards`
    *   *(Note: Ayurveda Aahara updates are typically nested within `/food-law/regulations` and `/food-law/notifications` as PDFs).*
*   **Media \u0026 Press:**
    *   `/press-release`
    *   `/in-the-news`

### Data Retrieval & PDFs
While the frontend uses clean URL paths, the underlying document data (PDFs for amendments, labeling rules, Ayurveda Aahara) is often hosted on legacy backend servers or specific API endpoints, such as:
*   `https://www.fssai.gov.in/view-gazette.php`
*   `https://stg-old.fssai.gov.in/`

**Scraping Strategy:**
1.  **For HTML Content:** Since the site relies heavily on client-side rendering (React), standard HTTP request libraries (like `requests` in Python) will only return the bare DOM `<div id="root"></div>`. You **must** use a headless browser (like Playwright, Puppeteer, or Selenium) to execute the JavaScript and render the DOM before extracting data.
2.  **For PDFs \u0026 Legacy APIs:** Once the page is rendered, you can extract the `href` attributes pointing to `.pdf` files. These files can then be downloaded directly using standard HTTP GET requests.

## 5. Verified Testings

Below are tested Python code snippets demonstrating how to effectively scrape the FSSAI website.

### Example 1: Scraping Rendered HTML with Playwright
Because FSSAI is a React app, we use Playwright to wait for the network to idle and the content to render before scraping.

```python
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def scrape_fssai_regulations():
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Navigate to the Regulations page
        target_url = "https://fssai.gov.in/food-law/regulations"
        print(f"Navigating to {target_url}...")
        
        # Wait until there are no more than 0 network connections for at least 500 ms
        await page.goto(target_url, wait_until="networkidle")
        
        # Extract the fully rendered HTML
        html_content = await page.content()
        await browser.close()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Example: Find all links that might point to PDFs (Regulations)
        links = soup.find_all('a', href=True)
        pdf_links = [link['href'] for link in links if '.pdf' in link['href'].lower()]
        
        print(f"Found {len(pdf_links)} PDF documents on the page.")
        for pdf in pdf_links[:5]:
            print(f"- {pdf}")

if __name__ == "__main__":
    asyncio.run(scrape_fssai_regulations())
```

### Example 2: Intercepting API / Network Calls
To find exactly where the React app fetches its data from, you can intercept the network requests. This is highly effective for discovering hidden APIs or structured JSON data.

```python
import asyncio
from playwright.async_api import async_playwright

async def intercept_apis():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        api_calls = []
        
        # Event listener for network requests
        page.on("request", lambda request: api_calls.append({
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type
        }) if request.resource_type in ["fetch", "xhr"] else None)

        # Go to the home page or a specific section
        await page.goto("https://fssai.gov.in/", wait_until="networkidle")
        
        print("API/Data calls made by the React application:")
        for call in api_calls:
            print(f"[{call['method']}] {call['url']}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(intercept_apis())
```

### Example 3: Downloading a Legacy PDF securely
When you extract a link pointing to a legacy server (e.g., `stg-old.fssai.gov.in`), use standard requests to download it.

```python
import requests

def download_fssai_pdf(pdf_url, save_path):
    # FSSAI might block requests without a proper User-Agent
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(pdf_url, headers=headers, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded to {save_path}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download PDF: {e}")

# Example Usage
# download_fssai_pdf("https://stg-old.fssai.gov.in/upload/uploadfiles/files/Regulation_Labeling.pdf", "Labeling_Rules.pdf")
```
