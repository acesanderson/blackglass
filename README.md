# blackglass

Headless API and command-line interface for managing and querying Markdown-based personal knowledge bases.

## Overview

Blackglass provides a programmable layer over local Markdown vaults (such as Obsidian). It exposes an HTTP API and CLI for manipulating notes, managing frontmatter, computing backlinks, and performing both full-text and vector-based semantic searches.

## Quick Start

### 1. Installation

Install the server and client components:

```bash
pip install blackglass-server blackglass-client
```

### 2. Configuration

Set the required environment variables:

```bash
export BLACKGLASS_VAULT_PATH="/path/to/your/vault"
export BLACKGLASS_API_KEY="your-secure-token"
export POSTGRES_PASSWORD="your-db-password"
```

### 3. Launch the Server

Start the API service:

```bash
python -m blackglass_server
```

### 4. Basic CLI Usage

Initialize the semantic index and search your vault:

```bash
# Sync files and generate embeddings
blackglass vault sync

# Perform a semantic search
blackglass search semantic "how do i implement vector search in postgres"
```

## Architecture

*   **blackglass-server**: A FastAPI service that interacts directly with the filesystem and a PostgreSQL database. It handles frontmatter parsing, wikilink extraction, and provides the search engine.
*   **blackglass-client**: A Click-based CLI that communicates with the server via HTTP.
*   **Database**: Uses PostgreSQL with the `pgvector` extension to store and query document embeddings.
*   **Embeddings**: Requires a connection to a compatible embedding service (defaulting to a local "backwater" instance) to process text into vectors.

## Core Features

### Semantic and Full-Text Search
The system supports standard keyword matching and vector-based semantic search. The semantic search uses `pgvector` for cosine similarity across the vault.

### Frontmatter Manipulation
The API provides atomic operations to modify YAML frontmatter without rewriting the entire file manually.

```bash
# Add or update a tag in a note's frontmatter
blackglass notes patch "projects/blackglass.md" --op set_frontmatter --key status --value active
```

### Git Synchronization
The `/vault/sync` endpoint triggers a `git pull` on the vault directory and incrementally updates the vector database by comparing file hashes.

### Knowledge Graph Tools
The server extracts wikilinks and computes backlinks dynamically, allowing tools to discover relationships between documents without manual indexing.

## Configuration Reference

| Environment Variable | Description | Default |
| --- | --- | --- |
| `BLACKGLASS_VAULT_PATH` | Absolute path to the Markdown vault | (Required) |
| `BLACKGLASS_API_KEY` | Token for X-API-Key header authentication | (Required) |
| `BLACKGLASS_PORT` | Port for the FastAPI server | `8083` |
| `BLACKGLASS_BACKWATER_URL` | URL of the embedding provider service | `http://localhost:8080` |
| `POSTGRES_PASSWORD` | Password for the PostgreSQL database | (Required) |
| `POSTGRES_USERNAME` | Username for the PostgreSQL database | `bianders` |

## API Endpoints

### Notes
*   `GET /vault/notes/{path}`: Retrieve note content, frontmatter, and metadata.
*   `POST /vault/notes`: Create a new note.
*   `PATCH /vault/notes/{path}`: Perform `append`, `prepend`, or `set_frontmatter` operations.
*   `DELETE /vault/notes/{path}`: Remove a note.

### Vault Discovery
*   `GET /vault/files`: List all Markdown files.
*   `GET /vault/tags`: Aggregate all tags and their frequencies.
*   `GET /vault/backlinks/{path}`: List files referencing the target path.
*   `GET /vault/periodic`: List date-based notes (YYYY-MM-DD.md).

### Search and Sync
*   `GET /vault/search?q={query}`: Execute full-text search.
*   `GET /vault/semantic-search?q={query}`: Execute vector similarity search.
*   `POST /vault/sync`: Pull Git changes and re-index modified files.

## Prerequisites

*   Python 3.12 or higher.
*   PostgreSQL with the `pgvector` extension installed.
*   Git (if using the sync functionality).
