import logging
import sys

openhens_log = logging.getLogger("openhens_logger")
openhens_log.propagate = False
openhens_log.setLevel(logging.INFO)

# Fallback handler ensures something is always visible
if not openhens_log.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    openhens_log.addHandler(handler)

def add_handler(handler: logging.Handler, level: int | None = None) -> None:
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    if level is not None:
        handler.setLevel(level)
    else:
        handler.setLevel(logging.INFO)
    openhens_log.addHandler(handler)

