# Concurrency Matching Test

import logging
import asyncio
import random
import time
import collections
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# The base URL of the running application.
BASE_URL = "http://127.0.0.1:5000"
LOBBY_URL = f"{BASE_URL}/lobby"

# Number of concurrent users to simulate
N_USERS = 10

# How long to wait for a match (redirect to game page)
MATCH_TIMEOUT = 30000  # milliseconds

STAGGER_TIME = 1.0  # seconds, uniformly sample and shift the starting time


async def simulate_user(browser, user_id):
    """
    Simulates a single user using a browser context.
    """
    # Create a new browser context (like a fresh incognito window)
    context = await browser.new_context()
    page = await context.new_page()
    
    logging.info(f"[User {user_id:02d}] Opening lobby...")
    
    await asyncio.sleep(random.uniform(0.0, STAGGER_TIME))  # slight stagger to avoid exact simultaneous hits
    
    try:
        # Navigate to lobby
        await page.goto(LOBBY_URL)
        
        # Random delay before clicking play
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)
        
        logging.info(f"[User {user_id:02d}] Clicking 'Play'...")
        
        # Click the Play button
        # The button has id="go"
        await page.click("#go")
        
        # Wait for navigation to the game page (index.html)
        # The URL pattern we expect is /index.html?room=...&team=...
        logging.info(f"[User {user_id:02d}] Waiting for match (redirect)...")
        
        try:
            await page.wait_for_url("**/index.html?*", timeout=MATCH_TIMEOUT)
        except PlaywrightTimeoutError:
            logging.warning(f"[User {user_id:02d}] Timed out waiting for redirect.")
            await context.close()
            return {'user': user_id, 'status': 'timeout'}
            
        # Parse the final URL to get room and team
        final_url = page.url
        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        
        room = qs.get('room', [''])[0]
        team = qs.get('team', [''])[0]
        
        logging.info(f"[User {user_id:02d}] Matched! Room: '{room}', Team: '{team}'")
        
        # Keep the page open for a moment to ensure any post-load scripts run (optional)
        # await asyncio.sleep(1)
        
        await context.close()
        return {'user': user_id, 'status': 'matched', 'room': room, 'team': team}

    except Exception as e:
        logging.error(f"[User {user_id:02d}] Error: {e}", exc_info=True)
        await context.close()
        return {'user': user_id, 'status': 'error', 'reason': str(e)}

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    logging.info(f"--- Starting Browser Concurrency Test for {N_USERS} Users ---")
    start_time = time.time()

    async with async_playwright() as p:
        # Launch the browser (headless=True by default)
        browser = await p.chromium.launch(headless=True)
        
        tasks = [simulate_user(browser, i + 1) for i in range(N_USERS)]
        results = await asyncio.gather(*tasks)
        
        await browser.close()

    end_time = time.time()
    logging.info(f"\n--- Test Finished in {end_time - start_time:.2f} seconds ---\n")

    # --- Analyze and Print Results ---
    matched_users = [r for r in results if r and r.get('status') == 'matched']
    timed_out_users = [r for r in results if r and r.get('status') == 'timeout']
    error_users = [r for r in results if r and r.get('status') == 'error']
    
    logging.info("--- Results Summary ---")
    logging.info(f"Total Users Simulated: {N_USERS}")
    logging.info(f"Successfully Matched:  {len(matched_users)}")
    logging.info(f"Timed Out:             {len(timed_out_users)}")
    logging.info(f"Errors:                {len(error_users)}")

    if matched_users:
        rooms = collections.defaultdict(list)
        for r in matched_users:
            rooms[r['room']].append(f"User {r['user']:02d} ({r['team']})")
        
        logging.info("\n--- Room Assignments ---")
        for room_id, users_in_room in sorted(rooms.items()):
            logging.info(f"Room '{room_id}':")
            if len(users_in_room) == 2:
                logging.info(f"  - {users_in_room[0]}")
                logging.info(f"  - {users_in_room[1]}")
                logging.info("  Status: ✅ Correctly paired")
            else:
                logging.warning(f"  - Users: {', '.join(users_in_room)}")
                logging.warning(f"  Status: ❌ Incorrectly paired (count: {len(users_in_room)})")

    if timed_out_users:
        logging.info("\n--- Timed Out Users ---")
        logging.info(", ".join([f"User {r['user']}" for r in timed_out_users]))

    if error_users:
        logging.error("\n--- Users with Errors ---")
        for r in error_users:
            logging.error(f"  - User {r['user']}: {r.get('reason', 'Unknown error')}")

if __name__ == "__main__":
    # Ensure an event loop is running
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "cannot run loop while another loop is running" in str(e):
            import nest_asyncio
            nest_asyncio.apply()
            asyncio.run(main())
        else:
            raise
