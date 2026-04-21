"""Phase 5 prototype endpoints. Live behind FEATURE_PROTOTYPE — registered
on every deploy but only reachable when the flag is on. Exists so the
prototype branch can iterate on vision prompts against deployed real infra
without polluting the production /attempt flow."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from services.openai_client import feature_flag
from services.ocr import diagnose

prototype_bp = Blueprint("prototype", __name__, url_prefix="/prototype")


@prototype_bp.before_request
def _gate():
    if not feature_flag("FEATURE_PROTOTYPE"):
        abort(404)


@prototype_bp.route("/diagnose", methods=["POST"])
def diagnose_endpoint():
    file = request.files.get("photo")
    if file is None:
        return jsonify({"error": "photo required"}), 400
    body = request.form.get("subpart_body", "")
    canonical = request.form.get("canonical_method")
    correct = request.form.get("correct_answer")
    submitted = request.form.get("submitted_answer")
    result = diagnose(
        photo_bytes=file.read(),
        subpart_body=body,
        canonical_method=canonical,
        marking_alternatives=[],
        correct_answer=correct,
        submitted_answer=submitted,
    )
    return jsonify(result)
