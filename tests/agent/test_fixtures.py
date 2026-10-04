"""H12: tools.check_fixtures loads every fixture file the engines read.

Each test breaks a temp copy of the incident folder; the real data/incidents is never written.
"""

import shutil
from pathlib import Path

import pytest

from agent import tools
from data import loader

INCIDENT = "INC-2041"
REQUIRED = ["incident.json", "events.json", "metrics.json", "system_model.json"]
TELEMETRY = ["deploys.json", "config.json", "logs.json", "traces.json"]


@pytest.fixture
def folder(monkeypatch, tmp_path) -> Path:
    """A writable copy of the real incident fixtures, swapped in for data/incidents."""
    name = loader._incident_dirs()[INCIDENT].name
    shutil.copytree(loader.INCIDENTS_DIR, tmp_path / "incidents")
    monkeypatch.setattr(loader, "INCIDENTS_DIR", tmp_path / "incidents")
    loader._incident_dirs.cache_clear()
    yield tmp_path / "incidents" / name
    loader._incident_dirs.cache_clear()  # monkeypatch then restores the real dir; the next call re-reads it


def test_real_fixtures_pass():
    assert tools.check_fixtures(INCIDENT) is None


def test_checks_every_file_the_engines_read():
    assert [name for name, _, _ in tools._FIXTURES] == REQUIRED + TELEMETRY
    assert "ground_truth.json" not in {name for name, _, _ in tools._FIXTURES}  # tests only, never the agent


@pytest.mark.parametrize("name", REQUIRED[1:])  # incident.json is how the incident is found at all; see below
def test_missing_required_file_fails_and_names_it(folder, name):
    (folder / name).unlink()
    with pytest.raises(tools.FixtureError, match=rf"^{INCIDENT} {name}: FileNotFoundError"):
        tools.check_fixtures(INCIDENT)


def test_missing_incident_file_makes_the_incident_unknown(folder):
    (folder / "incident.json").unlink()
    with pytest.raises(tools.FixtureError, match=rf"^{INCIDENT} incident.json: KeyError"):
        tools.check_fixtures(INCIDENT)


@pytest.mark.parametrize("name", REQUIRED + TELEMETRY)
def test_corrupt_file_fails_and_names_it(folder, name):
    (folder / name).write_text("{not json", encoding="utf-8")
    with pytest.raises(tools.FixtureError, match=rf"^{INCIDENT} {name}: JSONDecodeError"):
        tools.check_fixtures(INCIDENT)


def test_required_file_that_breaks_the_contract_fails(folder):
    (folder / "events.json").write_text('[{"id": "E-001"}]', encoding="utf-8")  # valid JSON, not an Event
    with pytest.raises(tools.FixtureError, match=rf"^{INCIDENT} events.json: ValidationError"):
        tools.check_fixtures(INCIDENT)


@pytest.mark.parametrize("name, wrong", [("deploys.json", "{}"), ("config.json", "[]"), ("logs.json", "{}"),
                                         ("traces.json", '"traces"')])
def test_telemetry_with_the_wrong_shape_fails(folder, name, wrong):
    (folder / name).write_text(wrong, encoding="utf-8")
    with pytest.raises(tools.FixtureError, match=rf"^{INCIDENT} {name}: expected a JSON (list|dict), got"):
        tools.check_fixtures(INCIDENT)


@pytest.mark.parametrize("name", TELEMETRY)
def test_missing_telemetry_is_allowed_by_the_loader_design(folder, name):
    (folder / name).unlink()  # the loader returns empty data for an incident without this file
    assert tools.check_fixtures(INCIDENT) is None
