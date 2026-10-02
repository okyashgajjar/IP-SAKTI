# Retrieval Architecture: FSSAI (Food Safety and Standards Authority)

## 1. Overview & VegaVelocity Scale Principles
The FSSAI platform is a modern React SPA paired with legacy backend PDF servers (`stg-old.fssai.gov.in`). Following VegaVelocity's principle **"Keep the request path short"**, we split the pipeline: Playwright for frontend routing, standard HTTP for legacy PDFs.

**Bottleneck Analysis:**
*   **Likely Bottleneck (P0):** Legacy PDF server rate-limiting or connection exhaustion.
*   **Mitigation:** Bounded connection pool specifically tailored to the legacy server's capacity (e.g., max 10 concurrent HTTP connections). Never flood the government legacy server.

## 2. SOLID Principles Application
*   **Single Responsibility Principle (SRP):** 
    *   `SpaRenderer`: Handles React DOM extraction via Playwright.
    *   `LegacyFileFetcher`: Handles HTTP GET for legacy PDFs with custom User-Agents.
*   **Open/Closed Principle (OCP):** Easily extendable to intercept new XHR/fetch APIs if FSSAI transitions fully to an open API model.
*   **Liskov Substitution Principle (LSP):** `FssaiRetrievalAdapter` fits seamlessly into the standard LangGraph tool interface.
*   **Interface Segregation Principle (ISP):** Splitting `IDomScraper` from `INetworkInterceptor`.
*   **Dependency Inversion Principle (DIP):** LangGraph interacts with `IFssaiService`, decoupled from Playwright/Requests.

## 3. LangGraph Multi-Agent Integration (Adapter Pattern)
To prevent LLM hallucination and ensure decoupling, LangGraph must **never** know about React routing or legacy FSSAI endpoints. It interacts purely through a unified `Retrieval Adapter` interface.

*   **Node:** `Research Planner Agent`
*   **Adapter Interface:** `FssaiRetrievalAdapter` implements `retrieve(source="FSSAI", query, jurisdiction="IN")`
*   **State Interaction:** 
    1.  LangGraph fires the abstract `retrieve(...)` command.
    2.  The `FssaiRetrievalAdapter` catches it, translating the semantic query into specific Playwright navigation and HTTP requests.
    3.  The Adapter formats the output and returns strictly structured `Normalized Evidence` back to the orchestrator.

## 4. Workload & Data Flow Model
```text
LangGraph (Research Planner)
       ↓
retrieve(source="FSSAI", query="Ashwagandha beverage", jurisdiction="IN")
       ↓
[ FSSAI Retrieval Adapter ]  <-- (Abstractions Boundary)
       ↓
[ Cache Layer ] (TTL 24h for regulations)
       ↓ (Cache Miss)
Playwright Instance (Render React)
       ↓
Extract legacy PDF URLs
       ↓
Legacy Server Queue (Bounded HTTP Pool)
       ↓
PDF OCR / Text Extraction
       ↓
Normalized Evidence (Returned to LangGraph)
```

## 5. Production Readiness & Failure Engineering
*   **Network Interception:** Instead of just scraping DOM, use Playwright's `page.on("request")` to sniff XHR calls for hidden APIs.
*   **Backpressure:** Implement backpressure on the LegacyFileFetcher to prevent overwhelming FSSAI servers (which could result in an IP ban).
*   **Alerting:** Alert if legacy URL formats change or if 403 Forbidden is received (User-Agent block).
