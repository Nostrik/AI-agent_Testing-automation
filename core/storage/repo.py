"""Типовые выборки поверх db."""
import time

from core.storage.db import list_


def project_scenarios(project_id):
    return list_("scenarios", "where project_id=?", (project_id,), order="sid")


def project_runs(project_id):
    return list_("runs", "where project_id=?", (project_id,), order="id desc")


def run_dialogs(run_id):
    return list_("dialogs", "where run_id=?", (run_id,), order="id")


def find_project(name_or_id: str):
    for p in list_("projects"):
        if str(p["id"]) == str(name_or_id) or p["name"] == name_or_id:
            return p
    return None


def now():
    return time.strftime("%Y-%m-%d %H:%M")
