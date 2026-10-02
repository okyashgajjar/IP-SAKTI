# Ayurveda IP & Regulatory Advisor

An AI-powered legal guidance orchestrator designed for Ayurveda Intellectual Property, Regulatory Compliance (D&C Act, FSSAI), and Access & Benefit Sharing (ABS / NBA).

---

## 🛑 The Problem
Ayurveda practitioners, startups, and researchers face a highly complex legal landscape.
- **Fragmented Laws:** Users must navigate multiple conflicting domains simultaneously (Drugs & Cosmetics Act, FSSAI regulations, Biological Diversity Act, WIPO patent laws).
- **High Risk of Non-Compliance:** Startups frequently face export bans or legal action because they misunderstood regulatory boundaries. 
  - *Example:* Misclassifying a proprietary medicine as an "Ayurveda Aahara" (food supplement) under FSSAI, triggering regulatory penalties.
- **Costly & Slow:** Traditional IP and legal consultations are extremely expensive, slow, and often lack specialized cross-domain Ayurveda knowledge.

## 🛡️ Mitigation
We designed a deterministic legal reasoning engine that acts as a strict IP Facilitator, mitigating liability through built-in guardrails.
- **Zero Hallucination:** The system is strictly forbidden from "guessing" laws. It must actively retrieve and cross-reference real statutory text.
- **Hard Citations:** Every claim must be backed by a specific Act, Section, or Rule.
- **Risk Assessment Guardrails:** 
  - *Example:* If a user asks "Can I patent this secret formula?", the system assesses the query as "High Risk / Low Confidence", refuses to synthesize a potentially harmful answer, and escalates the query to a human IP lawyer.

## 💡 How We Solve It
We built a **LangGraph-based Orchestrator** featuring an 8-node deterministic pipeline. 
1. **Dynamic Tool Routing:** The LLM parses the user intent to decide exactly which statutory databases to search.
   - *Example:* A query about exporting Neem automatically triggers searches in the NBA (Access & Benefit Sharing) and WIPO Lex databases.
2. **SOLID Data Adapters:** We interface with databases using completely decoupled retrieval adapters, ensuring strict legal data extraction.
3. **Citation & Feedback Loops:** Our `Citation Validator` checks the AI's response for hard legal citations. If citations are missing, the graph structurally loops backwards to fetch more evidence.
4. **Escalation Queue:** Queries that fail the `Confidence Assessor` are instantly routed away from the user and into a human review queue.

## ⚡ Latency & Scaling
To ensure real-time enterprise performance:
- **Parallel Retrieval:** The `Evidence Retrieval` node queries all required databases simultaneously rather than sequentially.
- **Auto-Routing Models:** Configured natively with `openrouter/free` to auto-route LLM requests to the fastest available node (like Gemma-4 or Nemotron), bypassing rate-limit hangups.
- **Monolithic Speed:** Designed using a monolithic PostgreSQL + pgvector architecture (modeled here via SQLite for local testing) to avoid the network latency inherent in microservices.

---

## 🏛 System Architecture

The application is built on a monolithic, highly decoupled architecture using FastAPI, LangGraph, and a local SQLite database, preparing it for highly scalable enterprise environments.

```mermaid
graph TD
    UI[Frontend Client <br/> HTML/CSS/JS] -->|POST /api/chat| API(FastAPI Backend)
    
    API --> ORCH[LangGraph Orchestrator]
    API --> DB[(SQLite Database)]
    
    subgraph Agentic Pipeline
        ORCH --> N1[1. Input & Lang State]
        N1 --> N2[2. Query Understanding]
        N2 --> N3[3. Research Planner]
        N3 --> N4[4. Evidence Retrieval]
        N4 --> N5[5. Evidence Reasoner]
        N5 --> N6[6. Citation Validator]
        N6 --> N7[7. Confidence Assessor]
        N7 --> N8[8. Answer Synthesis]
    end
    
    subgraph SOLID Data Adapters
        N4 --> A1(AyushAdapter)
        N4 --> A2(IndiaCodeAdapter)
        N4 --> A3(FssaiAdapter)
        N4 --> A4(NbaAdapter)
        N4 --> A5(WipoLexAdapter)
    end
```

---

## 🧠 LangGraph Pipeline Flow

The orchestrator utilizes **LangGraph Conditional Routing**. If citations are missing, it actively loops back to fetch more evidence. If a query is high-risk and low-confidence, it escalates and bypasses the AI synthesis.

