# NBA India Website Scraping Guide

## 1. Introduction
The [National Biodiversity Authority (NBA) India website](https://www.nbaindia.nic.in/) is the official portal managed by the Government of India. The platform is built using **Drupal 10** as its Content Management System (CMS). The website relies heavily on server-rendered HTML rather than client-side API calls to display its public documentation, making it straightforward for standard HTML parsing.

## 2. Website's Usecase
The website acts as a centralized hub for:
- Implementing India's Biological Diversity Act (2002).
- Facilitating, regulating, and advising the government on conservation and sustainable use of biological resources.
- Handling Access and Benefit Sharing (ABS) applications.
- Disseminating public information, acts, rules, and notifications related to State Biodiversity Boards (SBBs) and Biodiversity Management Committees (BMCs).

## 3. What it has
The website hosts a wealth of publicly available resources, specifically formatted as downloadable PDF files:
- **Acts & Rules:** Detailed documents of the Biological Diversity Act, National Rules, and State Biodiversity Rules.
- **Notifications & Guidelines:** Documents on People's Biodiversity Register (PBR) formats, exemption of crops, guidelines for BMCs/BHSs, and collaborative research.
- **ABS Application Portal:** Redirects for the online ABS e-filing system (`https://absefiling.nbaindia.in/`).
- **Media & News:** Latest updates, circulars, press releases, and event photo galleries.

## 4. API Routings / Structured Retrievals for Scraping
Because the site uses Drupal and server-rendered HTML, there are no open JSON APIs for these document sections. Scraping requires HTTP GET requests followed by HTML parsing (e.g., using `BeautifulSoup` in Python or `Cheerio` in Node.js). 

Here are the key routing structures and CSS selectors to target:

### A. ABS Rules
- **URL Route:** `https://www.nbaindia.nic.in/acts-and-rules/rules`
- **Scraping Strategy:**
  - Send a GET request to the URL.
  - Find all `<a>` tags with the class `download-link` (or target `.pdf` extensions in `href`).
  - Example file paths: `/sites/default/files/2026-05/BD_Rules.pdf`
  - Ensure you prepend the base URL (`https://www.nbaindia.nic.in`) to the extracted `href`.

### B. Biological-Resource Regulations & Notifications
- **URL Route:** `https://www.nbaindia.nic.in/public-information/notification-guidelines`
- **Scraping Strategy:**
  - This page contains multiple tabular sections for different categories of notifications.
  - Target table cells: `<td class="views-field views-field-field-file-upload-1">`
  - Extract the `<a>` tag with class `download-link`.
  - Notable documents found here:
    - *Guidelines on ABS Regulations (GNABSREG_2025.pdf)*
    - *Guidelines for BMC.pdf*
    - *State-level PBR Monitoring Committee Notifications*

### C. Homepage Latest Circulars (Marquee/Ticker)
- **URL Route:** `https://www.nbaindia.nic.in/`
- **Scraping Strategy:**
  - Target the `<div class="marquee">` or `<ul class="arrow_list">`.
  - Look for `<a>` tags with class `doc-link` containing `.pdf` files.

## 5. Verified Testings
- **Access Method:** The pages are accessible via standard HTTP GET requests. No strict bot-protection (like Cloudflare Turnstile or CAPTCHAs) is present on the public informational pages.
- **Dynamic Content:** Document links are directly embedded in the HTML returned by the server. Tools like Playwright/Puppeteer are not strictly necessary unless navigating the external ABS e-filing portal.
- **Link Structure Verification:** Verified that the document `href` attributes are relative paths (e.g., `/sites/default/files/2026-07/GNABSREG_2025.pdf`). A scraper must construct the absolute URL.
- **File Types:** 100% of the verified regulatory documents are hosted as `.pdf` files.
