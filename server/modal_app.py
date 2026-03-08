# modal_app.py
"""
Deploy:
    modal deploy modal_app.py

Dev:
    modal serve modal_app.py
"""

from pathlib import Path
import modal

ROOT = Path(__file__).resolve().parent

app = modal.App("tcr-agent-api")

image = (
    modal.Image.debian_slim(python_version="3.11")
    # Uses pyproject.toml + uv.lock from this directory.
    # Does NOT install your project package itself, so we add source below.
    .uv_sync(uv_project_dir=str(ROOT))
    # Include your application code and non-Python files like data/, .env.*, etc.
    .add_local_dir(str(ROOT), remote_path="/root/app")
)

# Recommended: expose env vars at runtime via Secrets, not by relying on copied .env files.
# from_dotenv() searches from the current working directory unless you pass an explicit path.
runtime_secrets = [
    modal.Secret.from_dotenv(str(ROOT), filename=".env"),
    # Uncomment if you also want another env file merged in:
    # modal.Secret.from_dotenv(str(ROOT), filename=".env.production"),
]

@app.function(
    image=image,
    secrets=runtime_secrets,
    timeout=60 * 60,
    scaledown_window=300,
)
@modal.asgi_app()
def fastapi_app():
    import os
    import sys
    from pathlib import Path

    app_root = Path("/root/app")
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    os.chdir(app_root)

    from main import app as fastapi_app

    return fastapi_app