"""
QuantumFlow — Flask Application Entry Point
Root convenience module re-exporting api.app.
"""

from api.app import app

__all__ = ["app"]

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"\n[QuantumFlow] API running on http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)

