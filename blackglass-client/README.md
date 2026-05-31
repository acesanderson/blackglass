# blackglass-client

A command-line interface for interacting with Obsidian vaults hosted over HTTP via Blackglass.

This client enables remote management, querying, and full-text/semantic searching of an Obsidian vault from the terminal or external scripts.

## Installation

Install the package using pip:

```bash
pip install blackglass-client
```

Or install it via pipx to run it in an isolated environment:

```bash
pipx install blackglass-client
```

## Configuration

The client requires connection details to the Blackglass server. Configure these by setting environment variables in the shell:

```bash
export BLACKGLASS_URL="http://172.16.0.3:8083"
export BLACKGLASS_API_KEY="your-secret-api-key"
```

| Environment Variable | Description | Default |
| :--- | :--- | :--- |
| `BLACKGLASS_URL` | Base URL of the Blackglass API server | `http://172.16.0.3:8083` |
| `BLACKGLASS_API_KEY` | Authentication token for the server | None (Optional if server doesn't require auth) |

## Quick Start

Create, retrieve, and search notes with a few commands:

```bash
# Create a new note
blackglass notes create "Work/Task.md" --content "# Refactor CLI

The CLI client needs clean documentation."

# Get note metadata and content
blackglass notes get "Work/Task.md"

# Perform a semantic search across the vault
blackglass search semantic "reorganizing command line tools"
```

## Usage Reference

All commands accept an optional `--json` flag to return raw server responses instead of formatted text.

### Note Management

Perform standard CRUD operations on notes within the vault. All note paths are relative to the vault root.

#### Create a note
```bash
blackglass notes create "path/to/note.md" --content "Note content goes here"
```

#### Get a note
```bash
blackglass notes get "path/to/note.md"
```

#### Update a note (overwrites entire content)
```bash
blackglass notes update "path/to/note.md" --content "New note content"
```

#### Append to a note
```bash
blackglass notes append "path/to/note.md" "Additional line of text"
```

#### Set YAML frontmatter
```bash
blackglass notes set-frontmatter "path/to/note.md" "status" "in-progress"
```

#### Delete a note
```bash
blackglass notes delete "path/to/note.md"
```

### Vault Operations

Query structural and relational data about the entire vault.

#### List all files
```bash
blackglass vault files
```

#### List all tags with usage counts
```bash
blackglass vault tags
```

#### List periodic/daily notes
```bash
blackglass vault periodic
```

#### List backlinks to a note
```bash
blackglass vault backlinks "path/to/note.md"
```

#### Trigger server git sync and re-indexing
```bash
blackglass vault sync
```

### Search

Query the vault using full-text or vector-based semantic search.

#### Full-text search
Find exact matches and keyword occurrences:
```bash
blackglass search text "refactor"
```

#### Semantic search
Find concepts and related context (even without exact keyword matches) using server-side embeddings:
```bash
blackglass search semantic "code improvements" --limit 5
```
