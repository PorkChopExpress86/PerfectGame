import argparse
import json
import re
import sys
import os
import time
from urllib.parse import urljoin
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from shared.config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BASE_DELAY
from shared.browser_profile import get_random_headers, random_delay

def _year_aware_parse(date_str, fmt, now):
    """Parse a date string, adjusting the year if the date is >6 months away."""
    d = datetime.strptime(f"{date_str} {now.year}", fmt)
    if (now - d).days > 180:
        d = d.replace(year=now.year + 1)
    elif (d - now).days > 180:
        d = d.replace(year=now.year - 1)
    return d


def _normalize_opponent(name):
    """Strip record strings like (3-0-0) or (0-1-0) from opponent names."""
    if not name: return ""
    return re.sub(r'\s*\(\d+-\d+(?:-\d+)?\)', '', name).strip()


def _parse_game_time_minutes(time_str):
    """Return minutes since midnight for sorting, or 0 for unknown time."""
    if time_str in ("N/A", "TBD"):
        return 0
    match = re.search(r'(\d{1,2}):(\d{2})\s*([AP]M)', time_str, re.IGNORECASE)
    if not match:
        return 0
    hour, minute, period = int(match.group(1)), int(match.group(2)), match.group(3).upper()
    if period == 'PM' and hour < 12:
        hour += 12
    if period == 'AM' and hour == 12:
        hour = 0
    return hour * 60 + minute


def _parse_schedule_date_for_sort(date_str, now):
    if "," in date_str:
        date_str = date_str.split(",", 1)[1].strip()
    for fmt in ["%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%b %d", "%B %d"]:
        try:
            return _year_aware_parse(date_str, fmt, now)
        except ValueError:
            continue
    return now


