"""Convert a rider's question into inputs for the local GTFS planner."""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_journey(question):
    if not question.strip():
        raise ValueError("Enter a journey question.")
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("Set GROQ_API_KEY in your environment to use --ask.")
    model = os.environ.get("GROQ_MODEL", "").strip() or "openai/gpt-oss-20b"
    today = datetime.now(timezone(timedelta(hours=8))).date()
    instructions = (
        "Extract inputs for a Kuala Lumpur transit journey. Return one JSON object "
        "with keys origin, destination, date, time. Preserve stop names as written. "
        "Use YYYY-MM-DD and 24-hour HH:MM for the earliest departure. "
        f"The local date is {today.isoformat()}. Resolve clear relative dates. "
        "Use null for each missing or ambiguous field. For unsupported requests, "
        "including arrive-by or live arrivals, return all fields as null. "
        "Never supply route advice or infer missing details."
    )
    request = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": question},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise ValueError(f"Groq returned HTTP {error.code}. Check API access for {model}.") from None
    except (URLError, TimeoutError):
        raise ValueError("Could not reach Groq. Try again or use the stop, date and time inputs.") from None
    except ValueError:
        raise ValueError("Groq returned an unreadable response.") from None
    fields = ("origin", "destination", "date", "time")
    try:
        values = json.loads(payload["choices"][0]["message"]["content"])
        if not isinstance(values, dict) or any(
            field not in values or not isinstance(values[field], (str, type(None))) for field in fields
        ):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("Groq did not return valid trip details. Rephrase the request.") from None
    missing = [field for field in fields if not (values[field] or "").strip()]
    if missing:
        raise ValueError("Ask for a departure journey and specify: " + ", ".join(missing) + ".")
    try:
        travel_date = date.fromisoformat(values["date"])
        if travel_date.isoformat() != values["date"] or not re.fullmatch(
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", values["time"]
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Use a clear departure date and time, such as 23 November 2026 at 5 a.m.") from None
    return values["origin"].strip(), values["destination"].strip(), travel_date, values["time"]
