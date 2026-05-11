"""
Study framework: TaskWidget for managing task lifecycle, event logging,
and tampering-detection snapshots.
"""

import time
import json
import os
import hashlib
from datetime import datetime
from IPython.display import display, HTML
import ipywidgets as widgets

EVENTS_FILE = "events.json"
SNAPSHOTS_FILE = "snapshots.json"
EVENT_LOG = []
SNAPSHOTS = {}


def _save_log():
    try:
        with open(EVENTS_FILE, "w") as f:
            json.dump(EVENT_LOG, f, indent=2)
    except Exception as e:
        print(f"Could not save event log: {e}")


def _load_log():
    global EVENT_LOG
    if os.path.exists(EVENTS_FILE):
        try:
            with open(EVENTS_FILE) as f:
                EVENT_LOG = json.load(f)
            return True
        except Exception as e:
            print(f"Could not read event log: {e}")
    return False


def _save_snapshots():
    try:
        with open(SNAPSHOTS_FILE, "w") as f:
            json.dump(SNAPSHOTS, f, indent=2)
    except Exception as e:
        print(f"Could not save snapshots: {e}")


def _load_snapshots():
    global SNAPSHOTS
    if os.path.exists(SNAPSHOTS_FILE):
        try:
            with open(SNAPSHOTS_FILE) as f:
                SNAPSHOTS = json.load(f)
            return True
        except Exception as e:
            print(f"Could not load snapshots: {e}")
    return False


def clear_log():
    global EVENT_LOG, SNAPSHOTS
    EVENT_LOG = []
    SNAPSHOTS = {}
    for path in [EVENTS_FILE, SNAPSHOTS_FILE]:
        if os.path.exists(path):
            os.remove(path)
    print("Event log and snapshots cleared.")


def _log_raw_event(task_id, event_type):
    EVENT_LOG.append({
        "task_id": task_id,
        "event": event_type,
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "epoch_seconds": time.time()
    })
    _save_log()


def snapshot_task(task_id, cell_contents):
    SNAPSHOTS[task_id] = [
        {
            "cell_index": i,
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            "content_preview": content[:200],
            "char_count": len(content)
        }
        for i, content in enumerate(cell_contents)
    ]
    _save_snapshots()


def check_tampering(task_id, current_cell_contents):
    if task_id not in SNAPSHOTS:
        return {"error": f"No snapshot found for task {task_id}"}
    snapshot = SNAPSHOTS[task_id]
    if len(current_cell_contents) != len(snapshot):
        return {"error": f"Cell count mismatch: snapshot has {len(snapshot)}, got {len(current_cell_contents)}"}
    tampered = []
    for i, (current, snap) in enumerate(zip(current_cell_contents, snapshot)):
        current_hash = hashlib.sha256(current.encode()).hexdigest()
        if current_hash != snap["content_hash"]:
            tampered.append({
                "cell_index": i,
                "snapshot_preview": snap["content_preview"],
                "current_preview": current[:200],
                "snapshot_chars": snap["char_count"],
                "current_chars": len(current)
            })
    return {"task_id": task_id, "tampered_cells": tampered, "ok": len(tampered) == 0}


def show_event_log():
    print(json.dumps(EVENT_LOG, indent=2))