def parse_and_filter_schedule(html_content, team_name_filter="D1 Athletics"):
    soup = BeautifulSoup(html_content, 'html.parser')
    schedule = []

    now = datetime.now()
    fourteen_days_ago = now - timedelta(days=14)

    team_aliases = [team_name_filter.lower(), "texas prospects", "d1 athletics", "cavazos"]

    # --- Path 1: Standard / RadGrid (Profile/Org Page) ---
    rows = soup.find_all(class_='nestedscheduleGridRow')
    if not rows: rows = soup.find_all('td', class_='nestedscheduleGridRow')

    for row in rows:
        game = {}
        date_elem = row.find(id=re.compile(r'lblMonthDay'))
        if date_elem:
            raw_date = date_elem.get_text(strip=True)
            game['date_str'] = raw_date
            try:
                game['parsed_date'] = _year_aware_parse(raw_date, "%b %d %Y", now)
            except Exception: pass
        else: continue

        opp_elem = row.find(id=re.compile(r'hlOpponentName'))
        if opp_elem:
            game['opponent'] = opp_elem.get_text(strip=True)
            rec_elem = opp_elem.find_next('span', id=re.compile(r'lblOpponentRecord'))
            if rec_elem: game['opponent_record'] = rec_elem.get_text(strip=True)
        else:
            cells = row.find_all('td')
            if len(cells) > 2: game['opponent'] = cells[2].get_text(strip=True)

        if not game.get('opponent'): continue

        time_elem = row.find(id=re.compile(r'lblTime'))
        if not time_elem:
            time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', row.get_text(), re.IGNORECASE)
            if time_match: game['time'] = time_match.group(1).strip()
        else: game['time'] = time_elem.get_text(strip=True)

        field_elem = row.find(id=re.compile(r'lblField'))
        ballpark_elem = row.find(id=re.compile(r'hlBallpark'))
        loc_parts = []
        if field_elem: loc_parts.append(field_elem.get_text(strip=True))
        if ballpark_elem: loc_parts.append(ballpark_elem.get_text(strip=True))
        game['location'] = " ".join(loc_parts).strip()

        score_elem = row.find(id=re.compile(r'lblGameScore'))
        if score_elem:
            game['score'] = score_elem.get_text(strip=True).strip(',')

        res_elem = row.find('span', style=re.compile(r'font-weight:\s*bold'))
        if res_elem and ',' in res_elem.get_text():
            game['result'] = res_elem.get_text().split(',')[0].strip()

        if game.get('score'):
            game['status'] = f"Played ({game.get('result', 'Unknown')} {game['score']})"
            game['type'] = 'Past'
        else:
            game['type'] = 'Upcoming'
            game['status'] = 'TBD'

        schedule.append(game)

    # --- Path 2: Tournament Schedule ---
    game_blocks = soup.find_all('div', class_=re.compile(r'shadow-sm'))
    for block in game_blocks:
        if 'GameID:' not in block.get_text(): continue

        links = block.find_all('a', href=re.compile(r'team=\d+'))
        our_link = None
        for l in links:
            txt = l.get_text().lower()
            if any(alias in txt for alias in team_aliases):
                our_link = l
                break

        if our_link:
            game = {'opponent': 'Unknown', 'type': 'Upcoming', 'time': 'TBD', 'location': 'TBD'}
            time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', block.get_text(), re.IGNORECASE)
            if time_match: game['time'] = time_match.group(1).strip()

            ballpark_link = block.find(id=re.compile(r'hlBallPark'))
            if ballpark_link:
                loc_txt = ballpark_link.parent.get_text(" ", strip=True)
                game['location'] = loc_txt.replace("@", " @ ").replace("  ", " ").strip()

            for l in links:
                if l != our_link:
                    game['opponent'] = l.get_text(strip=True)
                    txt_near = l.parent.get_text()
                    rec_match = re.search(r'\((\d+-\d+(?:-\d+)?)\)', txt_near)
                    if rec_match: game['opponent_record'] = rec_match.group(0)
                    else:
                        ns = l.find_next_sibling('span')
                        if ns:
                            nt = ns.get_text(strip=True)
                            if '(' in nt and '-' in nt: game['opponent_record'] = nt
                    break

            # Extract scores if the game has been played.
            # Visitor links carry style="color:#345872;"; home links have no style.
            v_div = block.find(id=re.compile(r'pnlVisitorPGScore'))
            h_div = block.find(id=re.compile(r'pnlHomeScoreFinal'))
            if v_div and h_div:
                v_txt = v_div.get_text(strip=True)
                h_txt = h_div.get_text(strip=True)
                if v_txt.isdigit() and h_txt.isdigit():
                    v_score, h_score = int(v_txt), int(h_txt)
                    our_is_visitor = bool(our_link.get('style'))
                    our_score = v_score if our_is_visitor else h_score
                    opp_score = h_score if our_is_visitor else v_score
                    result = 'W' if our_score > opp_score else ('L' if our_score < opp_score else 'T')
                    game['score'] = f"{our_score}-{opp_score}"
                    game['result'] = result
                    game['status'] = f"Played ({result} {our_score}-{opp_score})"
                    game['type'] = 'Past'

            prev_header = block.find_previous(['h4', 'h3', 'h2'])
            if prev_header: game['date_str'] = prev_header.get_text(strip=True)
            schedule.append(game)

    final_output = []
    # Deduplication strategy: group by Date + Opponent, then pick best
    groups = {}
    for g in schedule:
        # Normalize Date for grouping
        d_str = g.get('date_str') or 'TBD'
        if "," in d_str: d_str = d_str.split(",")[1].strip()
        # d_str might be "April 25" or "Apr 25"

        opp = _normalize_opponent(g.get('opponent', '?')).lower()
        key = (d_str, opp)
        if key not in groups: groups[key] = []
        groups[key].append(g)

    for key, items in groups.items():
        # Pick the one with a specific time if available
        best = items[0]
        for item in items:
            if item.get('time') and item['time'] != 'TBD' and item['time'] != 'N/A':
                best = item
                break

        # Filtering for Past games
        if best.get('type') == 'Past' and best.get('parsed_date'):
            if best['parsed_date'] < fourteen_days_ago or best['parsed_date'] > now:
                continue

        opp_name = _normalize_opponent(best.get('opponent', '?'))

        date_val = best.get('date_str') or 'TBD'
        time_val = best.get('time') or "TBD"
        if best.get('type') == 'Past' and (not time_val or time_val == 'TBD'):
            time_val = "N/A"

        final_output.append({
            'Date': date_val,
            'Time': time_val,
            'Score/Result': best.get('status') if best.get('type') == 'Past' else "N/A",
            'Opponent': opp_name,
            'Location': best.get('location', 'TBD'),
            'Type': best.get('type', 'Upcoming')
        })

    # Final Sort
    def sort_key(g):
        try:
            return (
                _parse_schedule_date_for_sort(g['Date'], now),
                _parse_game_time_minutes(g['Time']),
            )
        except Exception:
            return (datetime.now(), 0)

    final_output.sort(key=sort_key)
    return final_output

def _log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [scraper] {msg}"
    print(line)
    # Log to root monitor.log
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "monitor.log")
    try:
        with open(log_file, "a") as f: f.write(line + "\n")
    except Exception: pass

def _request_with_retry(session, url, timeout=None):
    timeout = timeout or REQUEST_TIMEOUT
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 429:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < MAX_RETRIES: time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
    raise last_exc

