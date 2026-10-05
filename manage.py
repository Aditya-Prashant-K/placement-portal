#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Did you install the requirements "
            "(pip install -r requirements.txt) and activate your virtualenv?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
