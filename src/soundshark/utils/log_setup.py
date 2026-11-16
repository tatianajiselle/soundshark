import logging
import sys

import structlog


def configure_logging(*, verbose: bool = False, json_output: bool = False) -> None:
    renderer: structlog.typing.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
        exception_formatter: list[structlog.typing.Processor] = [structlog.processors.dict_tracebacks]
    else:
        renderer = structlog.dev.ConsoleRenderer(sort_keys=False)
        exception_formatter = []
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            *exception_formatter,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG if verbose else logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
