# Career Intelligence Agent — Local RAG Edition

## Oren Salami | AI Systems Engineer ## 

A privacy-first Career Intelligence Agent that helps evaluate job opportunities, analyze role fit, identify skill gaps, and recommend the most relevant portfolio projects using local data and evidence-based retrieval.

This project is a **decision-support system**, not an automation tool.

It is designed to help make better career decisions while keeping the user fully in control.

---

## Project Overview

The **Career Intelligence Agent** is a local AI-powered career analysis system built around personal career data, job descriptions, scoring logic, portfolio matching, and local RAG-based evidence retrieval.

The system analyzes job opportunities against a structured candidate profile, identifies strengths and gaps, recommends whether a role is worth pursuing, and suggests which portfolio projects best support the application.

Unlike automated job-application systems, this project does not apply to jobs automatically.

It helps the user think, compare, and decide based on structured analysis and evidence from their own documents.

---

## Purpose

The purpose of this project is to demonstrate:

- How to build a privacy-first local career intelligence system
- How to combine deterministic scoring with local RAG retrieval
- How to analyze job descriptions against real experience and portfolio projects
- How to support multiple execution modes: Hybrid, Agent Only, and RAG Only
- How to separate profile data, job analysis, scoring, retrieval, dashboard, and documentation
- How to create a practical AI decision-support tool without relying on paid APIs
- How to present a local AI system as part of a professional AI Engineering portfolio

---

## Core Capabilities

- Local job-description analysis
- Candidate profile matching
- Fit score calculation from 0 to 100
- Apply / Stretch / Skip recommendation labels
- Skill gap detection
- Strengths and risks analysis
- Portfolio project matching
- Weekly career insights
- Local Q&A over career documents
- TF-IDF-based local retrieval
- Hybrid / Agent Only / RAG Only execution modes
- Streamlit dashboard
- SQLite-based local storage
- Docker-based local deployment
- No cloud dependency for core features
- No API keys required for core workflows

---

## Architecture & System Design

The system is designed as a local decision-support platform with clear separation between configuration, data, retrieval, scoring logic, dashboard UI, tests, and documentation.

