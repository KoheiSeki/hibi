import json
from pathlib import Path

from hibi.api.main import app

output = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(output)
