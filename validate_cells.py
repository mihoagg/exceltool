import argparse
import json
import os
import sys
import time
from pathlib import Path

import openpyxl
import requests
from dotenv import load_dotenv

from excel_helpers import parse_dinh_dang
from parser import parse

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXCEL_PATH = Path(r"C:\Users\PhuThaiCAT\Desktop\Code\vnsky\dinh_dang_095_soluong.xlsx")
SHEET_NAME = "Định dạng 095"
API_BASE = "https://openrouter.ai/api/v1/chat/completions"
BATCH_SIZE = 5
BATCH_DELAY = 0.5


def check_format(cell_value: str, parsed: dict) -> list[dict]:
    issues = []
    if not cell_value or not cell_value.strip():
        issues.append({"stage": "format", "type": "empty_cell", "severity": "fail", "detail": "Cell is empty"})
        return issues

    template = parsed.get("number", "")
    if not template:
        issues.append({"stage": "format", "type": "no_template", "severity": "fail", "detail": "Could not extract template from cell"})
        return issues

    paren_open = cell_value.count("(")
    paren_close = cell_value.count(")")
    if paren_open != paren_close:
        issues.append({
            "stage": "format", "type": "unbalanced_parens", "severity": "fail",
            "detail": f"Unbalanced parentheses: {paren_open} open vs {paren_close} close"
        })

    if paren_open > 0 and parsed.get("requirements") is None:
        issues.append({
            "stage": "format", "type": "unparseable_parens", "severity": "fail",
            "detail": "Cell contains parentheses but requirements could not be extracted"
        })

    return issues


def check_parse(requirements: str, conditions: list[dict]) -> list[dict]:
    issues = []
    if not requirements:
        return issues

    if not conditions:
        issues.append({
            "stage": "parse", "type": "empty_parse", "severity": "fail",
            "detail": f"Parser returned no conditions for: {requirements}"
        })
        return issues

    for i, cond in enumerate(conditions):
        if cond.get("type") == "raw":
            issues.append({
                "stage": "parse", "type": "raw_node", "severity": "warn",
                "detail": f"Condition {i + 1} is unparseable: {cond.get('raw', '?')}"
            })

    return issues


def check_variables(template: str, conditions: list[dict]) -> list[dict]:
    issues = []
    template_vars = set(ch for ch in template if ch.isupper() and ch.isalpha())
    if not template_vars:
        return issues

    flat = _flatten_conditions(conditions)
    rule_vars = set()
    for c in flat:
        f = c.get("field", "")
        if f.isalpha() and len(f) == 1:
            rule_vars.add(f)
    for v in sorted(rule_vars):
        if v not in template_vars:
            issues.append({
                "stage": "variable", "type": "missing_in_template", "severity": "fail",
                "detail": f"Variable '{v}' used in rules but not found in template '{template}'"
            })

    return issues


def _flatten_conditions(conditions: list[dict]) -> list[dict]:
    flat = []
    for c in conditions:
        t = c.get("type")
        if t in ("and", "or", "not"):
            flat.extend(_flatten_conditions(c.get("children", [])))
        else:
            flat.append(c)
    return flat


BATCH_SYSTEM_PROMPT = """You are a validator for a phone number formatting rule engine.
Each cell contains a template pattern and optional rules using single-letter variables (A-Z) representing digit positions.
The rules use operators: = (equals), # (not-equals), >=, <=, >, <.
Multiple values are comma-separated: A=1,2,3.
Conditions combine with "and" / "or" / "not".
Conditions can use chain operators and mix variables and integers.

You will receive MULTIPLE cells in a single message. Check EACH cell independently.

For each cell, check:
1. LOGICAL CONTRADICTIONS — impossible conditions like A=1 and A#1, A>5 and A<3, A=1 and A=2, A#1,2 where A is a single digit.

2. AMBIGUOUS / QUIRKY SYNTAX — things the parser might misinterpret:
   - Number in values outside 0-9 (e.g., A=12)
   - Unusual characters in the template (dots, underscores, etc.) mixed with uppercase variable letters
   - Potentially unintended chain patterns
   - Trailing/missing commas or spaces

Respond ONLY with a JSON object. Keys are cell indices (as strings: "0", "1", "2"...).
Values are arrays of issues for that cell, or [] if none.

Each issue: {"type": "contradiction"|"quirky_syntax", "severity": "warn"|"fail", "detail": "..."}

Example: {"0": [{"type": "contradiction", "severity": "fail", "detail": "A=1 and A#1 is impossible"}], "1": [], "2": [...]}
Do NOT include any text outside the JSON object."""


