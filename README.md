# arxiv_papers

Tools for finding papers from arXiv.

# Install 

1. Create conda/virtual environment using python 3.12.
2. Clone repo and change directory `cd arxiv_papers`
3. Make sure your environment has been activated.
4. `pip install -e .`
5. Setup the client (below).

# Setup OpenAI Client

The filtering tools require an OpenAI API key.

The client is configured automatically by `setup_client()` using either:

1. A local JSON config file  
2. An environment variable  

The config file path is:

```
src/arxiv_papers/openai_config.json
```

## Recommended: Use an Environment Variable (More Secure)

This avoids storing your API key in the repository.

```bash
export OPENAI_API_KEY="sk-..."
```

## Alternative: Use a Config File

Create:

```
src/arxiv_papers/openai_config.json
```

Example:

```json
{
  "api_key": "sk-REPLACE_WITH_YOUR_KEY"
}
```


## Optional Configuration Fields

You may optionally include:

```json
{
  "api_key": "sk-REPLACE_WITH_YOUR_KEY",
  "base_url": "https://api.openai.com/v1",
  "organization": "org_XXXXXXXX",
  "project": "proj_XXXXXXXX"
}
```

### When to use these:

- **base_url**  
  Only required if using:
  - Azure OpenAI
  - A proxy
  - A custom API gateway

- **organization**  
  Needed only if your account belongs to multiple organizations.

- **project**  
  Optional. Useful for usage tracking under OpenAI Projects.

## Security Recommendation

**Never commit your API key to version control.**

Add this to `.gitignore`:

```
src/arxiv_papers/openai_config.json
```