```text
career-intelligence-agent/
├── app/
│   ├── matching/
│   ├── rag/
│   ├── scoring/
│   ├── services/
│   └── utils/
├── config/
│   └── profile.yaml
├── dashboard/
│   └── streamlit_app.py
├── data/
├── knowledge_base/
├── scripts/
│   ├── init_db.py
│   ├── ingest_knowledge.py
│   └── fetch_jobs.py
├── tests/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

The system keeps career documents, retrieval, scoring, dashboard logic, and configuration separated so the project remains understandable, maintainable, and easy to extend.

---

## Tech Stack

- LayerTechnologies
- LanguagePython
- DashboardStreamlit
- Data StorageSQLite
- ORM / Data AccessSQLAlchemy
- RetrievalLocal TF-IDF
- AI LogicLocal RAG, scoring engine, rule-based analysis
- ConfigurationYAML
- DevOpsDocker, Docker Compose
- TestingPytest
- DocumentationMarkdown-based technical docs

---

## 📦 Repository Structure

config/
└── Profile and runtime configuration

data/
└── Local database and job data

knowledge_base/
└── Local career documents used for retrieval

scripts/
└── Database initialization, ingestion, and job-fetching utilities

app/
└── Core application logic, scoring, matching, and RAG components

dashboard/
└── Streamlit dashboard and user interface

tests/
└── Unit and integration tests

---

## How Local RAG Works

The local RAG workflow is based on private career documents stored on the user's machine.

Career documents
        ↓
knowledge_base/
        ↓
Local indexing with TF-IDF
        ↓
Relevant evidence retrieval
        ↓
Job analysis and career insight generation

The system works as follows:

Career documents are placed inside knowledge_base/
The system indexes them locally using TF-IDF
When a job description is analyzed, relevant evidence is retrieved
The output is grounded in the user's own data
Nothing needs to leave the local machine for the core workflow

---

## Execution Modes

The system supports three explicit execution modes from the dashboard sidebar.

ModeWhat RunsWhen to Use
Hybrid (RAG + Agent)Career scoring + knowledge base retrievalDefault mode for full analysis with evidence
Agent OnlyCareer scoring only, without knowledge retrievalWhen the knowledge base is not indexed or only scoring is needed
RAG OnlyKnowledge base retrieval only, without scoringWhen the user only wants to inspect available evidence

Each mode is shown clearly in the UI.

The dashboard displays:

- Active execution mode
- Mode description
- Execution status
- Components used during the run
- Success or failure state

Example:

Mode: Hybrid (RAG + Agent) | Status: Success | Components: Career Scorer + KB Retrieval
Mode Behavior
Hybrid — full analysis with career scoring and knowledge base evidence
Agent Only — scoring and recommendation without RAG evidence
RAG Only — evidence retrieval only, without scoring

The "Should I Apply?" and "Which Project?" actions require the scoring engine.
If RAG Only is selected, the UI prompts the user to switch to a scoring-enabled mode.

---

## Scoring System

The scoring system evaluates job fit across multiple dimensions.

- DimensionWeight
- Skill Overlap25%
- Title Relevance20%
- Seniority15%
- Domain Fit15%
- Work Mode10%
- Strategy Fit10%
- Portfolio Match5%

The result is translated into a practical recommendation label:

- Apply
- Stretch
- Skip

---

## Dashboard Overview

The Streamlit dashboard includes several sections for career analysis and decision support.

- SectionPurpose
- Decision ConsoleMain job evaluation workflow
- Classic JobsKeyword-based scoring and job list review
- AnalyticsTrends, signals, and career insights
- Weekly ReviewStrategic review of recurring patterns
- Profile ViewCandidate profile inspection
- Analyze External JobPaste and analyze external job descriptions
- Knowledge BaseManage local RAG index
- Career Q&AAsk questions over local career documents

---

## How to Run

1. Install dependencies
pip install -r requirements.txt
2. Initialize the database
python scripts/init_db.py
3. Ingest local career documents
python scripts/ingest_knowledge.py
4. Load mock job data
python scripts/fetch_jobs.py --mode mock
5. Start the dashboard
streamlit run dashboard/streamlit_app.py

Open:

http://localhost:8508

---

## Run with Docker

Recommended local execution:
```bash
docker compose up --build
```

Open:

'http://localhost:8508'

Stop the system:
```bash
docker compose down
```

---

## Configuration

Main profile configuration:
```bash
config/profile.yaml
```

Use this file to define:

- Target roles
- Experience level
- Work preferences
- Career direction
- Relevant skills
- Portfolio positioning

---

## Source Modes

The system can work with different job source modes.

- ModeDescription
- mockDemo data
- rssRemote job sources
- israelLocal Israeli job boards
- allCombined mode

---

## Tests

Run tests with:
```bash
python -m pytest tests/ -q
```

---

## Documentation

The public repository includes the README, source code, configuration examples,
tests, and local execution instructions required to understand and run the project.

Internal development notes, audit reports, validation records, AI-assistant
configuration, and private handover documents are intentionally excluded from
version control.

---

## Portfolio Demo

This project is part of my AI Engineering portfolio and can be presented as a local, privacy-first AI decision-support system.

The portfolio presentation focuses on:

- Career decision intelligence
- Local RAG over personal documents
- Structured scoring logic
- Portfolio matching
- Dashboard-based user experience
- Clear separation between automation and decision support

The system is designed to be understandable even without live external integrations.

---

## What This Project Demonstrates

This project demonstrates my ability to:

- Build privacy-first local AI systems
- Combine retrieval with deterministic scoring
- Design decision-support workflows instead of unsafe automation
- Structure a Streamlit-based AI dashboard
- Work with local databases and local knowledge bases
- Build RAG-style retrieval without cloud dependency
- Separate profile, scoring, retrieval, UI, and documentation layers
- Present a practical AI system in a portfolio-ready format

---

## Current Status

Status: Portfolio-ready / Local demo-ready / Decision-support system

This project is considered complete for portfolio presentation.

Future changes should be limited to:

- Small UI improvements
- Documentation updates
- Static demo alignment
- Minor bug fixes
- Optional source integration improvements

The project does not require paid APIs for core functionality.

---

## Important Notes
This system is not an automatic job application bot.
It does not apply to jobs on behalf of the user.
The user stays fully in control of all career decisions.
Core functionality is local and privacy-first.
The system is designed for analysis, prioritization, and decision support.

---

## Final Note

This project is part of my AI Engineering portfolio.

It represents a practical local AI decision-support system that combines career data, scoring logic, local RAG retrieval, Streamlit UI, and structured documentation.

The goal is not to automate career decisions, but to help make better decisions using evidence, structure, and clear analysis.

---

## License

This project is licensed under the MIT License.
See the LICENSE file for details.

---