class TaskWidget:
    def __init__(self, task_id, on_submit=None):
        self.task_id = task_id
        self.on_submit_callback = on_submit
        self.started = False
        self.submitted = False
        self.start_time = None
        self.submit_time = None

        prior_events = [e for e in EVENT_LOG if e["task_id"] == task_id]
        prior_start = next((e for e in prior_events if e["event"] == "start"), None)
        prior_submit = next((e for e in prior_events if e["event"] == "submit"), None)

        if prior_submit:
            self.started = True
            self.submitted = True
            self.start_time = prior_start["epoch_seconds"] if prior_start else None
            self.submit_time = prior_submit["epoch_seconds"]
        elif prior_start:
            self.started = True
            self.start_time = prior_start["epoch_seconds"]

        self.status_label = widgets.HTML(value="")
        self.start_button = widgets.Button(
            description=f"Start Task {self.task_id}",
            button_style='success',
            layout=widgets.Layout(width='200px')
        )
        self.submit_button = widgets.Button(
            description=f"Submit Task {self.task_id}",
            button_style='warning',
            layout=widgets.Layout(width='200px')
        )
        self.confirm_box = widgets.HTML(value="")

        self.start_button.on_click(self._on_start)
        self.submit_button.on_click(self._on_submit_click)

        self.container = widgets.VBox([
            self.status_label,
            widgets.HBox([self.start_button, self.submit_button]),
            self.confirm_box
        ])

        self._refresh_ui()

    def _refresh_ui(self):
        if self.submitted:
            elapsed = (self.submit_time - self.start_time) if self.start_time else 0
            self.status_label.value = (
                f"<b>Task {self.task_id}</b> — submitted "
                f"({elapsed:.1f} seconds elapsed) ✓"
            )
            self.start_button.disabled = True
            self.start_button.button_style = ''
            self.submit_button.disabled = True
            self.submit_button.button_style = ''
            self.confirm_box.value = (
                f"<div style='padding:14px; border:3px solid #d9534f; "
                f"background:#fff3f3; margin-top:10px; border-radius:4px;'>"
                f"<div style='font-size:16px; font-weight:bold; color:#d9534f; margin-bottom:6px;'>"
                f"��� Task {self.task_id} has been submitted and is now locked."
                f"</div>"
                f"<div style='color:#333; font-size:14px;'>"
                f"<b>Do not edit any cells in this task above.</b> "
                f"Editing cells after submission may invalidate your participation in the study. "
                f"Please scroll down and continue with the next task."
                f"</div>"
                f"</div>"
            )
        elif self.started:
            self.status_label.value = (
                f"<b>Task {self.task_id}</b> — in progress "
                f"(started at {datetime.fromtimestamp(self.start_time).strftime('%H:%M:%S')})"
            )
            self.start_button.disabled = True
            self.start_button.button_style = ''
            self.submit_button.disabled = False
        else:
            self.status_label.value = (
                f"<b>Task {self.task_id}</b> — not started"
            )
            self.start_button.disabled = False
            self.submit_button.disabled = True

    def _log_event(self, event_type):
        _log_raw_event(self.task_id, event_type)

    def _on_start(self, b):
        if self.started:
            return
        self.started = True
        self.start_time = time.time()
        self._log_event("start")
        self._refresh_ui()

    def _on_submit_click(self, b):
        if self.submitted:
            return
        self.confirm_box.value = (
            f"<div style='padding:10px; border:2px solid #d9534f; "
            f"background:#fff3f3; margin-top:10px;'>"
            f"<b>Confirm submission for Task {self.task_id}?</b><br>"
            f"This will lock your work for this task. You cannot return to it."
            f"After submission, remember to copy and submit your LLM chat transcript for this task."
            f"</div>"
        )
        confirm_yes = widgets.Button(description="Yes, submit and lock",
                                     button_style='danger')
        confirm_no = widgets.Button(description="Cancel",
                                    button_style='')
        confirm_row = widgets.HBox([confirm_yes, confirm_no])
        confirm_yes.on_click(lambda _: self._finalize_submit())
        confirm_no.on_click(lambda _: self._cancel_submit())
        self.container.children = list(self.container.children) + [confirm_row]

    def _cancel_submit(self):
        self.confirm_box.value = ""
        self.container.children = self.container.children[:3]

    def _finalize_submit(self):
        self.submitted = True
        self.submit_time = time.time()
        self._log_event("submit")
        self.container.children = self.container.children[:3]
        self._refresh_ui()
        if self.on_submit_callback:
            self.on_submit_callback(self.task_id)

    def display(self):
        display(self.container)


def initialize_framework():
    """Call this once at notebook start. Loads any prior state from disk."""
    restored = _load_log()
    _load_snapshots()
    if restored:
        print(f"Restored {len(EVENT_LOG)} previous events from disk.")
        task_ids = set(e["task_id"] for e in EVENT_LOG)
        for tid in task_ids:
            events = [e for e in EVENT_LOG if e["task_id"] == tid]
            has_start = any(e["event"] == "start" for e in events)
            has_submit = any(e["event"] == "submit" for e in events)
            if has_start and not has_submit:
                _log_raw_event(tid, "kernel_resumed")
                print(f"  Detected in-progress Task {tid}; logged kernel_resumed event.")
    else:
        print("Starting with empty event log.")
    print("Framework loaded.")
