"""Private generation Lambda foundation; Polly processing belongs to SW-02/SW-08."""
import os


def handler(event, context):
    passage_id = event.get("passageId") if isinstance(event, dict) else None
    if not isinstance(passage_id, str) or not passage_id.strip():
        return {"status": "invalid_input", "error": "passageId is required"}
    return {
        "status": "not_implemented",
        "passageId": passage_id,
        "engine": "neural",
        "assetBucket": os.environ["ASSET_BUCKET"],
        "message": "Infrastructure is ready; narration generation is not implemented yet.",
    }
