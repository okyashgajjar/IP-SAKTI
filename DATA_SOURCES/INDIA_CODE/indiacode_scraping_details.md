# India Code Web Scraping Details

## 1. Introduction
The India Code portal (https://indiacode.gov.in/) is the digital repository of all Central and State Acts, along with their subordinate legislations (Rules, Regulations, Notifications, Orders, Circulars, etc.). The website is built using **Angular** on the frontend and is powered by **DSpace 7/9 REST API** on the backend. This means the content is exposed via a well-structured, standardized open-source API framework, making it highly accessible for programmatic retrieval without the need for traditional HTML parsing (like BeautifulSoup).

## 2. Website's Usecase
The primary use case of India Code is to provide legal professionals, researchers, government entities, and the general public with an authentic, updated, and consolidated repository of Indian legislations. It aims to offer quick and easy access to both Central and State legislations, ensuring transparency and ease of legal reference. 

## 3. What it has
The repository follows a strict hierarchical classification modeled around the DSpace digital asset management system:
* **Communities:** Top-level categories representing regions, specifically `"CENTRAL"` for all central legislations, and state-wise communities like `"Maharashtra"`, `"Delhi"`, `"Andhra Pradesh"`, etc.
* **Collections:** The structural categories inside each community, mapping exactly to legal document types:
    * Acts
    * Rules
    * Regulations
    * Notifications
    * Ordinances
    * Orders, Circulars, etc.
* **Items:** The specific piece of legislation (e.g., *The National Bank for Financing Infrastructure and Development Act, 2021*). Each item holds comprehensive metadata including Ministry Name, Enactment Date, Act Number, Subject, etc.
* **Bitstreams (Files):** The actual PDF or text documents attached to the item.

## 4. API Routings/Structured Retrievals for Scraping Public Content
Since the application uses a pure REST API (DSpace backend), all content can be cleanly extracted via JSON responses without encountering UI anti-scraping measures. Here is the step-by-step API routing required to traverse and scrape the entire database.

### Step 1: Retrieve All Top-Level Communities (Statewise & Central)
**Endpoint:** `GET https://indiacode.gov.in/server/api/core/communities/search/top`
* **Purpose:** This returns a list of all states and the "CENTRAL" community along with their respective `uuid`s.
* **Extraction Target:** Extract the `uuid` and `name` of each community.

### Step 2: Retrieve Collections (Acts, Rules, Regulations, Notifications) per Community
**Endpoint:** `GET https://indiacode.gov.in/server/api/core/communities/{community_uuid}/collections`
* **Purpose:** This lists the document categories for a specific state or central government.
* **Extraction Target:** Extract the `uuid` and `name` of the collections. You will see collections like "Acts", "Rule", "Regulation", "Notification", etc.

### Step 3: Iterate and Retrieve Items (The Legislations) inside a Collection
**Endpoint:** `GET https://indiacode.gov.in/server/api/discover/search/objects?scope={collection_uuid}&size=100&page=0`
* **Purpose:** This retrieves a paginated list of all items (legislations) within the specified collection (e.g., all Acts under CENTRAL).
* **Extraction Target:** 
    * The item's `uuid` (located at `_embedded.searchResult._embedded.objects[]._embedded.indexableObject.uuid`).
    * Comprehensive metadata (title, dates, ministry, act number) under `_embedded.indexableObject.metadata`.
* **Pagination:** Use the `page` query parameter (0-indexed) or follow the `_links.next.href` provided in the response until completion.

### Step 4: Retrieve the Bundles for an Item
**Endpoint:** `GET https://indiacode.gov.in/server/api/core/items/{item_uuid}/bundles`
* **Purpose:** An item consists of different bundles (e.g., `ORIGINAL`, `TEXT`, `THUMBNAIL`). The `ORIGINAL` bundle contains the primary legal document files.
* **Extraction Target:** Find the bundle where `"name": "ORIGINAL"` and extract its `uuid`.

### Step 5: Retrieve the Bitstreams (PDF Files) from the Bundle
**Endpoint:** `GET https://indiacode.gov.in/server/api/core/bundles/{bundle_uuid}/bitstreams`
* **Purpose:** This fetches the list of actual files (bitstreams) attached to the document. 
* **Extraction Target:** The `uuid` of the bitstream or the download link directly.

### Step 6: Download the Document
**Endpoint:** `GET https://indiacode.gov.in/server/api/core/bitstreams/{bitstream_uuid}/content`
* **Purpose:** This binary endpoint triggers the direct download of the PDF/document file.

## 5. Verified Testings
To confirm the scraping methodology, the following live API calls were verified during testing:

1. **Top Communities Test:** 
   * `curl -s -L https://indiacode.gov.in/server/api/core/communities/search/top` successfully returned the `CENTRAL` community and all State/UT communities (e.g., `Andaman and Nicobar Islands`, `Andhra Pradesh`).
   * *Target UUID found for CENTRAL:* `f467b316-98f0-4c08-a722-a2627e45bc19`

2. **Collections Test (For CENTRAL):**
   * `curl -s -L https://indiacode.gov.in/server/api/core/communities/f467b316-98f0-4c08-a722-a2627e45bc19/collections` 
   * Output successfully showed "Acts", "Rule", "Regulation", "Notification", "Order", "Ordinance", etc.
   * *Target UUID found for Acts collection:* `69a0c1fb-7b22-4481-b16a-1dc59b5d02e6`

3. **Item Retrieval Test (Acts inside CENTRAL):**
   * `curl -s -L "https://indiacode.gov.in/server/api/discover/search/objects?scope=69a0c1fb-7b22-4481-b16a-1dc59b5d02e6&size=1"`
   * Successfully retrieved an Act: *The National Bank for Financing Infrastructure and Development Act, 2021*. All highly structured metadata (`dc.date.enact_date`, `dc.identifier.ministry_name`, `dc.description.abstract`) was fetched securely.
   * *Item UUID:* `040e5e03-bbf4-46d4-a75f-d032e28296d6`

4. **File Download Path Test:**
   * Getting Bundles: `curl -s -L https://indiacode.gov.in/server/api/core/items/040e5e03-bbf4-46d4-a75f-d032e28296d6/bundles` yielded the `ORIGINAL` bundle UUID.
   * Getting Bitstream Content Link: `curl -s -L https://indiacode.gov.in/server/api/core/bundles/{bundle_uuid}/bitstreams` provided the direct content link to download the PDF: `https://indiacode.gov.in/server/api/core/bitstreams/0d733c76-bb87-459a-b11b-d32056d1f7b9/content`

**Conclusion:** The India Code portal exposes a highly mature DSpace REST API allowing for fully programmatic, resilient, and structured scraping without requiring HTML parsing. You can systematically traverse from State/Central (Community) $\rightarrow$ Category (Collection) $\rightarrow$ Specific Legislation (Item) $\rightarrow$ PDF (Bitstream).
