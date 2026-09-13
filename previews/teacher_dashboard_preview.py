"""Run an isolated teacher dashboard with generated classroom progress.

    python3 previews/teacher_dashboard_preview.py 3198

All seats, credentials and the database are temporary. The varied towns are
preview fixtures, not a gameplay/balance simulation. Add ?teacher=0 to teach.html
to inspect the dashboard without a saved teacher login.
"""
from __future__ import annotations

import argparse
import json
import secrets
import tempfile
import time
from pathlib import Path

from preview_support import A, preview_handler, serve, solo_seat

E = A.economy


def classroom(db_path, count):
    solo_seat(db_path, 'TEACHER PREVIEW')
    teacher = A.create_session({'class_size': max(30, count)})
    teacher['label'] = 'TEACHER PREVIEW'
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET label=?, paused=1 WHERE code=?',
                     (teacher['label'], teacher['code']))
    seats = [A.join({'code': teacher['code'], 'name': 'STUDENT %02d' % (index + 1),
                     'pin': '%04d' % secrets.randbelow(10000)}) for index in range(count)]
    cfg = E.load_config()
    end = 3 * E.ticks_per_day(cfg)
    start = end - 80
    states = []
    for index in range(count):
        stage = index % 6
        st = E.new_state(cfg, start, seed=index + 19)
        # Seed distinct valid v4 towns, then let the engine earn actual receipts.
        tiers = list(range(1 + stage % 4))
        st['tierOf'] = tiers
        st['b'] = [E._building(tier, 1 + stage, 1 + stage // 2) for tier in tiers]
        st['cash'] = index * 83
        st['book'] = stage * 620
        st['unlock'] = {str(slot): 0 for slot in range(len(tiers))}
        st['cStats']['done'] = index * 2
        st['checklist'].update(lv25=stage >= 3, auto=stage >= 2, quiz=stage >= 3)
        st['regularDeliveries'] = min(3, stage)
        E.migrate_state(cfg, st)
        if stage >= 2:
            result = E.manage_customer_contract(cfg, st, 0, 'accept', customer_id='corner_grocer')
            assert result['ok'], result
        if stage in (0, 5):
            st['b'][0]['reserve'] = True
        states.append(st)
    world = E.new_class(cfg, end)
    E.advance_class(cfg, world, states, start, end)
    with A.connect() as conn:
        now = time.time()
        conn.execute('UPDATE sessions SET clock_base=?,clock_accum=?,started_at=? WHERE code=?',
                     (now, end * cfg['global']['tick'], now - end * cfg['global']['tick'], teacher['code']))
        session = A._session_of(conn, teacher['code'])
        rows = list(conn.execute('SELECT id FROM players WHERE code=? ORDER BY id', (teacher['code'],)))
        for row, st in zip(rows, states):
            A._save_state(conn, row['id'], cfg, st)
        A._save_world(conn, session, world)
    return teacher, seats[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', nargs='?', type=int, default=3198)
    parser.add_argument('--students', type=int, default=24)
    args = parser.parse_args()
    if not 1 <= args.students <= 200:
        parser.error('students must be between 1 and 200')
    with tempfile.TemporaryDirectory(prefix='yomama-teacher-preview-') as directory:
        teacher, seat = classroom(Path(directory) / 'preview.db', args.students)
        teacher_json = json.dumps(json.dumps(teacher))

        def rewrite(name, html):
            script = ('<script>/* temporary teacher preview */(function(){'
                      'if(new URLSearchParams(location.search).get("teacher")==="0")'
                      '{localStorage.removeItem("yomama_teacher_v1");}'
                      'else{localStorage.setItem("yomama_teacher_v1",' + teacher_json + ');}'
                      '})();</script>')
            return html.replace('<head>', '<head>' + script, 1)

        handler = preview_handler(seat['token'], name=seat['name'], code=seat['code'], rewrite=rewrite)
        serve(args.port, handler, first_page='teach.html')


if __name__ == '__main__':
    main()
