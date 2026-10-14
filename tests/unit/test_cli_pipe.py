"""Zavřená roura (`… | head -1`) nesmí přerušit příkaz ani zapsat do deníku běhů CHYBU (2026-10-13, 2026-10-14)."""

import io

from stockradar import cli


class _Broken(io.StringIO):
    def __init__(self, ok: int):
        super().__init__()
        self.ok = ok

    def write(self, text):
        if self.ok <= 0:
            raise BrokenPipeError(32, "Broken pipe")
        self.ok -= 1
        return super().write(text)

    def fileno(self):
        raise io.UnsupportedOperation("bez deskriptoru")


def test_output_after_closed_pipe_is_dropped_and_command_continues():
    inner = _Broken(ok=1)
    out = cli.QuietPipe(inner)
    out.write("první řádek\n")
    assert out.write("druhý řádek\n") == len("druhý řádek\n") and out.broken     # žádná výjimka
    out.write("třetí\n")
    out.flush()
    assert inner.getvalue() == "první řádek\n"
    assert out.getvalue() == "první řádek\n"                                       # ostatní atributy z původního výstupu


def test_main_installs_the_guard_once(monkeypatch):
    monkeypatch.setattr(cli, "build_parser", lambda: (_ for _ in ()).throw(SystemExit(0)))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    try:
        cli.main([])
    except SystemExit:
        pass
    import sys
    assert isinstance(sys.stdout, cli.QuietPipe)
    first = sys.stdout
    try:
        cli.main([])
    except SystemExit:
        pass
    assert sys.stdout is first
