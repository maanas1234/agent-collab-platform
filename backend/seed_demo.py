"""Create the demo workspace with a sample PRD. Run once before demoing."""
from app import repo
from app.db import get_session, init_db
from app.models import Workspace

PRD = """Build a URL shortener service with rate limiting.

Requirements:
- POST /shorten takes a long URL, returns a short code
- GET /:code redirects to the original URL
- Rate limit: max 10 shortens per IP per minute
- A simple web page to paste a URL and get the short link
- Basic tests covering the shorten/redirect/rate-limit behavior
"""

if __name__ == "__main__":
    init_db()
    with get_session() as session:
        session.add(Workspace(name="URL Shortener Team", prd_text=PRD))
        session.commit()
    repo.reset()
    repo.write_and_commit("README.md", f"# URL Shortener Team\n\n{PRD}", "Agent Collab Platform", "Seed workspace repo")
    print("Seeded workspace + reset repo. Start the servers, then connect agents.")