def _strip_markdown_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        start = raw.find("\n")
        if start != -1:
            raw = raw[start + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
        elif raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    return raw


def _call_llm(prompt: str, model: str, api_key: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    try:
        resp = requests.post(API_BASE, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content
    except Exception:
        return None


LLM_ERROR_DIR = Path("llm_errors")


def _save_llm_error(raw: str, batch: list[dict]):
    LLM_ERROR_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = LLM_ERROR_DIR / f"error_{ts}.json"
    payload = {
        "timestamp": ts,
        "raw_response": raw,
        "batch_cells": [
            {
                "cell": b["cell"],
                "template": b["template"],
                "requirements": b["requirements"],
            }
            for b in batch
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"    LLM error saved to {path}")


def llm_check_batch(batch: list[dict], model: str, api_key: str) -> list[list[dict]]:
    lines = []
    for i, entry in enumerate(batch):
        flat = _flatten_conditions(entry["conditions"])
        lines.append(f"[{i}]")
        lines.append(f'  Cell value: {entry["cell"]}')
        lines.append(f'  Template: {entry["template"]}')
        lines.append(f'  Requirements: {entry["requirements"]}')
        lines.append(f"  Parsed conditions: {json.dumps(flat, indent=2)}")

    prompt = "Cells to validate:\n\n" + "\n".join(lines)

    def try_parse(text: str) -> dict | None:
        cleaned = _strip_markdown_json(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(cleaned)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _is_safety_response(text: str) -> bool:
        t = text.strip().lower()
        return not t.startswith("{") and not t.startswith("[") and ("safety" in t or "safe" in t or "content" in t)

    max_attempts = 3
    parsed = None
    for attempt in range(max_attempts):
        raw = _call_llm(prompt, model, api_key)
        if raw is None:
            if attempt == max_attempts - 1:
                return [[{"stage": "llm", "type": "api_error", "severity": "warn", "detail": "LLM API call failed"}] for _ in batch]
            print("    API error, retrying...")
            time.sleep(2)
            continue

        parsed = try_parse(raw)
        if parsed is not None:
            break

        is_safety = _is_safety_response(raw)
        if is_safety:
            _save_llm_error(raw, batch)
        if attempt < max_attempts - 1:
            print(f"    {'Safety filter' if is_safety else 'Parse'} error, retrying ({attempt + 2}/{max_attempts})...")
            time.sleep(3 if is_safety else 1)

    if parsed is None:
        _save_llm_error(raw, batch)
        return [[{"stage": "llm", "type": "parse_error", "severity": "warn", "detail": f"LLM returned unparseable: {raw[:200]}"}] for _ in batch]

    results = []
    for i in range(len(batch)):
        cell_issues = parsed.get(str(i), [])
        if isinstance(cell_issues, list):
            for issue in cell_issues:
                issue["stage"] = "llm"
            results.append(cell_issues)
        else:
            results.append([])
    return results


def _status(issues: list[dict]) -> str:
    if any(i.get("severity") == "fail" for i in issues):
        return "FAIL"
    if issues:
        return "WARN"
    return "PASS"


def _print_table(results: list[dict]):
    header = f"{'Row':>6} | {'Status':6} | {'Template':30} | Issues"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for r in results:
        issues_str = "; ".join(f"[{i['type']}] {i['detail'][:60]}" for i in r["issues"])
        tmpl = (r.get("template") or "")[:30]
        print(f"{r['row']:>6} | {r['status']:6} | {tmpl:30} | {issues_str}")
    print(sep)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Total: {len(results)} | PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count}")


def _write_json(results: list[dict], path: str):
    report = {
        "metadata": {
            "model": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
            "total_rows": len(results),
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": {
            "pass": sum(1 for r in results if r["status"] == "PASS"),
            "warn": sum(1 for r in results if r["status"] == "WARN"),
            "fail": sum(1 for r in results if r["status"] == "FAIL"),
        },
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Validate cell formats and LLM-check parser compatibility.")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit rows to process")
    parser.add_argument("--index", type=int, default=None, help="Start processing from this row number")
    parser.add_argument("--model", default=None, help="OpenRouter model (default: OPENROUTER_MODEL env or openrouter/free)")
    parser.add_argument("--output", default="validation_report.json", help="JSON output path")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)

    model = args.model or os.getenv("OPENROUTER_MODEL", "openrouter/free")

    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb[SHEET_NAME]

    results = []
    total_rows = ws.max_row
    start_row = args.index or 2
    end_row = total_rows if args.max_rows is None else min(start_row + args.max_rows - 1, total_rows)

    pending = []
    pending_cell_idx = []

    def flush_batch():
        if not pending:
            return
        batch_results = llm_check_batch(pending, model, api_key)
        for idx, extra_issues in zip(pending_cell_idx, batch_results):
            results[idx]["issues"].extend(extra_issues)
            results[idx]["status"] = _status(results[idx]["issues"])
            r = results[idx]
            print(f"  Row {r['row']:4d} | {r['status']:6s} | issues: {len(r['issues'])}")
        pending.clear()
        pending_cell_idx.clear()
        time.sleep(BATCH_DELAY)

    for row_idx in range(start_row, end_row + 1):
        cell_value = ws.cell(row=row_idx, column=2).value
        if cell_value is None:
            continue

        cell_value = str(cell_value).strip()
        if not cell_value:
            continue

        issues = []

        parsed = parse_dinh_dang(cell_value)
        issues.extend(check_format(cell_value, parsed))

        requirements = parsed.get("requirements")
        conditions = []
        if requirements:
            conditions = parse(requirements)
            issues.extend(check_parse(requirements, conditions))
            issues.extend(check_variables(parsed.get("number", ""), conditions))

        result = {
            "row": row_idx,
            "cell": cell_value,
            "template": parsed.get("number", ""),
            "requirements": requirements,
            "status": _status(issues),
            "issues": issues,
        }
        idx = len(results)
        results.append(result)

        if requirements:
            pending.append({
                "cell": cell_value,
                "template": parsed.get("number", ""),
                "requirements": requirements,
                "conditions": conditions,
            })
            pending_cell_idx.append(idx)

            if len(pending) >= BATCH_SIZE:
                flush_batch()
        else:
            print(f"  Row {row_idx:4d} | {result['status']:6s} | (no rules)")

    if pending:
        flush_batch()

    wb.close()

    print()
    _print_table(results)
    _write_json(results, args.output)
    print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
