"""Version-aware form snapshots for existing HTTP workflow tests."""
def versioned_edit(client, url, payload, headers):
    current = client.get(url, headers=headers)
    assert current.status_code == 200, current.text
    return {**payload, "expected_version": current.json()["edit_version"]}
