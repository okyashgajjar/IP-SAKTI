# Retrieval Architecture: WIPO Lex (IP Country)

## 1. Overview & VegaVelocity Scale Principles
WIPO Lex utilizes custom Web Components (Shadow DOM) and is protected by AWS CloudFront. Following VegaVelocity's principle **"Abuse Prevention & Bot Protection"**, high-speed scraping will immediately result in IP bans (CloudFront 404s). 

**Bottleneck Analysis:**
*   **Likely Bottleneck (P0):** AWS CloudFront WAF blocking our IP due to rapid consecutive requests.
*   **Mitigation:** Strict concurrency limits (e.g., 1 request per 3 seconds), IP rotation/proxy pools if scaling is required, and mimicking human behavior (jitter, full browser rendering).

## 2. SOLID Principles Application
*   **Single Responsibility Principle (SRP):** 
    *   `ShadowDomInjector`: Solely handles executing JS inside Playwright to pierce the Shadow DOM.
    *   `WipoParser`: Extracts table data from the rendered WIPO results.
*   **Open/Closed Principle (OCP):** New WIPO treaty types or topics can be added by passing new configurations to the injector, without changing the execution logic.
*   **Liskov Substitution Principle (LSP):** Implements LangGraph's `BaseTool`.
*   **Interface Segregation Principle (ISP):** Separate interfaces for `ITreatySearch` and `ILegislationSearch`.
*   **Dependency Inversion Principle (DIP):** High-level agents depend on IP legal concepts, not Shadow DOM manipulation.

## 3. LangGraph Multi-Agent Integration (Adapter Pattern)
To prevent LLM hallucination and ensure decoupling, LangGraph must **never** know about Shadow DOM manipulation or CloudFront WAF. It interacts purely through a unified `Retrieval Adapter` interface.

*   **Node:** `Research Planner Agent`
*   **Adapter Interface:** `WipoLexRetrievalAdapter` implements `retrieve(source="WIPO_LEX", query, jurisdiction="US")`
*   **State Interaction:** 
    1.  LangGraph fires the abstract `retrieve(...)` command.
    2.  The `WipoLexRetrievalAdapter` catches it, translating the semantic query into the correct JS injection commands for Playwright.
    3.  The Adapter formats the output and returns strictly structured `Normalized Evidence` back to the orchestrator.

## 4. Workload & Data Flow Model
```text
LangGraph (Research Planner)
       ↓
retrieve(source="WIPO_LEX", query="Patent rules", jurisdiction="US")
       ↓
[ WipoLex Retrieval Adapter ]  <-- (Abstractions Boundary)
       ↓
[ Job Queue + Strict Rate Limiter (Jitter) ]
       ↓
Playwright Engine (Single/Low Concurrency)
       ↓
Shadow DOM JS Injection (Trigger Search)
       ↓
DOM Table Extraction
       ↓
PDF Downloader (Rate-limited HTTP)
       ↓
Normalized Evidence (Returned to LangGraph)
```

## 5. Production Readiness & Failure Engineering
*   **Graceful Degradation:** CloudFront bans are a reality. If blocked, the tool must cleanly return a `LowConfidence/HighRisk` state to LangGraph, triggering the `Human IP Facilitator` fallback rather than crashing.
*   **Component Volatility:** Custom web components (`<wu-input-text>`) may change. Integration tests must run daily to verify the JS injection payload still works.
*   **Cost:** Proxy rotation for AWS CloudFront bypass can be expensive. Cache WIPO results heavily; only fetch when a specific law is missing from the local Evidence Store.
