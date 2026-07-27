import json
import os

NOTES_PATH = "investigation_notes.json"

def jadx_add_investigation_note(class_name: str, finding: str, suspicious: bool) -> dict:
    notes = _load()
    notes.append({"class": class_name, "finding": finding, "suspicious": suspicious})
    _save(notes)
    return {"status": "success", "note_count": len(notes)}

def jadx_get_investigation_notes() -> dict:
    notes = _load()
    return {"notes": notes, "count": len(notes)}

def _load() -> list:
    if os.path.exists(NOTES_PATH):
        try:
            with open(NOTES_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save(notes: list) -> None:
    with open(NOTES_PATH, "w") as f:
        json.dump(notes, f, indent=2)
