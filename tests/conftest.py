"""모든 테스트 공통 설정."""
import pytest

from src.agent import runner_agent


@pytest.fixture(autouse=True)
def isolate_snapshot_dir(tmp_path_factory, monkeypatch):
    """러너가 만드는 스냅샷(results/raw/<줄기>_final)이 테스트 중에 실제 results/raw를 오염시키지 않게 한다."""
    monkeypatch.setattr(runner_agent, "RAW_DIR", tmp_path_factory.mktemp("raw"))
