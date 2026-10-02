# Retrieval Architecture: AYUSH (Ministry of Ayush)

## 1. Overview & VegaVelocity Scale Principles
The AYUSH website is an Angular Single Page Application (SPA). Based on the VegaVelocity principle of **"Measure before optimizing"** and **"Protect shared resources"**, we must account for the high memory and CPU footprint of headless browsers. 

**Bottleneck Analysis:**
*   **Likely Bottleneck (P0):** RAM/CPU exhaustion from too many concurrent Playwright chromium instances.
*   **Mitigation:** Implement a bounded Headless Browser Pool (e.g., max 5 concurrent instances) and process requests via a Message Queue (e.g., Redis/RabbitMQ).

## 2. SOLID Principles Application
*   **Single Responsibility Principle (SRP):** 
    *   `AyushScraper`: Only handles Playwright navigation and link extraction.
    *   `DocumentDownloader`: Only handles standard HTTP downloading of PDFs.
    *   `PdfProcessor`: Only handles OCR/text extraction.
*   **Open/Closed Principle (OCP):** The base `Connector` interface allows adding new AYUSH routes (e.g., `/tenders`) without modifying existing logic.
*   **Liskov Substitution Principle (LSP):** `AyushRetrievalAdapter` implements the standard LangGraph `BaseTool` interface, perfectly substitutable for any other data source tool.
*   **Interface Segregation Principle (ISP):** Instead of a massive `IScraper`, we use `IHtmlRenderer` and `IDownloader`.
*   **Dependency Inversion Principle (DIP):** The LangGraph agent depends on the `IAyushConnector` abstraction, not the concrete Playwright implementation.

## 3. LangGraph Multi-Agent Integration (Adapter Pattern)
To prevent LLM hallucination and ensure decoupling, LangGraph must **never** know about Playwright, Angular, or headless browsers. It interacts purely through a unified `Retrieval Adapter` interface. 

*   **Node:** `Research Planner Agent`
*   **Adapter Interface:** `AyushRetrievalAdapter` implements `retrieve(source="AYUSH", query, jurisdiction="IN")`
*   **State Interaction:** 
    1.  LangGraph fires the abstract `retrieve(...)` command.
    2.  The `AyushRetrievalAdapter` catches it, translating the semantic query into specific actions (e.g., navigating to `/whatsnew` or triggering the browser pool).
    3.  The Adapter formats the output and returns strictly structured `Normalized Evidence` back to the orchestrator.

## 4. Workload & Data Flow Model
```text
LangGraph (Research Planner)
       ↓
retrieve(source="AYUSH", query="Ayurveda guidelines", jurisdiction="IN")
       ↓
[ AYUSH Retrieval Adapter ]  <-- (Abstractions Boundary)
       ↓
[ Task Queue / Rate Limiter ]
       ↓
Ayush Playwright Pool (Max N Instances)
       ↓
Browser (Wait for Angular to render)
       ↓
Extract DOM Links
       ↓
Async Worker Pool (Download & Chunk PDFs)
       ↓
Normalized Evidence (Returned to LangGraph)
```

## 5. Production Readiness & Failure Engineering
*   **Timeout & Retries:** Playwright `goto` will have a strict 15s timeout. Exponential backoff for retries.
*   **Graceful Degradation:** If the Angular app structure changes, the scraper will fail gracefully, returning "Data Source Unavailable" to the LLM rather than crashing the orchestrator.
*   **Observability:** Trace Playwright startup times, navigation times, and PDF extraction times to monitor SLA.
