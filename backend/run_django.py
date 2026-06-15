"""Entry point for PyInstaller-packaged Django backend."""
import os
import sys
import socket
from pathlib import Path

os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def main():
    print("LitRadar backend starting...", flush=True)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "litradar.settings")

    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:
        app_dir = Path.home() / ".litradar"
        app_dir.mkdir(parents=True, exist_ok=True)
        db_path = app_dir / "db.sqlite3"
        os.environ["LITRADAR_DB_PATH"] = str(db_path)
        port = 18765
    else:
        port = 8765

    import django
    django.setup()
    print(f"Django ready, port={port}", flush=True)

    # Only run migrations if DB doesn't exist yet (first launch)
    db_path = os.environ.get("LITRADAR_DB_PATH", "")
    if db_path and not Path(db_path).exists():
        print("First launch, running migrations...", flush=True)
        from django.core.management import call_command
        call_command("migrate", "--run-syncdb", verbosity=0, interactive=False)

    from django.core.management import execute_from_command_line
    sys.argv = [sys.argv[0], "runserver", f"127.0.0.1:{port}", "--noreload", "--nothreading"]
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
