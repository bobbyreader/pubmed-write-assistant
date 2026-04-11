# AI Paper Tool

An AI-powered academic paper generation system that produces structured papers (Outline, Introduction, Related Work) with **verified real citations** from Semantic Scholar — no hallucinations.

## Features

- **Real Citation Map**: Every citation is verified against Semantic Scholar data
- **Anti-Hallucination**: Writer/Reviewer/Editor agents are constrained to only use citations from the citation_map
- **Multi-Agent Pipeline**: Researcher → Writer → Reviewer → Editor with 2-3 iteration rounds
- **Early Exit**: Stops iterating when Reviewer score >= 8.5 and citation accuracy == 10
- **Full-Context RAG**: All paper abstracts injected into Writer context
- **Interactive UI**: Streamlit app with sidebar paper list, round-by-round expander, and Markdown download

## Architecture

```
ai-paper-tool/
├── agents/                  # Agent classes
│   ├── base_agent.py        # Abstract base + LLMService integration
│   ├── researcher.py        # Semantic Scholar search → citation_map
│   ├── writer.py            # Outline + Introduction + Related Work
│   ├── reviewer.py          # Scored critique + hallucination check
│   └── editor.py           # Revision based on reviewer feedback
├── backend/services/
│   ├── llm_service.py       # MiniMax M2.7 via Anthropic SDK
│   ├── search_service.py    # Semantic Scholar API wrapper
│   ├── citation_service.py  # citation_map lifecycle management
│   └── rag_service.py      # Full-context RAG injection
├── workflows/
│   └── writing_pipeline.py  # Orchestrates the full pipeline
├── utils/
│   └── prompts.py           # All system prompts (anti-hallucination enforced)
└── app.py                   # Streamlit frontend
```

## Installation

```bash
# 1. Clone / navigate to project
cd ai-paper-tool

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL
```

## Configuration

Edit `.env`:

```env
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_BASE_URL=https://api.minimax.chat/v1
ANTHROPIC_MODEL=MiniMax-M2.7-highspeed
```

## Running

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## Usage

1. Enter a research topic (Chinese or English)
2. Click **Generate Paper**
3. Wait for the pipeline to complete:
   - 🔍 Researcher searches Semantic Scholar
   - ✍️ Writer generates draft
   - 🔎 Reviewer evaluates (up to 3 rounds)
   - ✏️ Editor revises
4. Download the final Markdown

## Test Topics

Try these topics to test the system:

**English:**
- `LLM reasoning in scientific discovery`
- `Retrieval-augmented generation for medical QA`
- `Attention mechanisms in vision transformers`

**Chinese:**
- `大语言模型在科学发现中的应用`
- `检索增强生成技术在医学问答系统中的应用`
- `注意力机制在计算机视觉中的应用`

## Citation Verification

All citations are validated:
- Writer can only use `[N]` numbers from the citation_map
- Reviewer checks for hallucinated citations and flags them
- Editor removes unsupported citations rather than replacing them
- Final References section is auto-formatted from citation_map

## Error Handling

- API failures: 3x retry with exponential backoff (built into LLMService)
- No search results: Friendly message to try different keywords
- JSON parse errors: Caught and surfaced as pipeline errors
- Hallucination flags: Displayed in Reviewer UI with warnings