```mermaid
stateDiagram-v2
    [*] --> InputLanguage
    InputLanguage --> QueryUnderstanding : Extract Intent & Jurisdiction
    QueryUnderstanding --> ResearchPlanner : Build Search Queue
    
    ResearchPlanner --> EvidenceRetrieval : Call Adapters
    EvidenceRetrieval --> EvidenceReasoner : Analyze Texts
    EvidenceReasoner --> CitationValidator : Verify Sections/Acts
    CitationValidator --> ConfidenceAssessor : Score Risk (Low/Med/High)
    
    ConfidenceAssessor --> ResearchPlanner : Missing Citations (Loop Retry)
    ConfidenceAssessor --> AnswerSynthesis : High/Med Confidence
    ConfidenceAssessor --> EscalationQueue : High Risk / Low Confidence
    
    AnswerSynthesis --> [*]
    EscalationQueue --> [*]
```

---

## 🧩 SOLID Adapter Design (Class Diagram)

Data ingestion is strictly decoupled. Every source must implement the `RetrievalAdapter` interface, guaranteeing that the Orchestrator (LangGraph) is isolated from web-scraping or API-specific logic.

```mermaid
classDiagram
    class RetrievalAdapter {
        <<interface>>
        +retrieve(query: str, jurisdiction: str) dict
    }
    
    class AyushRetrievalAdapter {
        +retrieve(query: str, jurisdiction: str) dict
    }
    class FssaiRetrievalAdapter {
        +retrieve(query: str, jurisdiction: str) dict
    }
    class IndiaCodeRetrievalAdapter {
        +retrieve(query: str, jurisdiction: str) dict
    }
    class NbaRetrievalAdapter {
        +retrieve(query: str, jurisdiction: str) dict
    }
    class WipoLexRetrievalAdapter {
        +retrieve(query: str, jurisdiction: str) dict
    }
    
    RetrievalAdapter <|-- AyushRetrievalAdapter
    RetrievalAdapter <|-- FssaiRetrievalAdapter
    RetrievalAdapter <|-- IndiaCodeRetrievalAdapter
    RetrievalAdapter <|-- NbaRetrievalAdapter
    RetrievalAdapter <|-- WipoLexRetrievalAdapter
```

---

## 🗄️ Database Architecture

The persistence layer tracks sessions, chat histories, documents, and escalations. (Designed for SQLite locally, scales perfectly to PostgreSQL).

```mermaid
erDiagram
    USERS ||--o{ CHAT_SESSIONS : creates
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : contains
    CHAT_SESSIONS ||--o| ESCALATIONS : triggers
    
    DOCUMENTS ||--|{ DOCUMENT_CHUNKS : split_into
    CHAT_MESSAGES }o--o{ DOCUMENT_CHUNKS : cites
    
    USERS {
        uuid id PK
        string role "startup, practitioner, aayush_admin"
        timestamp created_at
    }
    
    DOCUMENTS {
        uuid id PK
        string source_authority "AYUSH, FSSAI, INDIA_CODE"
        string jurisdiction "IN, US, WIPO"
        string title
        timestamp fetch_date
    }
    
    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        string chunk_text
        jsonb metadata "section_id, act_number"
    }

    CHAT_SESSIONS {
        uuid id PK
        uuid user_id FK
        string jurisdiction_lane
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid session_id FK
        string role "user, assistant"
        string content
        jsonb metadata "confidence, sources"
    }
```

---

## 📁 Directory Structure
```
.
├── AGENTS/             # LangGraph nodes, state definitions, and pipeline compilation
├── DATA_SOURCES/       # Raw data sources and dummy files
├── docs/               # Project analysis, DB architecture, and worklogs
├── frontend/           # HTML/CSS UI assets
├── TOOLS/              # Data source retrieval adapters and DB client
├── .env.example        # Template for environment variables
├── .gitignore          # Python and Web standard Git exclusions
├── app.py              # FastAPI server serving the UI and API endpoints
├── database.db         # Local SQLite DB for persistence
└── README.md           # This file
```

---

## 🚀 Setup & Running

1. **Clone the repository**
2. **Setup Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   Add your keys. By default, it uses `openrouter/free` which automatically routes to the best free model available.
3. **Install dependencies:**
   ```bash
   pip install fastapi uvicorn langchain langgraph langchain-openai langchain-google-genai python-dotenv
   ```
4. **Run the server:**
   ```bash
   python3 app.py
   ```
5. **Access the application:** Open `http://localhost:8000` in your browser. Watch the terminal logs to see the pipeline traverse and route the LangGraph nodes in real-time!
