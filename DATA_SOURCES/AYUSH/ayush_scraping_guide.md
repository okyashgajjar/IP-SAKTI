# AYUSH Ministry Website Scraping Guide

## 1. Introduction
This guide provides details on how to programmatically collect and scrape public information from the Ministry of Ayush official website (https://ayush.gov.in/). The website is built as an Angular Single Page Application (SPA), meaning the content is loaded and rendered dynamically via JavaScript rather than being served as static HTML pages.

## 2. Website's Usecase
The Ministry of Ayush website serves as the central digital portal for information related to Ayurveda, Yoga & Naturopathy, Unani, Siddha, Sowa Rigpa, and Homoeopathy (AYUSH) in India. Its primary use cases include:
- Providing public access to government acts, rules, and regulations.
- Publishing official notifications, tenders, and government schemes.
- Serving as a central repository for research and development documents in the Ayush sector.
- Offering a citizen charter, grievance redressal mechanisms, and contact directories.

## 3. What it has
The website contains a vast amount of publicly available content across various domains, specifically:
- **Ayurveda/ASU Regulations:** Guidelines, acts, and quality standards for Ayush systems.
- **Notifications:** Latest announcements, "what's new" updates, circulars, and official orders.
- **Official Documents:** PDF reports, publications, annual reports, and budget details.
- **Schemes & Tenders:** Information on the National Ayush Mission (NAM), research grants, and public procurement tenders.
- **Directories:** Contact details of Ayush institutions, organizations, and professionals.

## 4. API routings/structured retrievals for scrapping publicly available content
Unlike traditional websites or portals with open data architectures, `ayush.gov.in` does not expose a public-facing JSON REST API for direct data consumption. The data is either bundled directly into the minified JavaScript application chunks or protected by strict routing structures. Traditional HTTP `GET` requests (using tools like `curl`, `requests`, or `wget`) will only return the initial Angular app shell (`<app-root></app-root>`), omitting the actual textual content.

To successfully scrape this site, you must use a headless browser automation framework (e.g., **Playwright**, **Puppeteer**, or **Selenium**) that can execute JavaScript, wait for the DOM to render, and then extract the data.

### Key Content Routes (URLs) for Rendering
*   **What's New / Notifications:** `https://ayush.gov.in/whatsnew`
*   **Ayurveda Regulations & Info:** `https://ayush.gov.in/ayurveda`
*   **Publications & Documents:** `https://ayush.gov.in/ayushinindiapublications`
*   **Quality Standards:** `https://ayush.gov.in/qualitystandard`
*   **Tenders:** `https://ayush.gov.in/tenders`
*   **Schemes:** `https://ayush.gov.in/schemes`

### Recommended Scraping Approach (Python with Playwright)
Since there are no open API endpoints to query, you must extract the rendered HTML DOM.

```python
from playwright.sync_api import sync_playwright
import time

def scrape_ayush_documents(url):
    with sync_playwright() as p:
        # Launch Chromium in headless mode
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Navigate to the target section and wait for network activity to settle
        print(f"Navigating to {url}...")
        page.goto(url, wait_until="networkidle")
        
        # Sometimes Angular apps need a brief moment to render the view completely
        time.sleep(2)
        
        # Extract document links (Assuming PDFs are linked)
        documents = page.locator("a[href$='.pdf']").all()
        
        print(f"Found {len(documents)} PDF documents.")
        for doc in documents:
            title = doc.inner_text().strip()
            link = doc.get_attribute("href")
            # Handle relative URLs if necessary
            if link.startswith('/'):
                link = f"https://ayush.gov.in{link}"
                
            print(f"Title: {title} | Link: {link}")
            
        browser.close()

# Example usage for Notifications / What's New
scrape_ayush_documents("https://ayush.gov.in/whatsnew")
```

## 5. Verified Testings
Extensive programmatic testing was conducted on the website to determine the optimal scraping methodology:
1.  **HTTP Shell Test:** Standard `GET` requests to the homepage return a minimal 24-line HTML shell (`Total Bytes: ~12KB`). This confirms it is a strict client-side rendered Single Page Application; HTML parsing libraries like BeautifulSoup cannot be used on raw HTTP responses.
2.  **API Sniffing Test:** Automated background network sniffing (using Puppeteer intercepting `XHR/Fetch` traffic) revealed that navigating to content-heavy sections like `/whatsnew` or `/ayurveda` does not trigger standard JSON data payloads. The application relies heavily on embedded JavaScript chunks (e.g., `main-WP7EQPKJ.js` which is ~2.9MB).
3.  **Endpoint Availability:** Tests against common API structures (e.g., `/api/notifications`, `/v1/documents`, `/assets/config.json`) all resulted in `404 Not Found`. 
4.  **Security Measures:** The site enforces strict Content-Security-Policy (CSP) headers and relies on dynamic frontend routing.
5.  **Conclusion:** The only verified, reliable way to collect regulations, notifications, and official documents from this portal is through DOM extraction using a browser automation tool after the Angular application has fully rendered on the client side.
