"""Numeric voice timing logs without general request logging."""

import uvicorn


def timing_log_config():
    """Enable bounded numeric timings without enabling general request logging."""
    return {
        **uvicorn.config.LOGGING_CONFIG,
        "loggers": {
            **uvicorn.config.LOGGING_CONFIG["loggers"],
            "uvicorn.error.vab_timing": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
