# docupipe

A universal document transfer pipeline tool that retrieves content from various document sources, processes it through configurable steps, and transfers it to multiple destination systems.

## Why docupipe?

In the age of AI, document management faces many challenges:

- **Format conversion**: Incompatible document formats between different systems
- **Content migration**: Batch document migration during knowledge base relocation or system switching
- **Intelligent processing**: Preparing standardized document content for knowledge graphs and retrieval systems
- **Location transfer**: Document transfer between different storage systems

docupipe provides a universal, extensible framework to solve these problems.

## Key Features

- **Plugin architecture**: Four types of pluggable components: Source, Destination, Step, and Converter
- **YAML configuration**: Declarative configuration with environment variable interpolation
- **State management**: Support for resume and incremental sync
- **Multiple document sources**: DingTalk Knowledge Base, local file system, etc.
- **Multiple destination systems**: Local files, HindSight Memory, etc.
- **Format conversion**: Integration with markitdown, MinerU, and other conversion engines
- **Intelligent processing**: AI-powered image description and other processing steps

## Installation

### Via pip (recommended)

```bash
pip install docupipe
```

For PDF with embedded images (requires OCR), install the optional dependency:

```bash
pip install "docupipe[mineru]"
```

### From source

```bash
# Clone the repository
git clone <repository-url>
cd docupipe

# Install dependencies (uv recommended)
pip install uv
uv pip install -e ".[dev]"

# For PDF with embedded images (requires OCR)
uv pip install -e ".[mineru]"

# Or install all optional dependencies
uv pip install -e ".[all]"

# Or use pip
pip install -e ".[dev]"
pip install -e ".[mineru]"  # PDF support
```

## Quick Start

The following example uses local files as both source and destination, requiring no external dependencies.

### 1. Prepare configuration file

Create `docupipe.yaml`:

```yaml
pipelines:
  - name: quick-start
    source:
      localdrive:
        input_dir: ./input
        include: ["*.md"]
    destination:
      localdrive:
        output_dir: ./output
    steps: []
```

### 2. Prepare test files

```bash
mkdir -p input output
echo "Hello, docupipe!" > input/hello.md
```

### 3. Run the pipeline

```bash
python -m docupipe run
```

View the output:

```bash
cat output/hello.md
```

## Command Line Options

```bash
python -m docupipe run [OPTIONS]

Options:
  --config PATH              Configuration file path (default: docupipe.yaml)
  --pipeline NAME            Specify pipeline name
  --resume                   Skip already processed documents
  --sync                     Sync only changed documents
  --dry-run                  Print only, don't execute
  --state-dir PATH           State file directory (default: ./.state)
  --log-level LEVEL          Log level (DEBUG/INFO/WARNING/ERROR)

# List available components
python -m docupipe sources       # List all Sources
python -m docupipe destinations  # List all Destinations
```

## Configuration

### Global Configuration

```yaml
# HindSight Memory configuration
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

# Image description configuration
image_description:
  api_key: ${IMAGE_DESCRIPTION_API_KEY}
  base_url: ${IMAGE_DESCRIPTION_BASE_URL}
  model: ${IMAGE_DESCRIPTION_MODEL:-gpt-4o}

# File type conversion rules
converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".pptx": markitdown
```

### Pipeline Configuration

Each pipeline contains:

- `source`: Data source configuration
- `destination`: Destination configuration
- `steps`: List of processing steps
- `options`: Optional configuration (resume, sync, etc.)

### Environment Variables

Create a `.env` file (only needed when using HindSight Memory or image description):

```bash
# HindSight Memory configuration
HINDSIGHT_API_URL=http://localhost:8888
HINDSIGHT_API_KEY=your_api_key
HINDSIGHT_BANK_ID=your_bank_id

# Image description API configuration
IMAGE_DESCRIPTION_API_KEY=your_api_key
IMAGE_DESCRIPTION_BASE_URL=http://localhost:8002/v1
IMAGE_DESCRIPTION_MODEL=gpt-4o
```

### Environment Variable Interpolation

