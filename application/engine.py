import json
import os
import subprocess
import tempfile
from pathlib import Path

def get_engine_path():
    env_path = os.environ.get("ENGINE_PATH")
    if env_path:
        return env_path

    docker_path = "/app/engine"
    if Path(docker_path).exists():
        return docker_path

    local_path = Path.cwd() / "engine"
    return str(local_path)

def run_engine_for_request(request_id, photos):
    engine_path = get_engine_path()

    if not Path(engine_path).exists():
        raise FileNotFoundError(f"Engine binary not found at {engine_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        input_path = temp_dir / "input.json"
        output_base = temp_dir / "output"
        output_path = temp_dir / "output.json"

        payload = {
            "id": request_id,
            "content": photos,
        }

        with open(input_path, "w", encoding="utf-8") as file:
            json.dump(payload, file)

        result = subprocess.run([engine_path, "compute", "--input", str(input_path), "--output", str(output_base)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Engine failed with exit code {result.returncode}: {result.stderr}"
            )

        if not output_path.exists():
            raise FileNotFoundError("Engine output file was not created")

        with open(output_path, "r", encoding="utf-8") as file:
            engine_output = json.load(file)

        return engine_output

def validate_engine_output(engine_output):
    if not isinstance(engine_output, dict):
        raise ValueError("Engine output must be a JSON object")

    results = engine_output.get("results")
    if not isinstance(results, dict):
        raise ValueError("Missing results in engine output")

    generations = results.get("generations")
    if not isinstance(generations, dict):
        raise ValueError("Missing generations in engine output")

    required_generation_keys = ["silent", "baby_boomers", "x", "y", "z", "alpha"]
    for key in required_generation_keys:
        if key not in generations:
            raise ValueError(f"Missing generation key: {key}")

    required_result_keys = ["checksum", "primary_generation", "age"]
    for key in required_result_keys:
        if key not in results:
            raise ValueError(f"Missing result key: {key}")

    return results, generations
