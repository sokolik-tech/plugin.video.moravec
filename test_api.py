"""
Testovací skript pro moravec.cz API (bez Kodi).
Použití: python3 test_api.py <email> <heslo>
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "plugin.video.moravec", "resources", "lib"))
import api

api.set_token_cache_path("/tmp/moravec_token_test.json")


def main():
    if len(sys.argv) < 3:
        print("Použití: python3 test_api.py <email> <heslo>")
        sys.exit(1)

    email, password = sys.argv[1], sys.argv[2]

    print(f"[1/4] Přihlášení jako {email}...")
    try:
        api.sign_in(email, password)
        print("      OK")
    except api.ApiError as e:
        print(f"      CHYBA: {e}")
        sys.exit(1)

    print("[2/4] Načtení pořadů...")
    shows = []
    try:
        shows = api.get_shows()
        print(f"      OK – {len(shows)} pořadů")
        for s in shows:
            print(f"       - {s['title']} (id: {s['id']})")
    except api.ApiError as e:
        print(f"      CHYBA: {e}")

    if shows:
        show = shows[0]
        print(f"[3/4] Videa pořadu '{show['title']}'...")
        videos = []
        try:
            videos = api.get_videos_by_tag(show["id"])
            print(f"      OK – {len(videos)} videí")
            for v in videos[:3]:
                print(f"       - {v['title']} (id: {v['id']})")
        except api.ApiError as e:
            print(f"      CHYBA: {e}")

        if videos:
            vid = videos[0]
            print(f"[4/4] Stream URL pro '{vid['title'][:50]}'...")
            try:
                url = api.get_stream_url(vid["id"])
                print(f"      OK – {url}")
            except api.ApiError as e:
                print(f"      CHYBA: {e}")

    print("\nTest dokončen.")


if __name__ == "__main__":
    main()
