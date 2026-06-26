"""
Mock ML Server for Testing Self-Learning System

A simple Flask server that simulates the production ML server API.
Useful for testing data uploads, model downloads, and feedback collection.

Run: python ml_server_mock/mock_server.py
"""

from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# In-memory storage
batches_db = []
feedback_db = []
model_versions = []

# Mock model metadata
CURRENT_MODEL = {
    "version": "1.2.0",
    "release_date": "2026-01-10",
    "size_mb": 8.5,
    "accuracy": 0.93,
    "download_url": "http://localhost:8000/models/download/1.2.0",
    "sha256": "abc123...",
    "changelog": "• Added 5K new Flutter samples\n• Improved checkbox detection\n• Better React Native support"
}

NEW_MODEL = {
    "version": "1.3.0",
    "release_date": "2026-01-12",
    "size_mb": 9.2,
    "accuracy": 0.95,
    "download_url": "http://localhost:8000/models/download/1.3.0",
    "sha256": "def456...",
    "changelog": "• Added 10K new samples\n• iOS SwiftUI improvements\n• Android Compose enhancements"
}


@app.route('/v1/ml/samples', methods=['POST'])
def upload_samples():
    """Upload training batch"""
    try:
        batch = request.json

        if not batch or 'samples' not in batch:
            return jsonify({"error": "Invalid batch format"}), 400

        # Store batch
        batch["received_at"] = datetime.now().isoformat()
        batches_db.append(batch)

        print(f"\n✅ Received batch: {batch.get('batch_id')}")
        print(f"   Samples: {batch.get('total_count')}")
        print(f"   Platforms: {batch.get('platform_distribution')}")

        return jsonify({
            "status": "success",
            "batch_id": batch.get('batch_id'),
            "samples_count": batch.get('total_count')
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/v1/ml/samples/stats', methods=['GET'])
def get_stats():
    """Get upload statistics"""
    total_samples = sum(b.get('total_count', 0) for b in batches_db)

    platform_dist = {}
    for batch in batches_db:
        for platform, count in batch.get('platform_distribution', {}).items():
            platform_dist[platform] = platform_dist.get(platform, 0) + count

    return jsonify({
        "total_batches": len(batches_db),
        "total_samples": total_samples,
        "platform_distribution": platform_dist,
        "last_upload": batches_db[-1].get('received_at') if batches_db else None
    })


@app.route('/v1/ml/models/latest', methods=['GET'])
def get_latest_model():
    """Get latest model metadata"""
    current_version = request.args.get('current_version', '0.0.0')

    print(f"\n📥 Model update check: current={current_version}")

    # Simulate: return new model if current version is older
    if current_version < NEW_MODEL['version']:
        print(f"   → New version available: {NEW_MODEL['version']}")
        return jsonify(NEW_MODEL), 200
    else:
        print(f"   → Already up to date")
        return jsonify(CURRENT_MODEL), 200


@app.route('/models/download/<version>', methods=['GET'])
def download_model(version):
    """Download model file"""
    print(f"\n📦 Downloading model v{version}")

    # For testing, just send a small dummy file
    # In production, this would be the actual model file
    dummy_model = b"MOCK_MODEL_DATA"

    # Save to temp file and send
    temp_file = Path(f"/tmp/model_{version}.pkl")
    with open(temp_file, 'wb') as f:
        f.write(dummy_model)

    return send_file(temp_file, as_attachment=True, download_name=f"model_{version}.pkl")  # noqa: F541


@app.route('/v1/ml/feedback', methods=['POST'])
def upload_feedback():
    """Upload user correction"""
    try:
        correction = request.json

        if not correction:
            return jsonify({"error": "Invalid feedback format"}), 400

        correction["received_at"] = datetime.now().isoformat()
        feedback_db.append(correction)

        print("\n✅ Received correction:")  # noqa: F541
        print(f"   {correction.get('predicted_type')} → {correction.get('actual_type')}")
        print(f"   Platform: {correction.get('platform')}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/v1/ml/feedback/stats', methods=['GET'])
def get_feedback_stats():
    """Get feedback statistics"""
    correction_count = len(feedback_db)

    corrections_by_type = {}
    for feedback in feedback_db:
        pred = feedback.get('predicted_type', 'unknown')
        actual = feedback.get('actual_type', 'unknown')
        key = f"{pred} → {actual}"
        corrections_by_type[key] = corrections_by_type.get(key, 0) + 1

    return jsonify({
        "total_corrections": correction_count,
        "corrections_by_type": corrections_by_type
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({"status": "ok", "service": "ML Server Mock"})


@app.route('/', methods=['GET'])
def home():
    """Homepage"""
    return """
    <h1>Mobile Observe ML Server (Mock)</h1>
    <p>Endpoints:</p>
    <ul>
        <li><b>POST</b> /v1/ml/samples - Upload training batch</li>
        <li><b>GET</b> /v1/ml/samples/stats - Get upload stats</li>
        <li><b>GET</b> /v1/ml/models/latest - Get latest model metadata</li>
        <li><b>GET</b> /models/download/&lt;version&gt; - Download model</li>
        <li><b>POST</b> /v1/ml/feedback - Upload user correction</li>
        <li><b>GET</b> /v1/ml/feedback/stats - Get feedback stats</li>
        <li><b>GET</b> /health - Health check</li>
    </ul>
    <p>Status: <span style="color: green;">Online</span></p>
    """


if __name__ == '__main__':
    print("=" * 60)
    print("  🧪 MOBILE OBSERVE ML SERVER (MOCK)")
    print("=" * 60)
    print("\n✅ Server starting on http://localhost:8000")
    print("\n📝 To use with framework:")
    print("   observe config set ml.upload_endpoint http://localhost:8000/v1/ml/samples")
    print("   observe config set ml.contribute true")
    print("\n🔍 View stats:")
    print("   curl http://localhost:8000/v1/ml/samples/stats")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=8000, debug=True)
