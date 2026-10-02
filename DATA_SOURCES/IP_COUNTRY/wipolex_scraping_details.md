# WIPO Lex Scraping Guide

## 1. Introduction
WIPO Lex is a global database that provides free of charge access to legal information on intellectual property (IP) from around the world. As it is an essential public resource hosted by the World Intellectual Property Organization (WIPO), developers and researchers often need to scrape its data for analysis, legal tech products, or academic research. 

This guide outlines the technical structure of the website and the necessary approaches to scrape its publicly available content.

## 2. Website's Usecase
The primary use case for WIPO Lex is to serve as a comprehensive, centralized repository for global intellectual property laws, regulations, and treaties. It allows users (lawyers, researchers, policymakers, and the general public) to:
- Find national and regional IP laws for almost every country in the world.
- Access WIPO-administered treaties and other IP-related treaties.
- Track versions, amendments, and historical changes to IP legislation.
- Search documents by specific topics like Patents, Trademarks, Copyrights, Industrial Designs, etc.

## 3. What it has
The database is structured into three main collections:
1. **National IP Laws (Country-wise)**: Laws, regulations, and administrative texts related to intellectual property for individual countries (e.g., The Patents Act of India, The Lanham Act of the US).
2. **Treaty Information**: Multilateral, bilateral, and regional treaties concerning IP, including their current status, contracting parties, and text versions.
3. **Judgments**: Significant IP judgments from various jurisdictions (though this is a separate sub-collection).
4. **Version Information**: Access to the historical evolution of laws, including repealed versions and subsequent amendments.

## 4. API Routings & Structured Retrievals
Through verified testing and network analysis, it has been determined that **WIPO Lex does not expose a public, documented REST API for its database**. Furthermore, the website is built as a modern Single Page Application (SPA) using custom WIPO Web Components (e.g., `<wu-multi-search>`, `<wu-datepicker>`). 

Because data is not easily retrieved via simple `GET`/`POST` requests to a JSON endpoint, scraping requires **browser automation** tools like **Playwright**, **Selenium**, or **Puppeteer**.

### A. Routing Structure (Client-Side)
Although it relies on an internal, undocumented backend, the client-side routing follows a predictable pattern which you can use to automate your browser:

- **Legislation Search Page**: `https://wipolex.wipo.int/en/main/legislation`
- **Treaties Search Page**: `https://wipolex.wipo.int/en/main/treaties`
- **Results View Route**: `/wipolex/en/legislation/results` (Rendered via JS; navigating here directly without a proper session or via basic `curl` returns a 404).

### B. Form Payload Structure
When automating the search page, you must interact with the shadow DOM elements. The search form accepts the following key parameters:
- `searchType`: (Hidden input) e.g., `laws`
- `countriesOrgs`: 2-letter ISO Country Code (e.g., `IN` for India, `US` for USA).
- `subjects`: Numeric topic codes. Example: `1` = Patents, `4` = Trademarks, `11` = Copyright.
- `typeOfTexts`: Numeric type codes. Example: `205` = Main IP Laws, `207` = Implementing Rules.
- `keywords`: Text search input.
- `dateTextFrom` / `dateTextTo`: Date range for text.
- `pubDateFrom` / `pubDateTo`: Date range for publication.

### C. Recommended Scraping Approach
Since raw `requests` or `curl` will fail to render the search results (returning a CloudFront 404 page), you must use a headless browser.

**Workflow for National IP Laws & Versions:**
1. Launch Headless Browser (e.g., Playwright).
2. Navigate to `https://wipolex.wipo.int/en/main/legislation`.
3. Wait for network idle and custom web components (`wu-button`, `wu-input-text`) to load.
4. Inject JavaScript to populate the fields and dispatch events, as Shadow DOM encapsulation prevents standard CSS selectors from interacting with the inputs easily:
   ```javascript
   // Example Playwright JS execution to trigger search
   document.querySelector('wu-input-text#keywords').value = 'patent';
   document.querySelector('wu-input-text#keywords').dispatchEvent(new Event('input', {bubbles: true}));
   document.querySelector('wu-button#searchBtn').removeAttribute('disabled');
   document.querySelector('wu-button#searchBtn').click();
   ```
5. Wait for the results table to render in the DOM, then parse the resulting HTML table using BeautifulSoup or Playwright's locators to extract the Document Title, Date, Subject, and PDF/HTML URLs.

**Workflow for Treaty Information:**
1. Navigate to `https://wipolex.wipo.int/en/main/treaties`.
2. Follow the same component interaction pattern to select the Treaty type or specific keywords.
3. Scrape the rendered results for contracting parties and PDF links.

## 5. Verified Testings
During testing of the WIPO Lex infrastructure, the following behaviors were verified:
1. **Direct HTTP Requests Fail**: Attempting to query `https://wipolex.wipo.int/en/legislation/results?countriesOrgs=IN` directly via `curl` or Python `requests` results in an Amazon CloudFront 404 Error page. The server relies entirely on the client-side JavaScript bundle to route and render results.
2. **Component Architecture**: The site utilizes custom elements like `<wipo-navbar>` and `<wu-multi-search>`. These elements utilize Shadow DOM, meaning standard Selenium `find_element_by_id` will fail unless you explicitly pierce the shadow root or execute JavaScript directly on the page.
3. **No Hidden XHR Data Endpoints Exposed**: Monitoring network traffic (`fetch`/`xhr`) during search execution reveals that WIPO Lex obscures its data retrieval mechanism (likely through complex state management or GraphQL endpoints not easily replicable via curl). 
4. **Rate Limiting & Protection**: The WIPO servers use AWS CloudFront and have standard protections. High-speed scraping without delays will result in IP blocks. It is strictly required to implement `time.sleep()` and concurrency limits when writing your scraper.
