"""Reproducciones aisladas de auditoría; no utiliza la BD ni las claves reales."""
import base64
import json
import logging
from pathlib import Path
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.context import AppContext
from app.models import Person, AttendanceEvent
from app.services import attendance
from sqlalchemy import select
from tests.conftest import make_settings, FakeClock, jpeg
from tests.test_kiosk_session import add_person, new_session, run_until, finish_challenge


def main():
    results = {}
    with tempfile.TemporaryDirectory(prefix='biometria_audit_') as tmp:
        ctx = AppContext(make_settings(Path(tmp)))
        try:
            add_person(ctx, 'AUDITA', 1)
            bid = add_person(ctx, 'AUDITB', 2)
            clock = FakeClock()
            session = new_session(ctx, clock)
            session.handle_frame(jpeg(1))
            # Freeze quality ranking only: keep the first captured image, then let
            # the real identity/consensus and active challenge code run for B.
            session.best_score = 2.0
            run_until(session, jpeg(2), clock=clock)
            view = finish_challenge(session, 2, clock)
            results['photo_identity'] = {
                'state': view['state'],
                'registered_person': view.get('result', {}).get('person', {}).get('code'),
                'photo_is_previous_person_A': base64.b64decode(view['result']['photo'].split(',')[1]) == jpeg(1),
                'note': 'Ranking de calidad controlado; identidad, votos y reto sin mock.'
            }
            # Start both requests together; delay the read to expose the old race.
            # Do not put a barrier inside the serialized write transaction.
            barrier = threading.Barrier(2)
            original = attendance.last_valid_event
            def synchronized_read(db, pid):
                last = original(db, pid)
                time.sleep(0.15)
                return last
            clock.advance(180)
            def register():
                barrier.wait(timeout=10)
                with ctx.session() as db:
                    person = db.get(Person, bid)
                    reg = attendance.register_event(
                        db, person=person, method='ROSTRO', now=clock(), tz=ctx.tz,
                        data_path=ctx.data_path, max_shift_hours=16, debounce_seconds=120,
                        photo=None, liveness='SUPERADA'
                    )
                    return {'id': reg.event.id, 'type': reg.event.event_type}
            with patch.object(attendance, 'last_valid_event', synchronized_read):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(register) for _ in range(2)]
                    attempts = []
                    for f in futures:
                        try:
                            attempts.append(f.result())
                        except Exception as exc:
                            attempts.append({'error': type(exc).__name__})
            results['concurrent_registration'] = attempts
            with ctx.session() as db:
                results['events_at_same_time'] = len(list(db.scalars(select(AttendanceEvent).where(AttendanceEvent.ts == clock()))))
            assert not results['photo_identity']['photo_is_previous_person_A'], results
            assert results['events_at_same_time'] == 1, results
            assert sum(a.get('error') == 'AlreadyRegistered' for a in attempts) == 1, results
        finally:
            ctx.close()
            logging.shutdown()
    print(json.dumps(results, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