Supports `${VAR}` and `${VAR:-default}` syntax:

```yaml
api_key: ${API_KEY}                          # Required
model: ${MODEL:-gpt-4o}                      # Default value
base_url: ${BASE_URL:-http://localhost:8080} # Default value
```

## Use Cases

### Use Case 1: Download documents from DingTalk Knowledge Base to local

Before using DingTalk Knowledge Base, install `dws` (official DingTalk CLI) and complete authentication:

```bash
# Install dws (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh | sh

# Or via npm
npm install -g dingtalk-workspace-cli

# Authenticate (browser QR code)
dws auth login

# Headless environment use device flow
dws auth login --device
```

> If your organization has not enabled CLI access, scan the QR code and apply to the administrator as prompted. Administrators can enable it in DingTalk Open Platform → "CLI Access Management".

Configure the pipeline:

```yaml
pipelines:
  - name: dingtalk-download
    source:
      dingtalk:
        # Use knowledge base name (program will auto-query ID)
        space: "Product Knowledge Base"
        # Or use space_id directly
        # space_id: "kfiwoue83nkxQXyA"
        folders: ["Product Planning Materials"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      localdrive:
        output_dir: ./output/dingtalk
    steps: []
```

### Use Case 2: Local document format conversion

```yaml
pipelines:
  - name: convert-docs
    source:
      localdrive:
        input_dir: ./output/dingtalk
        include: ["*.docx"]
    destination:
      localdrive:
        output_dir: ./output/markdown
    steps:
      - convert          # Convert to markdown
      - image_description # Add descriptions to images
```

### Use Case 3: Write local documents to HindSight Memory

```yaml
pipelines:
  - name: to-hindsight
    source:
      localdrive:
        input_dir: ./output/markdown
        include: ["*.md"]
    destination:
      hindsight:
        context_prefix: "Product Knowledge Base"
    steps: []
```

### Use Case 4: ALL IN ONE

```yaml
pipelines:
  - name: full-pipeline
    source:
      dingtalk:
        space: "Product Knowledge Base"
    destination:
      hindsight:
        context_prefix: "Knowledge Base"
    steps:
      - convert
      - image_description
```

## Available Components

### Source

- `dingtalk`: DingTalk Knowledge Base
- `localdrive`: Local file system

### Destination

- `localdrive`: Local file system
- `hindsight`: HindSight Memory

### Step

- `convert`: Document format conversion
- `image_description`: Image description generation

### Converter

- `markitdown`: Common office documents
- `mineru`: High-quality PDF conversion

## State Management

docupipe maintains state files (`{source}_{dest}_state.json`) for each source-dest combination, recording:

- Processed document IDs
- Document hashes (for change detection)

### Run Modes

- **Default mode**: Process all documents
- **--resume**: Skip already processed documents
- **--sync**: Sync only changed documents, remove documents deleted from source

## Architecture

```
source.list_documents() → [DocumentMeta]
  → filter (resume skips processed / sync only syncs changes)
    → source.fetch(meta) → Document
      → steps process sequentially (convert → image_description → ...)
        → dest.write(doc)
          → state.mark_done()
```

## Development

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run single test file
python -m pytest tests/test_pipeline.py -v
```

### Adding New Components

All components use decorators for registration. Adding a new component requires three steps:

1. **Implement the abstract base class**
2. **Add the decorator**: `@register_source("name")`
3. **Import in __init__.py**

Example:

```python
# sources/custom.py
from docupipe.sources.base import BaseSource
from docupipe.sources import register_source

@register_source("custom")
class CustomSource(BaseSource):
    def list_documents(self):
        # Implement document list logic
        pass

    def fetch(self, meta):
        # Implement document fetch logic
        pass
```

## Dependencies

- Python 3.11+
- Click (CLI framework)
- Rich (Terminal output)
- PyYAML (Configuration parsing)
- markitdown (Document conversion)
- MinerU (PDF OCR conversion with embedded images)
- hindsight-client (HindSight Memory client)
- OpenAI SDK (Image description)

## License

MIT License

## Contributing

Issues and Pull Requests are welcome!