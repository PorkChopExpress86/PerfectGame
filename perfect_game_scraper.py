import argparse
import json
import re
import sys
import os
import time
from urllib.parse import urljoin
import requests
from datetime import datetime, timedelta

from config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BASE_DELAY
from browser_profile import get_random_headers, random_delay

def parse_and_filter_schedule(html_content):
    if 'nestedscheduleGridRow' not in html_content:
        return []
        
    rows = html_content.split('nestedscheduleGridRow')[1:]
    schedule = []
    
    current_year = datetime.now().year
    now = datetime.now()
    fourteen_days_ago = now - timedelta(days=14)
    
    for row_html in rows:
        game = {}
        
        # Extract Date
        date_match = re.search(r'lblMonthDay"[^>]*>(.*?)</span>', row_html)
        if date_match: 
            raw_date = date_match.group(1).strip()
            game['date_str'] = raw_date
            try:
                parsed_date = datetime.strptime(f"{raw_date} {current_year}", "%b %d %Y")
                game['parsed_date'] = parsed_date
            except Exception:
                game['parsed_date'] = None
        else:
            continue
            
        # Extract Time (if upcoming)
        time_match = re.search(r'lblTime"[^>]*>(.*?)</span>', row_html)
        if time_match: 
            game['time'] = time_match.group(1).strip()
            
        # Extract Opponent Name
        opp_match = re.search(r'hlOpponentName"[^>]*>(.*?)</a>', row_html)
        if opp_match: 
            game['opponent'] = opp_match.group(1).strip()
            
        # Extract Field and Location
        field_match = re.search(r'lblField"[^>]*>(.*?)</span>', row_html)
        ballpark_match = re.search(r'hlBallpark"[^>]*>(.*?)</a>', row_html)
        field_str = ""
        if field_match: 
            field_str += field_match.group(1).strip()
        if ballpark_match: 
            field_str += " " + ballpark_match.group(1).strip()
            
        if field_str: 
            game['location'] = field_str.strip()
            
        # Extract Score (if played)
        score_match = re.search(r'lblGameScore"[^>]*>(.*?)</span>', row_html)
        if score_match: 
            game['score'] = score_match.group(1).strip().strip(',')
            
        # Extract Game Result 
        res_match = re.search(r'<span style="font-weight:bold;">(.*?), </span>', row_html)
        if res_match: 
            game['result'] = res_match.group(1).strip()

        # Determine overall status
        if game.get('score'):
            game['status'] = f"Played ({game.get('result', 'Unknown')} {game['score']})"
            game['type'] = 'Past'
        elif not game.get('time') or game.get('time') == 'N/A':
            game['type'] = 'Upcoming'
            game['status'] = 'TBD'
        else:
            game['type'] = 'Upcoming'
            game['status'] = f"Upcoming at {game['time']}"
            
        if game.get('opponent'):
            schedule.append(game)
            
    # Now filter: Last 14 days + all Upcoming
    filtered = []
    for g in schedule:
        if g['type'] == 'Upcoming':
            filtered.append(g)
            continue
        if g['type'] == 'Past' and g.get('parsed_date'):
            if g['parsed_date'] >= fourteen_days_ago and g['parsed_date'] <= now:
                filtered.append(g)
                
    output = []
    for g in filtered:
        output.append({
            'Date': g.get('date_str'),
            'Time': g.get('time') if g['type'] == 'Upcoming' else "N/A",
            'Score/Result': g.get('status') if g['type'] == 'Past' else "N/A",
            'Opponent': g.get('opponent'),
            'Location': g.get('location'),
            'Type': g.get('type')
        })
    return output

def _log(msg):
    """Lightweight logger."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [scraper] {msg}"
    print(line)
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")
    try:
        with open(log_file, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _request_with_retry(session, url, timeout=None):
    """
    Make an HTTP GET request with exponential backoff on failure.

    Retries on 429 (rate-limited), 5xx server errors, connection errors,
    and timeouts.  Returns the Response on success, or raises on exhaustion.
    """
    timeout = timeout or REQUEST_TIMEOUT
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 429:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                _log(f"  429 rate-limited — retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                _log(f"  {resp.status_code} server error — retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                _log(f"  Request failed ({e}) — retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                _log(f"  Request failed after {MAX_RETRIES} attempts: {e}")

    raise last_exc or RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts")


def fetch_team_schedule(team_name_filter="Your Team Name", player_id="YOUR_PLAYER_ID"):
    """
    Fetches the team schedule using requests with rotating browser headers
    and human-like delays between requests.
    Navigates via the player profile to find the team link.
    """
    _log(f"Fetching schedule for player {player_id} via robust requests...")

    session = requests.Session()
    session.headers.update(get_random_headers())
    _log(f"  UA: {session.headers.get('User-Agent', '')[:60]}...")

    try:
        # 1. Load Player Profile
        player_url = f"https://www.perfectgame.org/Players/Playerprofile.aspx?ID={player_id}"
        _log(f"GET {player_url}")
        resp = _request_with_retry(session, player_url)

        # 2. Find the team link
        _log(f"Looking for team links matching '{team_name_filter}'...")
        team_matches = re.findall(r'href="([^"]*team=\d+[^"]*)"[^>]*>(.*?)</a>', resp.text, re.IGNORECASE)

        target_href = None
        for href, text in team_matches:
            if team_name_filter.lower() in text.lower():
                target_href = href
                _log(f"Found matching team link: '{text.strip()}' -> {href}")
                break

        if not target_href:
            if team_matches:
                target_href = team_matches[0][0]
                _log(f"Could not find exact match for '{team_name_filter}'. Using first team link: {target_href}")
            else:
                _log("No team links found on player profile.")
                return []

        if not target_href.startswith("http"):
            target_href = urljoin(player_url, target_href.replace("&amp;", "&"))
        else:
            target_href = target_href.replace("&amp;", "&")

        # Random delay between requests — human browsing pace
        delay = random_delay()
        _log(f"  Waiting {delay:.1f}s before next request...")

        # Rotate headers for the second request
        session.headers.update(
            get_random_headers(referer=f"https://www.perfectgame.org/Players/Playerprofile.aspx?ID={player_id}")
        )

        # 3. Navigate to Team Schedule
        _log(f"GET {target_href}")
        sched_resp = _request_with_retry(session, target_href)

        _log("Parsing schedule content...")
        games = parse_and_filter_schedule(sched_resp.text)
        _log(f"Successfully parsed {len(games)} games.")
        return games

    except Exception as e:
        _log(f"Error during fetch: {e}")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perfect Game Team Schedule Scraper")
    parser.add_argument("--team", type=str, default="Your Team Name")
    parser.add_argument("--player_id", type=str, default="YOUR_PLAYER_ID")
    parser.add_argument("--url", type=str, default="")
    parser.add_argument("--file", type=str, default="")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            schedule_data = parse_and_filter_schedule(f.read())
    elif args.url:
        _log(f"Direct URL fetch requested for {args.url}")
        try:
            resp = requests.get(args.url, timeout=REQUEST_TIMEOUT, headers=get_random_headers())
            schedule_data = parse_and_filter_schedule(resp.text)
        except Exception as e:
            _log(f"Error: {e}")
            schedule_data = []
    else:
        schedule_data = fetch_team_schedule(args.team, args.player_id)
    
    if schedule_data:
        print(json.dumps(schedule_data, indent=2))
        with open("team_schedule.json", "w") as f:
            json.dump(schedule_data, f, indent=2)
    else:
        print("No games found.")
