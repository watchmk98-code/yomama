"""Access logging preserves useful routing details without query credentials."""
import secrets
from http import HTTPStatus
from urllib.parse import urlencode

import pytest

from server import NewsProxyHandler


def handler_for(method, target):
    # Exercise the real stderr logger without starting a server or touching a DB.
    handler = object.__new__(NewsProxyHandler)
    handler.command = method
    handler.path = target
    handler.request_version = 'HTTP/1.1'
    handler.requestline = method + ' ' + target + ' HTTP/1.1'
    handler.client_address = ('127.0.0.1', 12345)
    handler.log_date_time_string = lambda: 'TEST-TIME'
    return handler


@pytest.mark.parametrize('method', ['GET', 'POST', 'HEAD', 'OPTIONS'])
def test_access_log_removes_all_query_credentials_but_preserves_request_details(capsys, method):
    private = {key: secrets.token_hex(16) for key in ('token', 'teacher_token', 'code', 'pin')}
    target = '/api/game/port?' + urlencode(private)
    handler = handler_for(method, target)
    handler.log_request(HTTPStatus.OK, 321)
    output = capsys.readouterr().err
    assert '"%s /api/game/port HTTP/1.1" 200 321' % method in output
    assert '?' not in output
    for value in private.values():
        assert value not in output
    # Redaction affects logs only; dispatch still receives the original URL.
    assert handler.path == target
    assert handler.requestline == method + ' ' + target + ' HTTP/1.1'


def test_absolute_request_target_logs_only_its_path(capsys):
    private = secrets.token_hex(16)
    target = 'https://' + private + '@example.invalid/api/game/teacher?teacher_token=' + private + '#' + private
    handler_for('POST', target).log_request(403, 0)
    output = capsys.readouterr().err
    assert '"POST /api/game/teacher HTTP/1.1" 403 0' in output
    assert private not in output and 'example.invalid' not in output


def test_access_log_handles_malformed_target_without_echoing_query_values(capsys):
    private = secrets.token_hex(16)
    handler_for('GET', 'http://[invalid?token=' + private).log_request(400)
    output = capsys.readouterr().err
    assert '"GET [invalid path] HTTP/1.1" 400 -' in output
    assert private not in output


def test_query_free_path_and_default_status_size_remain_logged(capsys):
    handler_for('GET', '/join.html').log_request()
    assert '"GET /join.html HTTP/1.1" - -' in capsys.readouterr().err