def fetch_team_schedule(team_name_filter="D1 Athletics", player_id="YOUR_PLAYER_ID",
                        extra_urls=None, team_url=None):
    source = f"team URL {team_url}" if team_url else f"player {player_id}"
    _log(f"Fetching schedule for {source}...")
    session = requests.Session()
    session.headers.update(get_random_headers())

    games = []
    seen_urls = set()
    queue = []

    def add_to_queue(url):
        u = url.split('#')[0].strip()
        if u and u not in seen_urls:
            seen_urls.add(u)
            queue.append(u)

    try:
        if team_url:
            add_to_queue(team_url)
        else:
            player_url = f"https://www.perfectgame.org/Players/Playerprofile.aspx?ID={player_id}"
            resp = _request_with_retry(session, player_url)
            soup = BeautifulSoup(resp.text, 'html.parser')

            team_links = soup.find_all('a', href=re.compile(r'team=\d+'))
            for link in team_links:
                txt = link.get_text().lower()
                if team_name_filter.lower() in txt or "texas prospects" in txt or "d1 athletics" in txt:
                    add_to_queue(urljoin(player_url, link['href']))
                    _log(f"Found matching team link: '{link.get_text().strip()}'")

            if not queue and team_links:
                add_to_queue(urljoin(player_url, team_links[0]['href']))

        if extra_urls:
            if isinstance(extra_urls, str): extra_urls = [extra_urls]
            for e_url in extra_urls:
                add_to_queue(e_url)

        # Process the queue with recursion for tournament schedules
        idx = 0
        while idx < len(queue):
            url = queue[idx]
            idx += 1
            try:
                time.sleep(random_delay())
                _log(f"GET {url}")
                resp = _request_with_retry(session, url)
                new_games = parse_and_filter_schedule(resp.text, team_name_filter)

                # Extract event ID to restrict crawling
                current_event_id = None
                ev_match = re.search(r'event=(\d+)', url)
                if ev_match: current_event_id = ev_match.group(1)

                # If it's a tournament schedule page, try to apply the date from URL if games are TBD
                if "TournamentSchedule.aspx" in url:
                    date_match = re.search(r'Date=(\d{2}/\d{2}/\d{4})', url)
                    if date_match:
                        d_str = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%b %d")
                        for ng in new_games:
                            if not ng.get('Date') or ng.get('Date') == 'TBD':
                                ng['Date'] = d_str

                games.extend(new_games)

                # Discover more tournament schedule or bracket links
                if "orgteamid=" in url or "TournamentSchedule.aspx" in url or "Brackets.aspx" in url:
                    s_soup = BeautifulSoup(resp.text, 'html.parser')
                    # Only follow links with the SAME event ID to avoid crawling the whole site
                    pattern = r'(TournamentSchedule|Brackets)\.aspx\?event=' + (current_event_id if current_event_id else r'\d+')
                    links = s_soup.find_all('a', href=re.compile(pattern))
                    for l in links:
                        full_url = urljoin(url, l['href'].replace("&amp;", "&"))
                        full_url = full_url.split('#')[0].strip()
                        if full_url not in seen_urls:
                            # Date filtering for schedule pages
                            d_match = re.search(r'Date=(\d{2}/\d{2}/\d{4})', full_url)
                            if d_match:
                                try:
                                    d_val = datetime.strptime(d_match.group(1), "%m/%d/%Y")
                                    # Yesterday -2 through Today +7
                                    if (datetime.now() - timedelta(days=2)) <= d_val <= (datetime.now() + timedelta(days=7)):
                                        add_to_queue(full_url)
                                        _log(f"  -> Discovered: {full_url}")
                                except ValueError: pass
                            elif "Brackets.aspx" in full_url:
                                add_to_queue(full_url)
                                _log(f"  -> Discovered Bracket: {full_url}")
            except Exception as e:
                _log(f"Error fetching {url}: {e}")

        deduped = []
        seen = set()
        for g in games:
            k = (g['Date'], g['Time'], _normalize_opponent(g['Opponent']).lower())
            if k not in seen:
                deduped.append(g)
                seen.add(k)

        _log(f"Total games found: {len(deduped)}")
        return deduped

    except Exception as e:
        _log(f"Error during fetch: {e}")
        import traceback
        _log(traceback.format_exc())
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perfect Game Team Schedule Scraper")
    parser.add_argument("--team", type=str, default="D1 Athletics")
    parser.add_argument("--player_id", type=str, default="YOUR_PLAYER_ID")
    parser.add_argument("--team-url", type=str, default=None)
    args = parser.parse_args()

    schedule_data = fetch_team_schedule(args.team, args.player_id, team_url=args.team_url)
    if schedule_data:
        print(json.dumps(schedule_data, indent=2))
    else: print("No games found.")
