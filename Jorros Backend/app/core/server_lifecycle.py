"""Local process control for draining live responses before stopping the API.

This state is never exposed through an HTTP management endpoint. The launcher
controls its own child process through a private stdin pipe.
"""
from threading import Event

_draining = Event()


def drain_streams():
    _draining.set()


def resume_streams():
    _draining.clear()


def streams_draining():
    return _draining.is_set()
