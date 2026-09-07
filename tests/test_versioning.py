from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_prompt_versioning_and_rollback():
    r = client.post("/prompts", json={"name": "greeter", "description": "says hi", "actor": "tester"})
    assert r.status_code == 200
    prompt = r.json()

    r = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"system_prompt": "Say hello to {{name}}", "commit_message": "v1", "actor": "tester"},
    )
    assert r.status_code == 200
    v1 = r.json()
    assert v1["version_number"] == 1
    assert v1["template_variables"] == ["name"]

    # first version should be auto-activated
    r = client.get(f"/prompts/{prompt['id']}")
    assert r.json()["active_version_id"] == v1["id"]

    r = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"system_prompt": "Warmly greet {{name}}", "commit_message": "v2", "actor": "tester"},
    )
    v2 = r.json()
    assert v2["version_number"] == 2

    # activating v2 should not happen automatically
    r = client.get(f"/prompts/{prompt['id']}")
    assert r.json()["active_version_id"] == v1["id"]

    r = client.post(f"/prompts/{prompt['id']}/versions/2/activate", json={"reason": "promote v2", "actor": "tester"})
    assert r.json()["active_version_id"] == v2["id"]

    # rollback to v1
    r = client.post(f"/prompts/{prompt['id']}/versions/1/activate", json={"reason": "rollback", "actor": "tester"})
    assert r.json()["active_version_id"] == v1["id"]

    activations = client.get(f"/prompts/{prompt['id']}/activations").json()
    assert len(activations) == 3  # auto-activate v1, activate v2, rollback to v1

    audit = client.get("/audit-log").json()
    actions = [a["action"] for a in audit]
    assert "create_prompt" in actions
    assert "activate" in actions
    assert "rollback" in actions


def test_diff_endpoint():
    prompt = client.post("/prompts", json={"name": "diff-test"}).json()
    client.post(f"/prompts/{prompt['id']}/versions", json={"system_prompt": "A {{x}}", "commit_message": "v1"})
    client.post(f"/prompts/{prompt['id']}/versions", json={"system_prompt": "B {{x}}", "temperature": 0.9, "commit_message": "v2"})

    diff = client.get(f"/prompts/{prompt['id']}/diff/1/2").json()
    assert "system_prompt" in diff["changed_fields"]
    assert "temperature" in diff["changed_fields"]
    assert diff["diff"]["system_prompt"]["from"] == "A {{x}}"
    assert diff["diff"]["system_prompt"]["to"] == "B {{x}}"


def test_missing_template_variable_rejected():
    prompt = client.post("/prompts", json={"name": "template-test"}).json()
    client.post(f"/prompts/{prompt['id']}/versions", json={"system_prompt": "Hello {{name}}", "commit_message": "v1"})

    r = client.post(
        "/v1/completions",
        json={"prompt_id": prompt["id"], "variables": {}, "user_key": "u1"},
    )
    assert r.status_code == 422
