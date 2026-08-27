$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000
