# Retrieval Architecture: NBA (National Biodiversity Authority)

## 1. Overview & VegaVelocity Scale Principles
The NBA website is built on Drupal 10 and uses Server-Rendered HTML. Following VegaVelocity's principle **"Prefer simplicity until complexity is justified"**, we DO NOT need headless browsers (Playwright/Puppeteer) here. We can achieve massive scale using lightweight HTTP clients and standard HTML parsing.

**Bottleneck Analysis:**
*   **Likely Bottleneck (P0):** CPU overhead from parsing large HTML files across thousands of concurrent queries.
*   **Mitigation:** Use fast HTML parsers (e.g., `lxml` via BeautifulSoup) and cache the extracted document links.

## 2. SOLID Principles Application
*   **Single Responsibility Principle (SRP):** 
    *   `DrupalHtmlFetcher`: Handles HTTP GET requests.
    *   `NbaLinkExtractor`: Handles CSS Selection (e.g., `.download-link`).
*   **Open/Closed Principle (OCP):** Base HTML parser is closed for modification but open for extension to support new NBA URL routes (e.g., new ABS e-filing routes).
*   **Liskov Substitution Principle (LSP):** Implements the LangGraph `BaseTool` interface seamlessly.
*   **Interface Segregation Principle (ISP):** Client only implements `IHtmlParser`, ignoring browser automation interfaces.
*   **Dependency Inversion Principle (DIP):** The orchestrator depends on `INbaRegulatoryData`, not `BeautifulSoup` specifics.

## 3. LangGraph Multi-Agent Integration (Adapter Pattern)
To prevent LLM hallucination and ensure decoupling, LangGraph must **never** know about Drupal 10 or BeautifulSoup parsing logic. It interacts purely through a unified `Retrieval Adapter` interface.

*   **Node:** `Research Planner Agent`
*   **Adapter Interface:** `NbaRetrievalAdapter` implements `retrieve(source="NBA", query, jurisdiction="IN")`
*   **State Interaction:** 
    1.  LangGraph fires the abstract `retrieve(...)` command.
    2.  The `NbaRetrievalAdapter` catches it, translating the semantic query into standard HTTP requests and executing the LXML parser.
    3.  The Adapter formats the output and returns strictly structured `Normalized Evidence` back to the orchestrator.

## 4. Workload & Data Flow Model
```text
LangGraph (Research Planner)
       ↓
retrieve(source="NBA", query="ABS rules", jurisdiction="IN")
       ↓
[ NBA Retrieval Adapter ]  <-- (Abstractions Boundary)
       ↓
Async HTTP Pool (aiohttp/httpx)
       ↓
NBA Drupal Server (Standard GET)
       ↓
BeautifulSoup (lxml parser) 
       ↓
Relative to Absolute URL Construction
       ↓
PDF Downloader
       ↓
Normalized Evidence (Returned to LangGraph)
```

## 5. Production Readiness & Failure Engineering
*   **URL Resolution Security:** The guide notes relative paths (`/sites/default/files/...`). The pipeline must safely construct absolute URLs (`https://www.nbaindia.nic.in/...`) and validate them to prevent Server-Side Request Forgery (SSRF) or malformed URL crashes.
*   **Performance:** Since this is standard HTTP, it scales incredibly well. A pool of 50 async workers can parse the entire site in seconds. 
*   **Cache Strategy:** Cache the HTML DOM for 24 hours. The ABS rules do not change by the minute. This completely removes the NBA server as a bottleneck during peak 20k user load.
