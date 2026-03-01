#!/usr/bin/env python3
"""
get_player_games.py - Fetches all team games for a given Perfect Game player ID.

Looks up a player's profile, finds their team links, and scrapes each team's
schedule. Outputs unique games and saves to player_<id>_games.json.

Requires the .venv virtual environment.

Usage:
    python3 get_player_games.py --player_id YOUR_PLAYER_ID
"""

import argparse
import json
import re

import requests
from bs4 import BeautifulSoup

from browser_profile import get_random_headers, random_delay
from config import REQUEST_TIMEOUT
from perfect_game_scraper import parse_and_filter_schedule, _request_with_retry

def fetch_html_with_requests(url, session=None):
    """Fetch HTML content using requests with rotating browser headers."""
    print(f"Navigating to {url}...")
    try:
        if session is None:
            session = requests.Session()
            session.headers.update(get_random_headers())
        resp = _request_with_retry(session, url, timeout=REQUEST_TIMEOUT)
        return resp.text
    except Exception as e:
        print(f"Exception fetching {url}: {e}")
        return ""

def parse_team_urls(profile_html):
    """Extracts base team URLs from the player profile HTML."""
    soup = BeautifulSoup(profile_html, 'html.parser')
    team_links = set()
    
    # We want to extract the team ID and form the base PGBA Team URL
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'team=' in href.lower():
            # Extract the team ID using regex
            match = re.search(r'team=(\d+)', href, re.IGNORECASE)
            if match:
                team_id = match.group(1)
                # Form the base PGBA Team schedule URL
                base_url = f"https://www.perfectgame.org/PGBA/Team/default.aspx?team={team_id}"
                team_links.add(base_url)
            
    print(f"Found {len(team_links)} team links.")
    return list(team_links)

def main():
    parser = argparse.ArgumentParser(description="Fetch games for a specified player.")
    parser.add_argument("--player_id", type=str, default="YOUR_PLAYER_ID", help="Perfect Game Player ID")
    args = parser.parse_args()
    
    player_url = f"https://www.perfectgame.org/Players/Playerprofile.aspx?ID={args.player_id}"
    
    print(f"Fetching profile for Player ID: {args.player_id}")

    session = requests.Session()
    session.headers.update(get_random_headers())

    profile_html = fetch_html_with_requests(player_url, session)
    
    if not profile_html:
        print("Failed to retrieve player profile.")
        return
        
    team_urls = parse_team_urls(profile_html)
    
    all_games = []
    
    for team_url in team_urls:
        print(f"Fetching team schedule for: {team_url}")
        # Random delay between team requests to avoid burst patterns
        delay = random_delay()
        print(f"  (waiting {delay:.1f}s)")
        session.headers.update(get_random_headers(referer=player_url))
        schedule_html = fetch_html_with_requests(team_url, session)
        if schedule_html:
            print("Parsing schedule...")
            # We use parse_and_filter_schedule from perfect_game_scraper
            games = parse_and_filter_schedule(schedule_html)
            print(f"Found {len(games)} recent/upcoming games for this team.")
            all_games.extend(games)
            
    print(f"\n--- Total games found: {len(all_games)} ---")
    if all_games:
        # Deduplicate games by date, time, opponent, location
        unique_games = []
        seen = set()
        for g in all_games:
            key = (g.get('Date'), g.get('Time'), g.get('Opponent'), g.get('Location'))
            if key not in seen:
                seen.add(key)
                unique_games.append(g)
                
        print(f"--- Unique games found: {len(unique_games)} ---")
        print(json.dumps(unique_games, indent=2))
        
        # Save output to file
        output_file = f"player_{args.player_id}_games.json"
        with open(output_file, "w") as f:
            json.dump(unique_games, f, indent=2)
        print(f"Saved game data to {output_file}")
    else:
        print("No games found.")

if __name__ == "__main__":
    main()
