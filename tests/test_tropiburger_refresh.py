import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import Settings
from app.database import Base
from app.tropiburger_refresh import BASE, PLATFORMS, TropiburgerSnapshot, load_data, refresh_data
from app.windsor import WindsorError

class FakeClient:
    def __init__(self, failed=()): self.failed = failed
    def fetch_connector(self, connector, fields, start, end, filters=None):
        platform = next(p for p, v in PLATFORMS.items() if v[0] == connector)
        if platform in self.failed: raise WindsorError('sin conexión')
        if platform in ('DV360', 'GOOGLE'): return []
        account = PLATFORMS[platform][1]
        row = {'account_id': account, 'date': '2026-11-10', 'campaign': 'CAMPAÑA TEST', 'spend': 12.34, 'impressions': 100}
        for index, field in enumerate(PLATFORMS[platform][2]): row[field] = 10 + index
        return [row]

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db: yield db

def test_refresh_updates_metrics_and_preserves_history_and_static_data(db):
    before = load_data(db)
    payload, failures = refresh_data(db, Settings(), client=FakeClient(), today=date(2026, 11, 11))
    assert failures == []
    assert payload['reach'] == before['reach'] and payload['ads'] == before['ads']
    index = payload['snap']['camps'].index(['META', 'CAMPAÑA TEST', None])
    assert [index, (date(2026, 11, 10)-BASE).days, 1234, 100, 10, 11, 12] in payload['snap']['rows']
    assert payload['platformThrough']['META'] == '2026-11-10'
    assert payload['platformThrough']['GOOGLE'] == '2026-04-16'
    assert any(row[1] < (date(2026, 10, 12)-BASE).days for row in payload['snap']['rows'])
    assert db.query(TropiburgerSnapshot).count() == 1

def test_partial_failure_preserves_previous_platform_data(db):
    before = load_data(db)
    payload, failures = refresh_data(db, Settings(), client=FakeClient(failed=('META',)), today=date(2026, 11, 11))
    assert failures == ['META']
    def platform_rows(data, platform):
        return [r for r in data['snap']['rows'] if data['snap']['camps'][r[0]][0] == platform]
    assert platform_rows(payload, 'META') == platform_rows(before, 'META')
    assert payload['platformThrough']['META'] == '2026-11-09'

def test_complete_failure_does_not_replace_snapshot(db):
    with pytest.raises(WindsorError):
        refresh_data(db, Settings(), client=FakeClient(failed=PLATFORMS), today=date(2026, 11, 11))
    assert db.query(TropiburgerSnapshot).count() == 0

def test_wrong_account_is_rejected_without_overwriting_it(db):
    class Wrong(FakeClient):
        def fetch_connector(self, connector, *args, **kwargs):
            result = super().fetch_connector(connector, *args, **kwargs)
            if connector == 'facebook' and result: result[0]['account_id'] = 'other'
            return result
    before = load_data(db)
    payload, failures = refresh_data(db, Settings(), client=Wrong(), today=date(2026, 11, 11))
    assert 'META' in failures
    assert [r for r in payload['snap']['rows'] if payload['snap']['camps'][r[0]][0] == 'META'] == [r for r in before['snap']['rows'] if before['snap']['camps'][r[0]][0] == 'META']
