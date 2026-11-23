import re
import unittest
from pathlib import Path


class OpenApiContractTests(unittest.TestCase):
    def test_documented_paths_match_the_public_api_surface(self):
        text = (Path(__file__).resolve().parents[1] / "openapi.yaml").read_text(encoding="utf-8")
        documented = set(re.findall(r"^  (/[^:]+):$", text, re.MULTILINE))
        expected = {
            "/health", "/ready", "/api/v1/media/upload", "/api/v1/sessions/{session_id}",
            "/api/v1/sessions/{session_id}/source", "/api/v1/sessions/{session_id}/music",
            "/api/v1/sessions/{session_id}/transcript", "/api/v1/sessions/{session_id}/instructions",
            "/api/v1/sessions/{session_id}/undo", "/api/v1/sessions/{session_id}/redo",
            "/api/v1/sessions/{session_id}/restore", "/api/v1/sessions/{session_id}/render",
            "/api/v1/jobs/{job_id}", "/api/v1/outputs/{filename}",
        }
        self.assertEqual(documented, expected)


if __name__ == "__main__":
    unittest.main()
