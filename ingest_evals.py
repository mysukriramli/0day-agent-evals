#!/usr/bin/env python3
"""
0Day Agent Evals Wire
Mines recently merged bug-fix PRs to generate uncontaminated, zero-day 
coding benchmarks for AI agent testing and RLHF fine-tuning.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

LANGUAGES = ["python", "typescript", "go"]
DATA_DIR = "data"

def get_headers():
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def fetch_diff(diff_url: str) -> str:
    """Fetches the raw Git patch (the solution)."""
    try:
        res = requests.get(diff_url, headers=get_headers(), timeout=10)
        if res.status_code == 200:
            return res.text
    except Exception:
        pass
    return ""

def save_data(language: str, records: list, md_text: str):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    year_str, month_str = now.strftime("%Y"), now.strftime("%m")
    
    base_dir = os.path.join(DATA_DIR, language)
    archive_dir = os.path.join(base_dir, "archive", year_str, month_str)
    os.makedirs(archive_dir, exist_ok=True)
    
    payload = {
        "metadata": {
            "language": language,
            "generated_at": now.isoformat(),
            "total_evals": len(records),
            "schema_version": "1.0.0"
        },
        "benchmarks": records
    }
    
    # 1. Rolling active JSON
    with open(os.path.join(base_dir, "today.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        
    # 2. Token-efficient LLM digest
    with open(os.path.join(base_dir, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(md_text)
        
    # 3. Permanent historical archive
    with open(os.path.join(archive_dir, f"{date_str}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

def generate_root_llms():
    now_iso = datetime.now(timezone.utc).isoformat()
    content = f"""# 0Day Agent Evals Wire
> Continuous, uncontaminated coding benchmarks for AI agents.
> Last synchronized: {now_iso}

## The Problem with Static Benchmarks
Foundation LLMs pre-train on GitHub, meaning they memorize standard benchmarks like SWE-bench. This wire generates a daily stream of *Zero-Day* benchmarks—bugs fixed and merged in the last 24 hours—guaranteeing they are absent from LLM pre-training datasets.

## Available Evaluation Feeds
- **Python:** [Active Evals](data/python/today.json)
- **TypeScript:** [Active Evals](data/typescript/today.json)
- **Go:** [Active Evals](data/go/today.json)

## How to Test Your Agent
1. Fetch `today.json` for your target language.
2. Clone the `repository` and `git checkout base_commit_sha`.
3. Provide your agent with the `task_description`.
4. Compare your agent's generated patch against the `solution_diff`.
"""
    with open("llms.txt", "w", encoding="utf-8") as f:
        f.write(content)

def main():
    # Only fetch PRs merged since yesterday to ensure zero-day freshness
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
    headers = get_headers()
    
    for lang in LANGUAGES:
        logging.info(f"Fetching zero-day evals for {lang}...")
        # Search for recently merged bugs in target language
        query = f"is:pr is:merged merged:>{yesterday} label:bug language:{lang}"
        search_url = f"https://api.github.com/search/issues?q={query}&sort=updated&order=desc&per_page=15"
        
        try:
            res = requests.get(search_url, headers=headers, timeout=15)
            res.raise_for_status()
            items = res.json().get("items", [])
            
            records = []
            md_lines = [
                f"# Zero-Day {lang.capitalize()} Evals",
                f"> Uncontaminated bugs merged after {yesterday}.\n"
            ]
            
            for item in items:
                pr_url = item.get("pull_request", {}).get("url")
                if not pr_url: 
                    continue
                
                pr_res = requests.get(pr_url, headers=headers, timeout=10)
                if pr_res.status_code != 200: 
                    continue
                
                pr_info = pr_res.json()
                repo_name = pr_info.get("base", {}).get("repo", {}).get("full_name")
                base_sha = pr_info.get("base", {}).get("sha")
                diff_url = pr_info.get("diff_url")
                
                diff_text = fetch_diff(diff_url)
                # Filter out massive refactors; keep diffs under 12k chars to save tokens
                if not diff_text or len(diff_text) > 12000: 
                    continue
                
                # Combine title and body to form the prompt task
                task_desc = f"{item.get('title', '')}\n\n{item.get('body', '')}"
                
                records.append({
                    "eval_id": f"eval-{pr_info['id']}",
                    "repository": repo_name,
                    "language": lang,
                    "base_commit_sha": base_sha,
                    "pull_request_url": pr_info.get("html_url"),
                    "task_description": task_desc.strip(),
                    "solution_diff": diff_text
                })
                
                md_lines.append(f"### [{repo_name}] {item.get('title')}")
                md_lines.append(f"- **Base Commit:** `{base_sha}`")
                md_lines.append(f"- **Solution PR:** {pr_info.get('html_url')}\n")
                
            if records:
                save_data(lang, records, "\n".join(md_lines))
                logging.info(f"Saved {len(records)} evals for {lang}.")
            else:
                logging.warning(f"No valid evals found for {lang} today.")
                
        except Exception as e:
            logging.error(f"Failed to process {lang}: {e}")
            
    generate_root_llms()

if __name__ == "__main__":
    main()
