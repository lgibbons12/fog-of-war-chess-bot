"""Download a bounded recent sample from the course's documented public API.

Sequential requests, at least one second apart; completed replays are cached.
No credentials are used. See https://www.mit.edu/~6.7980/fow/api.html.
"""
import argparse
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

BASE = "https://6s890.lids.mit.edu"
NORMAL_REASONS = {"King capturable", "Threefold repetition", "50-move rule",
                  "No legal moves", "Move limit reached"}


class Client:
    def __init__(self):
        self.last_request = 0.0

    def get(self, route):
        for attempt in range(4):
            time.sleep(max(0, 1.05 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = Request(BASE + route, headers={"User-Agent": "FOW-training-sample/1.0"})
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code not in (429, 503) or attempt == 3:
                    raise
                retry = error.headers.get("Retry-After", "0")
                try:
                    delay = float(retry)
                except ValueError:
                    delay = max(0, parsedate_to_datetime(retry).timestamp() - time.time())
                if delay > 60:
                    raise RuntimeError("Server requests a longer pause; retry the download later") from error
                time.sleep(max(delay, 2 ** attempt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/public-sample"))
    parser.add_argument("--pages", type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.count <= 10000 or not 1 <= args.pages <= 100:
        parser.error("count must be 2..10000 and pages 1..100")
    args.output.mkdir(parents=True, exist_ok=True)
    client = Client()
    query = dict(sort="played", order="desc", limit=100, colors="fixed")
    def games():
        for _ in range(args.pages):
            page = client.get("/api/games?" + urlencode(query))
            yield from page["games"]
            if not page.get("nextCursor"):
                break
            query["cursor"] = page["nextCursor"]
    downloaded, skipped = [], []
    for game in games():
        if len(downloaded) >= args.count:
            break
        game_id = game["id"]
        if not re.fullmatch(r"[a-z0-9]{8}", game_id):
            raise ValueError("Invalid public game ID")
        if game.get("reason") not in NORMAL_REASONS:
            skipped.append({"id": game_id, "reason": game.get("reason")})
            continue
        path = args.output / (game_id + ".json")
        replay = json.loads(path.read_text()) if path.exists() else client.get("/api/games/" + game_id)
        if (replay.get("id") != game_id or replay.get("reason") not in NORMAL_REASONS
                or "failedSide" in replay or len(replay.get("frames", [])) < 2):
            skipped.append({"id": game_id, "reason": "Replay not eligible"})
            continue
        path.write_text(json.dumps(replay) + "\n")
        downloaded.append(game_id)
        print(f"{len(downloaded)}/{args.count}: {game_id}", flush=True)
    manifest = {"source": BASE, "documentation": "https://www.mit.edu/~6.7980/fow/api.html",
                "selection": "recent completed games with normal chess termination",
                "ids": downloaded, "skipped": skipped}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Saved {len(downloaded)} games. Train only the listed game files, not manifest.json.")


if __name__ == "__main__":
    main()
