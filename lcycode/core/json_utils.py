"""Best-effort extraction of a JSON object/array from model output that
may be wrapped in prose or markdown fences."""
import json


def extract_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start_candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not start_candidates:
        raise ValueError("no JSON found in model output")
    start = min(start_candidates)
    for end in range(len(text), start, -1):
        chunk = text[start:end]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    raise ValueError("could not parse JSON from model output")
