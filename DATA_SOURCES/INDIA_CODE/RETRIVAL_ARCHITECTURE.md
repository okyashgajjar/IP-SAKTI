# Retrieval Architecture: India Code

## 1. Overview & VegaVelocity Scale Principles
India Code operates on a highly mature DSpace 7/9 REST API. This is the ideal scenario. Following VegaVelocity's **"Design for 20,000+ concurrent users"**, we do NOT need headless browsers here. We can utilize highly concurrent, asynchronous HTTP clients.

**Bottleneck Analysis:**
*   **Likely Bottleneck (P0):** Rate limits imposed by the India Code API (HTTP 429 Too Many Requests).
*   **Mitigation:** Distributed rate limiter (e.g., Redis Token Bucket) and exponential backoff with jitter. Aggressive caching of static statutes.

## 2. SOLID Principles Application
*   **Single Responsibility Principle (SRP):** 
    *   `CommunityClient`: Fetches Communities/Collections.
    *   `ItemClient`: Fetches Legislation metadata.
    *   `BitstreamClient`: Downloads actual PDFs.
*   **Open/Closed Principle (OCP):** Easily extendable to include State-specific communities without altering the Central community logic.
*   **Liskov Substitution Principle (LSP):** Implements the same `IRetrievalTool` as other connectors for LangGraph.
*   **Interface Segregation Principle (ISP):** Clients are split by endpoint domains (Communities vs Bitstreams).
*   **Dependency Inversion Principle (DIP):** The LangGraph agent relies on a standardized `StatuteResponse` interface, regardless of the API layout.

## 3. LangGraph Multi-Agent Integration (Adapter Pattern)
To prevent LLM hallucination and ensure decoupling, LangGraph must **never** know about DSpace REST APIs or JSON schemas. It interacts purely through a unified `Retrieval Adapter` interface.

*   **Node:** `Research Planner Agent`
*   **Adapter Interface:** `IndiaCodeRetrievalAdapter` implements `retrieve(source="INDIA_CODE", query, jurisdiction="IN")`
*   **State Interaction:** 
    1.  LangGraph fires the abstract `retrieve(...)` command.
    2.  The `IndiaCodeRetrievalAdapter` catches it, translating the semantic query into a sequence of API calls (`/communities` -> `/items` -> `/bitstreams`).
    3.  The Adapter formats the output and returns strictly structured `Normalized Evidence` back to the orchestrator.

## 4. Workload & Data Flow Model
```text
LangGraph (Research Planner)
       ↓
retrieve(source="INDIA_CODE", query="Biological Diversity Act", jurisdiction="IN")
       ↓
[ IndiaCode Retrieval Adapter ]  <-- (Abstractions Boundary)
       ↓
[ Redis Rate Limiter ]
       ↓
Async HTTP Client Pool (aiohttp/httpx)
       ↓
India Code REST API (DSpace)
       ↓
JSON Metadata + PDF Bitstreams
       ↓
Chunker (Preserve Section IDs)
       ↓
Normalized Evidence (Returned to LangGraph)
```

## 5. Production Readiness & Failure Engineering
*   **Idempotency & Caching:** Statutes rarely change daily. Implement aggressive caching (e.g., 7 days TTL) for `/items` and `/bitstreams`.
*   **Retry Storm Prevention:** If India Code goes down, implement strict circuit breakers. Do not let 20k users trigger 20k retries to a failing government API.
*   **Data Integrity:** The pipeline preserves API-provided metadata (Ministry, Enactment Date) injecting it straight into the Vector DB metadata for precise filtering by the Evidence Reasoner.
