from pathlib import Path

BASELINE_REPOSITORY = "https://github.com/dunnolab/nethack-bot.git"
BASELINE_COMMIT = "fe3c9a21679d79c1a696987d90c4a6fe87f7c124"
GIGAEVO_REPOSITORY = "https://github.com/AIRI-Institute/gigaevo-core.git"
GIGAEVO_COMMIT = "9b8687ebaf1708962370ea82b4cf2480d74874e5"

CANDIDATE_SCHEMA = "nethacker.candidate/v1"
EVALUATION_SCHEMA = "nethacker.evaluation/v1"
SUBMISSION_SCHEMA = "nethacker.submission/v1"
GITHUB_SOURCE_SCHEMA = "nethacker.github-source/v1"

LATEST_OPENAI_MODEL = "gpt-5.6-sol"
DEFAULT_BRIDGE_PORT = 8765
DEFAULT_HUB_PORT = 8766

MAX_PATCH_BYTES = 256 * 1024
MAX_PATCH_FILES = 32
MAX_REQUEST_BYTES = 1024 * 1024
MAX_SHARED_ANCESTORS = 16
AUTOASCEND_STEP_TIMEOUT_SECONDS = 5.0


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_baseline_path() -> Path:
    return repository_root() / "baseline" / "nethack-bot"


def default_gigaevo_path() -> Path:
    return repository_root() / "vendor" / "gigaevo-core"


def default_problem_path() -> Path:
    return repository_root() / "problems" / "nethack_symbolic"
