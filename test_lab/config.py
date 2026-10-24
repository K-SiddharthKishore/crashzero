from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestLabConfig:
    root: Path
    data_dir: Path
    db_path: Path
    uploads_dir: Path
    evidence_dir: Path
    model_path: Path

    @classmethod
    def load(cls, root=None, data_dir=None):
        project = Path(root or Path(__file__).resolve().parents[1])
        data = Path(data_dir) if data_dir is not None else project / 'outputs' / 'test_lab'
        uploads = data / 'uploads'
        evidence = data / 'evidence'
        for folder in (data, uploads, evidence):
            folder.mkdir(parents=True, exist_ok=True)
        return cls(project, data, data / 'test_history.sqlite3', uploads, evidence,
                   project / 'models' / 'crash_temporal.pt')

