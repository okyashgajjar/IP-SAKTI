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
