#!/usr/bin/env python3
"""List or query Earth Engine batch tasks without modifying them."""

from __future__ import annotations

import argparse
import warnings
from datetime import datetime
from typing import Any

from _gee_common import error_payload, import_ee, initialize_ee, iso_from_millis, print_json


OPERATION_TO_TASK_STATE = {
    "PENDING": "READY",
    "RUNNING": "RUNNING",
    "CANCELLING": "CANCEL_REQUESTED",
    "SUCCEEDED": "COMPLETED",
    "CANCELLED": "CANCELLED",
    "FAILED": "FAILED",
}

EXAMPLES = """examples:
  List the 25 most recent tasks:
    python gee_task_status.py --project YOUR_PROJECT

  List the 10 most recent failed tasks:
    python gee_task_status.py --state FAILED --limit 10 --project YOUR_PROJECT

  Query one task by its short Task ID:
    python gee_task_status.py --task-id 3DNU363IM57LNU4SDTMB6I33 --project YOUR_PROJECT

  Query using a full operation name:
    python gee_task_status.py --task-id projects/YOUR_PROJECT/operations/TASK_ID --project YOUR_PROJECT

This command is read-only. It has no cancellation option and never calls
cancelOperation() or cancelTask(). Cancellation requires a separate, explicit
user request and confirmation of the exact task target.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task-id", help="Return one task by short ID or operation name.")
    parser.add_argument(
        "--state",
        action="append",
        help="Filter recent tasks by state; repeat for multiple states.",
    )
    parser.add_argument(
        "--description-contains",
        help="Case-insensitive description filter for recent tasks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum recent tasks returned (1-500; default: 25).",
    )
    parser.add_argument("--project", help="Google Cloud project used by ee.Initialize().")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be between 1 and 500")
    if args.task_id and (args.state or args.description_contains):
        parser.error("--state and --description-contains cannot be used with --task-id")


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def task_id_from_name(name: Any) -> str | None:
    if not isinstance(name, str) or not name:
        return None
    return name.rstrip("/").rsplit("/", 1)[-1]


def normalized_state(value: Any) -> str:
    state = str(value or "UNKNOWN").upper()
    return OPERATION_TO_TASK_STATE.get(state, state)


def error_message_from(raw: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    direct = first_present(raw.get("error_message"), metadata.get("errorMessage"))
    if direct not in (None, ""):
        return str(direct)
    error = raw.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        return str(message) if message not in (None, "") else None
    if error not in (None, ""):
        return str(error)
    return None


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    operation_name = first_present(raw.get("name"), metadata.get("name"))
    operation_state = first_present(metadata.get("state"), raw.get("operation_state"))
    state = normalized_state(first_present(operation_state, raw.get("state")))
    task_id = first_present(raw.get("id"), task_id_from_name(operation_name))
    error_message = error_message_from(raw, metadata)

    result: dict[str, Any] = {
        "id": task_id,
        "description": first_present(metadata.get("description"), raw.get("description")),
        "state": state,
        "task_type": first_present(metadata.get("type"), raw.get("task_type")),
        "error_message": error_message,
        "failed": state == "FAILED",
    }

    if operation_name is not None:
        result["operation_name"] = operation_name
    if operation_state is not None:
        result["operation_state"] = str(operation_state).upper()

    iso_fields = {
        "createTime": "creation_time_utc",
        "startTime": "start_time_utc",
        "updateTime": "update_time_utc",
        "endTime": "end_time_utc",
    }
    for source_key, output_key in iso_fields.items():
        value = metadata.get(source_key)
        if value is not None:
            result[output_key] = value

    millisecond_fields = {
        "creation_timestamp_ms": "creation_time_utc",
        "start_timestamp_ms": "start_time_utc",
        "update_timestamp_ms": "update_time_utc",
    }
    for source_key, output_key in millisecond_fields.items():
        value = raw.get(source_key)
        if value is not None:
            result[source_key] = value
            result.setdefault(output_key, iso_from_millis(value))

    for output_key, candidates in {
        "attempt": (metadata.get("attempt"), raw.get("attempt")),
        "destination_uris": (
            metadata.get("destinationUris"),
            raw.get("destination_uris"),
        ),
        "priority": (metadata.get("priority"), raw.get("priority")),
        "batch_eecu_usage_seconds": (
            metadata.get("batchEecuUsageSeconds"),
            raw.get("batch_eecu_usage_seconds"),
        ),
    }.items():
        value = first_present(*candidates)
        if value is not None:
            result[output_key] = value

    if result["failed"]:
        reason = error_message or "Earth Engine marked the task FAILED without an error message."
        result["failure"] = {
            "highlight": True,
            "reason": reason,
        }
        result["attention"] = f"FAILED: {reason}"
    return result


def timestamp_sort_value(task: dict[str, Any]) -> float:
    milliseconds = task.get("creation_timestamp_ms")
    if milliseconds is not None:
        try:
            return float(milliseconds) / 1000.0
        except (TypeError, ValueError):
            pass
    value = task.get("creation_time_utc")
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return 0.0


def read_one_task(ee: Any, task_id: str) -> list[dict[str, Any]]:
    if "/operations/" in task_id:
        raw = ee.data.getOperation(task_id)
        return [raw] if isinstance(raw, dict) else []
    # The current getOperation API requires a full operation name. The compatibility
    # method accepts the short alphanumeric Task ID and safely returns UNKNOWN for a
    # missing task. Suppress only its deprecation warning, not runtime failures.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        raw = ee.data.getTaskStatus(task_id)
    return raw if isinstance(raw, list) else [raw]


def failure_summary(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": task.get("id"),
            "description": task.get("description"),
            "error_message": task.get("error_message")
            or "Earth Engine did not provide an error message.",
        }
        for task in tasks
        if task.get("failed")
    ]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    result: dict[str, Any] = {
        "status": "PENDING",
        "ok": False,
        "read_only": True,
        "mutation_performed": False,
        "project": args.project,
        "mode": "task_id" if args.task_id else "recent",
        "query_task_id": args.task_id,
    }

    try:
        ee = import_ee()
        project_selection = initialize_ee(ee, args.project)
        result["project_selection"] = project_selection
        result["project"] = (
            project_selection.get("effective_project")
            or project_selection.get("selected_project")
        )
        if args.task_id:
            raw_tasks = read_one_task(ee, args.task_id)
            source = "getOperation" if "/operations/" in args.task_id else "getTaskStatus"
        else:
            raw_tasks = ee.data.listOperations()
            source = "listOperations"
    except Exception as exc:
        result.update(error_payload("task_status", exc))
        result["status"] = "ERROR"
        print_json(result)
        return 2

    tasks = [normalize(task) for task in raw_tasks if isinstance(task, dict)]
    result["source"] = source

    if args.task_id:
        if not tasks or tasks[0].get("state") == "UNKNOWN":
            result.update(
                {
                    "status": "NOT_FOUND",
                    "task_found": False,
                    "count": 0,
                    "failed_count": 0,
                    "has_failures": False,
                    "failed_tasks": [],
                    "tasks": [],
                    "message": f"Earth Engine Task was not found: {args.task_id}",
                }
            )
            print_json(result)
            return 4
        filtered = tasks[:1]
        result["task_found"] = True
    else:
        tasks.sort(key=timestamp_sort_value, reverse=True)
        allowed_states = {normalized_state(state) for state in args.state or []}
        needle = (args.description_contains or "").casefold()
        filtered = []
        for task in tasks:
            if allowed_states and task.get("state") not in allowed_states:
                continue
            if needle and needle not in str(task.get("description") or "").casefold():
                continue
            filtered.append(task)
            if len(filtered) >= args.limit:
                break
        result["filters"] = {
            "states": sorted(allowed_states),
            "description_contains": args.description_contains,
            "limit": args.limit,
        }

    failures = failure_summary(filtered)
    result.update(
        {
            "status": "OK",
            "ok": True,
            "count": len(filtered),
            "failed_count": len(failures),
            "has_failures": bool(failures),
            "failed_tasks": failures,
            "tasks": filtered,
        }
    )
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
