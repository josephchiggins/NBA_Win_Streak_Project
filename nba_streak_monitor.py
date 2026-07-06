#!/usr/bin/env python3
"""
NBA Streak Monitor
==================
Shows only teams that are currently ON a streak of 2+ games (win or loss).
Also displays each team's next scheduled opponent and game date/time.

DATA SOURCE (no API key needed):
    pip install nba_api requests
    python nba_streak_monitor.py

Primary:  NBA.com via nba_api  (standings + schedule)
Fallback: ESPN public API      (no key required)
"""

# ─────────────────────────────────────────────────────────────
#  TEAM CONFIGURATION  — edit freely
# ─────────────────────────────────────────────────────────────
WIN_STREAK_TEAMS = [
    "Utah Jazz",
    "Washington Wizards",
    "Indiana Pacers",
    "Sacramento Kings",
    "New Orleans Pelicans",
]

LOSS_STREAK_TEAMS = [
    "Detroit Pistons",
    "Boston Celtics",
    "Oklahoma City Thunder",
    "San Antonio Spurs",
    "Denver Nuggets",
    "Philadelphia 76ers",
    "Cleveland Cavaliers",
]

# ─────────────────────────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────────────────────────
MIN_STREAK          = 2          # only show teams with streak >= this
REFRESH_INTERVAL_MS = 120_000   # auto-refresh every 2 minutes
CURRENT_SEASON      = "2024-25"

# ─────────────────────────────────────────────────────────────
#  IMPORTS
# ─────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import urllib.request
import json
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────
#  COLOUR / FONT PALETTE
# ─────────────────────────────────────────────────────────────
BG        = "#0d1117"
PANEL     = "#161b22"
PANEL2    = "#1c2128"
BORDER    = "#30363d"
FG        = "#e6edf3"
FG_DIM    = "#8b949e"
FG_DIMMER = "#484f58"
WIN_CLR   = "#3fb950"
LOSS_CLR  = "#f85149"
ACCENT    = "#58a6ff"
GOLD      = "#d29922"

FONT_SM   = ("Segoe UI", 9)
FONT_UI   = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_LG   = ("Segoe UI", 13, "bold")
FONT_HDR  = ("Segoe UI", 11, "bold")
FONT_STRK = ("Segoe UI", 15, "bold")
FONT_MONO = ("Courier New", 10)


# ═════════════════════════════════════════════════════════════
#  DATA LAYER
# ═════════════════════════════════════════════════════════════

# ── ESPN team ID map (stable, all 30 teams) ──────────────────
# Maps team nickname → ESPN team ID string
_ESPN_ID_BY_NICKNAME: dict[str, str] = {
    "Hawks":         "1",
    "Celtics":       "2",
    "Nets":          "17",
    "Hornets":       "30",
    "Bulls":         "4",
    "Cavaliers":     "5",
    "Mavericks":     "6",
    "Nuggets":       "7",
    "Pistons":       "8",
    "Warriors":      "9",
    "Rockets":       "10",
    "Pacers":        "11",
    "Clippers":      "12",
    "Lakers":        "13",
    "Grizzlies":     "29",
    "Heat":          "14",
    "Bucks":         "15",
    "Timberwolves":  "16",
    "Pelicans":      "3",
    "Knicks":        "18",
    "Thunder":       "25",
    "Magic":         "19",
    "76ers":         "20",
    "Suns":          "21",
    "Trail Blazers": "22",
    "Kings":         "23",
    "Spurs":         "24",
    "Raptors":       "28",
    "Jazz":          "26",
    "Wizards":       "27",
}

# ── cross-platform strftime helper ───────────────────────────
import sys as _sys

def _fmt_day(dt: "datetime") -> str:
    """Return e.g. 'Thu Feb 20' — works on Windows and Linux."""
    if _sys.platform == "win32":
        return dt.strftime("%a %b %#d")
    return dt.strftime("%a %b %-d")

def _fmt_time(dt: "datetime") -> str:
    """Return e.g. '7:30 PM' — works on Windows and Linux."""
    if _sys.platform == "win32":
        return dt.strftime("%#I:%M %p")
    return dt.strftime("%-I:%M %p")

# ── name normalisation ───────────────────────────────────────
_NICKNAME_MAP = {
    "utah jazz":             "Jazz",
    "washington wizards":    "Wizards",
    "indiana pacers":        "Pacers",
    "sacramento kings":      "Kings",
    "new orleans pelicans":  "Pelicans",
    "detroit pistons":       "Pistons",
    "boston celtics":        "Celtics",
    "oklahoma city thunder": "Thunder",
    "san antonio spurs":     "Spurs",
    "denver nuggets":        "Nuggets",
    "philadelphia 76ers":    "76ers",
    "cleveland cavaliers":   "Cavaliers",
    "golden state warriors": "Warriors",
    "los angeles lakers":    "Lakers",
    "los angeles clippers":  "Clippers",
    "new york knicks":       "Knicks",
    "brooklyn nets":         "Nets",
    "toronto raptors":       "Raptors",
    "chicago bulls":         "Bulls",
    "milwaukee bucks":       "Bucks",
    "miami heat":            "Heat",
    "orlando magic":         "Magic",
    "atlanta hawks":         "Hawks",
    "charlotte hornets":     "Hornets",
    "minnesota timberwolves":"Timberwolves",
    "dallas mavericks":      "Mavericks",
    "houston rockets":       "Rockets",
    "memphis grizzlies":     "Grizzlies",
    "phoenix suns":          "Suns",
    "portland trail blazers":"Trail Blazers",
    "oklahoma city thunder": "Thunder",
    "new orleans pelicans":  "Pelicans",
}


def _to_nickname(name: str) -> str:
    fixed = _NICKNAME_MAP.get(name.lower().strip())
    if fixed:
        return fixed
    parts = name.strip().split()
    return parts[-1] if parts else name


# ── ESPN helpers ─────────────────────────────────────────────

def _espn_get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (NBAStreakMonitor/2.0)"}
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def fetch_all_streaks_espn() -> dict[str, dict]:
    """Pull standings (streak + record) from ESPN public API."""
    data = _espn_get(
        "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
    )
    result: dict[str, dict] = {}
    for group in data.get("children", []):
        for entry in group.get("standings", {}).get("entries", []):
            team     = entry.get("team", {})
            fullname = team.get("displayName", "")
            abbr     = team.get("abbreviation", "???")
            nickname = team.get("name", fullname.split()[-1])
            espn_id  = team.get("id", "")

            stats_map = {s["name"]: s for s in entry.get("stats", [])}

            def sv(key, default=0):
                return stats_map.get(key, {}).get("value", default)

            wins   = int(sv("wins"))
            losses = int(sv("losses"))
            l10_w  = int(sv("last10", 0))
            l10    = f"{l10_w}-{10 - l10_w}"

            streak_val      = int(sv("streak", 0))
            streak_type_raw = stats_map.get("streakType", {}).get("displayValue", "")
            if streak_type_raw.upper().startswith("W"):
                stype = "W"
            elif streak_type_raw.upper().startswith("L"):
                stype = "L"
            else:
                stype = "W" if streak_val > 0 else ("L" if streak_val < 0 else "?")
            slen = abs(streak_val)

            if stype == "W":
                pips = ["W"] * min(slen, 10) + ["L"] * max(0, 10 - slen)
            elif stype == "L":
                pips = ["L"] * min(slen, 10) + ["W"] * max(0, 10 - slen)
            else:
                pips = ["W"] * l10_w + ["L"] * (10 - l10_w)

            result[nickname] = {
                "name":         fullname,
                "abbreviation": abbr,
                "espn_id":      espn_id,
                "wins":         wins,
                "losses":       losses,
                "streak_type":  stype,
                "streak_len":   slen,
                "results":      pips[:10],
                "record":       f"{wins}-{losses}",
                "last10":       l10,
                "next_game":    None,   # filled in later
                "error":        None,
            }
    return result


def fetch_next_game_espn(nickname: str, team_abbr: str) -> dict | None:
    """
    Fetch the next scheduled game for a team.
    Uses hardcoded ESPN IDs so this works regardless of data source (nba_api or ESPN).
    Returns a dict with keys: opponent, home_away, day_str, time_str — or None.
    """
    espn_id = _ESPN_ID_BY_NICKNAME.get(nickname, "")
    if not espn_id:
        # Try abbr → nickname fallback via the map
        for nick, eid in _ESPN_ID_BY_NICKNAME.items():
            if nick.lower() in team_abbr.lower():
                espn_id = eid
                break
    if not espn_id:
        return None

    try:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
            f"teams/{espn_id}/schedule"
        )
        data = _espn_get(url)
        now_utc = datetime.now(timezone.utc)

        for event in data.get("events", []):
            # Skip completed / in-progress games
            status_type = (event.get("competitions", [{}])[0]
                               .get("status", {})
                               .get("type", {})
                               .get("name", ""))
            if status_type in ("STATUS_FINAL", "STATUS_IN_PROGRESS"):
                continue

            # Parse tip-off time
            date_str_raw = event.get("date", "")
            try:
                game_dt = datetime.fromisoformat(date_str_raw.replace("Z", "+00:00"))
            except Exception:
                continue

            # Belt-and-suspenders: also skip anything in the past
            if game_dt < now_utc - timedelta(hours=3):
                continue

            # Determine opponent and whether we're home or away
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])
            opponent  = "TBD"
            home_away = "vs"

            for comp in competitors:
                comp_abbr    = comp.get("team", {}).get("abbreviation", "")
                comp_ha      = comp.get("homeAway", "")   # 'home' or 'away'
                comp_name    = comp.get("team", {}).get("displayName", "TBD")

                if comp_abbr.upper() == team_abbr.upper():
                    # This is our team — are we home or away?
                    home_away = "vs" if comp_ha == "home" else "@"
                else:
                    opponent = comp_name

            # Format date/time in local timezone
            local_dt = game_dt.astimezone()
            today    = datetime.now().date()
            tomorrow = today + timedelta(days=1)

            if local_dt.date() == today:
                day_str = "Today"
            elif local_dt.date() == tomorrow:
                day_str = "Tomorrow"
            else:
                day_str = _fmt_day(local_dt)

            time_str = _fmt_time(local_dt)

            return {
                "opponent":  opponent,
                "home_away": home_away,
                "day_str":   day_str,
                "time_str":  time_str,
            }

    except Exception:
        pass
    return None


# ── nba_api primary ──────────────────────────────────────────

def fetch_all_streaks_nba_api() -> dict[str, dict]:
    from nba_api.stats.endpoints import leaguestandings
    standings = leaguestandings.LeagueStandings(
        season=CURRENT_SEASON,
        season_type="Regular Season",
        league_id="00",
    )
    data = standings.get_normalized_dict()["Standings"]
    result: dict[str, dict] = {}
    for row in data:
        city     = row.get("TeamCity", "")
        nickname = row.get("TeamName", "")
        abbr     = row.get("TeamAbbreviation", "???")
        wins     = int(row.get("WINS", 0))
        losses   = int(row.get("LOSSES", 0))
        l10      = row.get("L10", "?-?")

        streak_str = row.get("strCurrentStreak", "").strip()
        if streak_str and len(streak_str) >= 3:
            stype = streak_str[0]
            try:
                slen = int(streak_str[2:].strip())
            except ValueError:
                stype, slen = "?", 0
        else:
            stype, slen = "?", 0

        try:
            l10w, _ = (int(x) for x in l10.split("-"))
            if stype == "W":
                pips = ["W"] * min(slen, 10) + ["L"] * max(0, 10 - slen)
            elif stype == "L":
                pips = ["L"] * min(slen, 10) + ["W"] * max(0, 10 - slen)
            else:
                pips = ["W"] * l10w + ["L"] * (10 - l10w)
            pips = pips[:10]
        except Exception:
            pips = []

        result[nickname] = {
            "name":         f"{city} {nickname}",
            "abbreviation": abbr,
            "espn_id":      "",
            "wins":         wins,
            "losses":       losses,
            "streak_type":  stype,
            "streak_len":   slen,
            "results":      pips,
            "record":       f"{wins}-{losses}",
            "last10":       l10,
            "next_game":    None,
            "error":        None,
        }
    return result


def fetch_all_streaks() -> tuple[dict[str, dict], str]:
    """Try nba_api first, fall back to ESPN."""
    try:
        data = fetch_all_streaks_nba_api()
        return data, "NBA.com"
    except ImportError:
        pass
    except Exception:
        pass
    data = fetch_all_streaks_espn()
    return data, "ESPN"


def resolve_team(team_name: str, all_data: dict[str, dict]) -> dict:
    nick = _to_nickname(team_name)
    if nick in all_data:
        return all_data[nick]
    nl = team_name.lower()
    for key, val in all_data.items():
        if key.lower() in nl or nl in val.get("name", "").lower():
            return val
    return {"name": team_name, "error": f'"{team_name}" not found in standings'}


def _longest_loss_streak_from_results(results: list[str]) -> int:
    """Given a list of 'W'/'L' strings, return the longest consecutive L run."""
    best = cur = 0
    for r in results:
        if r == "L":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def fetch_season_loss_streak_espn(espn_id: str) -> int:
    """Return the longest loss streak seen so far this season via ESPN schedule."""
    if not espn_id:
        return 0
    try:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
            f"teams/{espn_id}/schedule"
        )
        data = _espn_get(url)
        results: list[str] = []
        for event in data.get("events", []):
            comp = event.get("competitions", [{}])[0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue
            for c in comp.get("competitors", []):
                if c.get("team", {}).get("id", "") == espn_id:
                    results.append("W" if c.get("winner", False) else "L")
                    break
        return _longest_loss_streak_from_results(results)
    except Exception:
        return 0


def fetch_season_loss_streak_nba_api(team_abbreviation: str) -> int:
    """Return the longest loss streak seen so far this season via nba_api."""
    try:
        from nba_api.stats.static import teams as nba_teams
        from nba_api.stats.endpoints import teamgamelog
        all_t = nba_teams.get_teams()
        team = next((t for t in all_t
                     if t["abbreviation"].upper() == team_abbreviation.upper()), None)
        if not team:
            return 0
        log = teamgamelog.TeamGameLog(
            team_id=team["id"],
            season=CURRENT_SEASON,
            season_type_all_star="Regular Season",
        )
        rows = log.get_normalized_dict()["TeamGameLog"]
        results = [row.get("WL", "") for row in reversed(rows)
                   if row.get("WL", "") in ("W", "L")]
        return _longest_loss_streak_from_results(results)
    except Exception:
        return 0


def enrich_with_season_worst(info: dict) -> dict:
    """Add 'season_worst_loss_streak' key to info dict in-place and return it."""
    abbr     = info.get("abbreviation", "")
    nickname = _to_nickname(info.get("name", ""))
    espn_id  = _ESPN_ID_BY_NICKNAME.get(nickname, "")
    best = fetch_season_loss_streak_nba_api(abbr)
    if best == 0:
        best = fetch_season_loss_streak_espn(espn_id)
    info["season_worst_loss_streak"] = best
    return info


# ═════════════════════════════════════════════════════════════
#  TEAM CARD WIDGET
# ═════════════════════════════════════════════════════════════

class TeamCard(tk.Frame):
    PIPS = 10

    def __init__(self, parent, info: dict, **kw):
        super().__init__(parent, bg=PANEL, bd=0,
                         highlightthickness=1, highlightbackground=BORDER, **kw)
        self.info = info
        self._build()
        self._populate()

    def _build(self):
        # ── top row: abbr / name / record ──
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(10, 2))

        stype = self.info.get("streak_type", "?")
        accent = WIN_CLR if stype == "W" else LOSS_CLR

        self.abbr_lbl = tk.Label(top, text=self.info.get("abbreviation", "---"),
                                  font=FONT_BOLD, bg=PANEL, fg=accent,
                                  width=4, anchor="w")
        self.abbr_lbl.pack(side="left")

        self.name_lbl = tk.Label(top, text=self.info.get("name", ""),
                                  font=FONT_BOLD, bg=PANEL, fg=FG, anchor="w")
        self.name_lbl.pack(side="left", padx=(4, 0))

        self.rec_lbl = tk.Label(top, text=self.info.get("record", ""),
                                 font=FONT_SM, bg=PANEL, fg=FG_DIM)
        self.rec_lbl.pack(side="right")

        # ── streak badge row ──
        mid = tk.Frame(self, bg=PANEL)
        mid.pack(fill="x", padx=12, pady=2)

        slen  = self.info.get("streak_len", 0)
        badge_txt = f"  {'W' if stype=='W' else 'L'}{slen}  "
        badge_bg  = WIN_CLR if stype == "W" else LOSS_CLR
        sub_txt   = (f"{'Win' if stype=='W' else 'Loss'} streak · "
                     f"{slen} in a row")

        self.badge = tk.Label(mid, text=badge_txt, font=FONT_STRK,
                               bg=badge_bg, fg=BG, padx=6, pady=1)
        self.badge.pack(side="left")

        self.sub_lbl = tk.Label(mid, text=sub_txt, font=FONT_SM,
                                 bg=PANEL, fg=badge_bg)
        self.sub_lbl.pack(side="left", padx=10)

        l10 = self.info.get("last10", "")
        if l10:
            tk.Label(mid, text=f"L10: {l10}", font=FONT_SM,
                     bg=PANEL, fg=FG_DIM).pack(side="right", padx=4)

        # ── pip bar ──
        pip_row = tk.Frame(self, bg=PANEL)
        pip_row.pack(fill="x", padx=12, pady=(3, 0))

        pips = self.info.get("results", [])
        for i in range(self.PIPS):
            clr = BORDER
            if i < len(pips):
                clr = WIN_CLR if pips[i] == "W" else LOSS_CLR
            p = tk.Frame(pip_row, width=16, height=16, bg=clr)
            p.pack(side="left", padx=1)
            p.pack_propagate(False)

        # ── season-worst badge (shown only when flagged) ──
        if self.info.get("is_season_worst"):
            worst = self.info.get("season_worst_loss_streak", slen)
            sw_frame = tk.Frame(self, bg="#2d1b1b")
            sw_frame.pack(fill="x", padx=0, pady=(4, 0))
            tk.Frame(sw_frame, height=1, bg="#6e2020").pack(fill="x")
            sw_inner = tk.Frame(sw_frame, bg="#2d1b1b")
            sw_inner.pack(fill="x", padx=12, pady=5)
            tk.Label(sw_inner, text="🔥", font=FONT_SM,
                     bg="#2d1b1b").pack(side="left")
            tk.Label(sw_inner,
                     text=f"  Season-worst loss streak  ({worst} games)",
                     font=FONT_BOLD, bg="#2d1b1b", fg="#ff6b6b").pack(side="left")

        # ── next game row ──
        ng_frame = tk.Frame(self, bg=PANEL2)
        ng_frame.pack(fill="x", padx=0, pady=(4, 0))

        tk.Frame(ng_frame, height=1, bg=BORDER).pack(fill="x")

        ng_inner = tk.Frame(ng_frame, bg=PANEL2)
        ng_inner.pack(fill="x", padx=12, pady=6)

        tk.Label(ng_inner, text="NEXT", font=("Segoe UI", 8, "bold"),
                 bg=PANEL2, fg=FG_DIMMER).pack(side="left")

        ng = self.info.get("next_game")
        if ng:
            tk.Label(ng_inner, text=f"  {ng['home_away']} {ng['opponent']}",
                     font=FONT_BOLD, bg=PANEL2, fg=FG).pack(side="left", padx=(4, 0))
            tk.Label(ng_inner,
                     text=f"{ng['day_str']}  ·  {ng['time_str']}",
                     font=FONT_SM, bg=PANEL2, fg=ACCENT).pack(side="right")
        else:
            tk.Label(ng_inner, text="  schedule unavailable",
                     font=FONT_SM, bg=PANEL2, fg=FG_DIMMER).pack(side="left", padx=4)

        # Glowing border — red-orange for season-worst, else standard
        if self.info.get("is_season_worst"):
            border_clr = "#ff6b6b"
        elif slen >= 3:
            border_clr = WIN_CLR if stype == "W" else LOSS_CLR
        else:
            border_clr = BORDER
        self.config(highlightbackground=border_clr)

    def _populate(self):
        pass  # data supplied at construction time


# ═════════════════════════════════════════════════════════════
#  EMPTY STATE WIDGET
# ═════════════════════════════════════════════════════════════

class EmptyState(tk.Frame):
    def __init__(self, parent, text: str, **kw):
        super().__init__(parent, bg=PANEL, bd=0,
                         highlightthickness=1, highlightbackground=BORDER, **kw)
        tk.Label(self, text=text, font=FONT_SM, bg=PANEL, fg=FG_DIM, pady=14).pack()


# ═════════════════════════════════════════════════════════════
#  TEAM EDITOR DIALOG
# ═════════════════════════════════════════════════════════════

class TeamEditor(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Edit Monitored Teams")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self._center()

    def _build(self):
        tk.Label(self, text="Edit Team Lists", font=FONT_LG, bg=BG, fg=FG
                 ).pack(pady=(16, 2))
        tk.Label(self,
                 text="One team per line  ·  e.g. 'Boston Celtics'  ·  "
                      f"Only teams on a {MIN_STREAK}+ game streak will appear",
                 font=FONT_SM, bg=BG, fg=FG_DIM, wraplength=500).pack(pady=(0, 4))

        cols = tk.Frame(self, bg=BG)
        cols.pack(padx=20, pady=8)

        self.texts: dict[str, tk.Text] = {}
        for key, title, clr, init in [
            ("win",  "🟢  Win Streak Watch",  WIN_CLR,  self.app.win_teams),
            ("loss", "🔴  Loss Streak Watch", LOSS_CLR, self.app.loss_teams),
        ]:
            f = tk.Frame(cols, bg=BG)
            f.pack(side="left", fill="both", expand=True, padx=8)
            tk.Label(f, text=title, font=FONT_BOLD, bg=BG, fg=clr).pack(anchor="w")
            txt = tk.Text(f, width=30, height=14, bg=PANEL, fg=FG,
                          insertbackground=FG, font=FONT_MONO, relief="flat",
                          highlightthickness=1, highlightbackground=BORDER)
            txt.insert("1.0", "\n".join(init))
            txt.pack(pady=(4, 0))
            self.texts[key] = txt

        # Min streak spinner
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(pady=(6, 0))
        tk.Label(ctrl, text="Minimum streak length:", font=FONT_SM,
                 bg=BG, fg=FG_DIM).pack(side="left")
        self._min_var = tk.IntVar(value=self.app.min_streak)
        tk.Spinbox(ctrl, from_=1, to=20, width=4, textvariable=self._min_var,
                   font=FONT_UI, bg=PANEL, fg=FG, buttonbackground=BORDER,
                   insertbackground=FG, relief="flat").pack(side="left", padx=6)

        btns = tk.Frame(self, bg=BG)
        btns.pack(pady=(8, 16))
        kw = dict(font=FONT_SM, relief="flat", cursor="hand2", padx=14, pady=5)
        tk.Button(btns, text="Cancel", bg=PANEL, fg=FG,
                  activebackground=BORDER, command=self.destroy, **kw
                  ).pack(side="left", padx=6)
        tk.Button(btns, text="Apply & Refresh", bg=ACCENT, fg=BG,
                  activebackground="#79c0ff", command=self._apply, **kw
                  ).pack(side="left", padx=6)

    def _apply(self):
        win  = [l.strip() for l in self.texts["win"].get("1.0","end").splitlines()  if l.strip()]
        loss = [l.strip() for l in self.texts["loss"].get("1.0","end").splitlines() if l.strip()]
        if not win and not loss:
            messagebox.showwarning("Empty", "Please add at least one team.", parent=self)
            return
        self.app.min_streak = max(1, self._min_var.get())
        self.app.apply_team_lists(win, loss)
        self.destroy()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = self.app.winfo_x() + (self.app.winfo_width()  - w) // 2
        y = self.app.winfo_y() + (self.app.winfo_height() - h) // 2
        self.geometry(f"+{x}+{y}")


# ═════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NBA Streak Monitor")
        self.configure(bg=BG)
        self.geometry("1460x760")
        self.minsize(1000, 500)

        self.win_teams:  list[str] = list(WIN_STREAK_TEAMS)
        self.loss_teams: list[str] = list(LOSS_STREAK_TEAMS)
        self.min_streak: int       = MIN_STREAK

        self._all_data:  dict[str, dict] = {}
        self._busy      = False
        self._after_id  = None

        self._build_chrome()
        self._build_board()
        self.after(150, self._refresh)

    # ── chrome ──────────────────────────────────────────────
    def _build_chrome(self):
        topbar = tk.Frame(self, bg=BG)
        topbar.pack(fill="x", padx=18, pady=(14, 4))

        tk.Label(topbar, text="🏀  NBA Streak Monitor",
                 font=FONT_LG, bg=BG, fg=FG).pack(side="left")

        kw = dict(font=FONT_SM, relief="flat", cursor="hand2", padx=12, pady=5)
        self.btn_refresh = tk.Button(
            topbar, text="⟳  Refresh", bg=ACCENT, fg=BG,
            activebackground="#79c0ff", command=self._refresh, **kw)
        self.btn_refresh.pack(side="right", padx=(6, 0))

        tk.Button(topbar, text="⚙  Edit Teams", bg=PANEL, fg=FG,
                  activebackground=BORDER, command=lambda: TeamEditor(self), **kw
                  ).pack(side="right", padx=(6, 0))

        # Legend
        leg = tk.Frame(self, bg=BG)
        leg.pack(fill="x", padx=18, pady=(0, 4))
        for clr, lbl in [(WIN_CLR, "Win"), (LOSS_CLR, "Loss"), (BORDER, "No data")]:
            tk.Frame(leg, width=13, height=13, bg=clr).pack(side="left", padx=(0, 3))
            tk.Label(leg, text=lbl, font=FONT_SM, bg=BG, fg=FG_DIM
                     ).pack(side="left", padx=(0, 10))
        tk.Label(leg, text="· dots = recent form, newest left",
                 font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left")

        # Status bar
        sb = tk.Frame(self, bg=BG)
        sb.pack(fill="x", padx=18, pady=(0, 6))
        self._status = tk.StringVar(value="Initialising…")
        tk.Label(sb, textvariable=self._status,
                 font=FONT_SM, bg=BG, fg=FG_DIM, anchor="w").pack(side="left")
        self._ts_lbl = tk.Label(sb, text="", font=FONT_SM, bg=BG, fg=FG_DIM)
        self._ts_lbl.pack(side="right")

    # ── scrollable board ────────────────────────────────────
    def _build_board(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self._canvas = tk.Canvas(outer, bg=BG, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._board = tk.Frame(self._canvas, bg=BG)
        self._cwin  = self._canvas.create_window((0, 0), window=self._board, anchor="nw")

        self._board.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._cwin, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def _repopulate_board(self, win_infos: list[dict], loss_infos: list[dict],
                          worst_infos: list[dict]):
        for w in self._board.winfo_children():
            w.destroy()

        left   = tk.Frame(self._board, bg=BG)
        middle = tk.Frame(self._board, bg=BG)
        right  = tk.Frame(self._board, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        middle.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right.pack(side="left", fill="both", expand=True)

        n_win   = len(win_infos)
        n_loss  = len(loss_infos)
        n_worst = len(worst_infos)

        self._col_hdr(left,
                      f"🟢  Win Streak Watch  ({n_win} team{'s' if n_win!=1 else ''})",
                      WIN_CLR)
        self._col_hdr(middle,
                      f"🔴  Loss Streak Watch  ({n_loss} team{'s' if n_loss!=1 else ''})",
                      LOSS_CLR)
        self._col_hdr(right,
                      f"🔥  Season-Worst Loss Streak  ({n_worst} team{'s' if n_worst!=1 else ''})",
                      "#ff6b6b")

        if win_infos:
            for info in sorted(win_infos, key=lambda x: x.get("streak_len", 0), reverse=True):
                TeamCard(left, info).pack(fill="x", pady=5)
        else:
            EmptyState(left, f"🟢  No teams on a {self.min_streak}+ game win streak"
                       ).pack(fill="x", pady=5)

        if loss_infos:
            for info in sorted(loss_infos, key=lambda x: x.get("streak_len", 0), reverse=True):
                TeamCard(middle, info).pack(fill="x", pady=5)
        else:
            EmptyState(middle, f"🔴  No teams on a {self.min_streak}+ game loss streak"
                       ).pack(fill="x", pady=5)

        if worst_infos:
            for info in sorted(worst_infos, key=lambda x: x.get("streak_len", 0), reverse=True):
                TeamCard(right, info).pack(fill="x", pady=5)
        else:
            EmptyState(right, "🔥  No teams currently on their season-worst loss streak"
                       ).pack(fill="x", pady=5)

    @staticmethod
    def _col_hdr(parent, text: str, color: str):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=(4, 6))
        tk.Label(f, text=text, font=FONT_HDR, bg=BG, fg=color).pack(side="left")
        tk.Frame(f, height=2, bg=color).pack(side="bottom", fill="x")

    # ── data loading ─────────────────────────────────────────
    def _refresh(self):
        if self._busy:
            return
        self._busy = True
        self.btn_refresh.config(state="disabled", text="  …  ")
        if self._after_id:
            self.after_cancel(self._after_id)

        # Clear board with a loading indicator
        for w in self._board.winfo_children():
            w.destroy()
        tk.Label(self._board, text="Fetching live standings…",
                 font=FONT_UI, bg=BG, fg=FG_DIM).pack(pady=40)

        self._status.set("Fetching standings…")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            all_data, source = fetch_all_streaks()

            # ── Columns 1 & 2: current streak filter ──
            win_infos:   list[dict] = []
            loss_infos:  list[dict] = []
            worst_infos: list[dict] = []

            # Collect all qualifying teams that need a next-game fetch
            ng_needed: list[tuple[list, dict]] = []

            for name in self.win_teams:
                info = resolve_team(name, all_data)
                if (not info.get("error") and
                        info.get("streak_type") == "W" and
                        info.get("streak_len", 0) >= self.min_streak):
                    ng_needed.append((win_infos, info))

            for name in self.loss_teams:
                info = resolve_team(name, all_data)
                if (not info.get("error") and
                        info.get("streak_type") == "L" and
                        info.get("streak_len", 0) >= self.min_streak):
                    ng_needed.append((loss_infos, info))

            # ── Column 3: season-worst loss streak (all 30 teams) ──
            total_teams = len(all_data)
            self.after(0, lambda t=total_teams: self._status.set(
                f"Checking season-worst loss streaks for all {t} teams…"))
            for idx, info in enumerate(all_data.values(), 1):
                if info.get("error"):
                    continue
                self.after(0, lambda d=idx, t=total_teams: self._status.set(
                    f"Season-worst check: {d}/{t} teams…"))

                # Fetch full season game log to find the worst loss streak
                enrich_with_season_worst(info)
                season_worst = info.get("season_worst_loss_streak", 0)
                current_len  = info.get("streak_len", 0) if info.get("streak_type") == "L" else 0

                # Qualify: currently ON their season-worst loss streak (≥2 games)
                if season_worst >= 2 and current_len == season_worst:
                    info["is_season_worst"] = True
                    ng_needed.append((worst_infos, info))

            # ── Fetch next game for all qualifying teams ──
            total = len(ng_needed)
            for i, (target_list, info) in enumerate(ng_needed):
                self.after(0, lambda done=i+1, t=total:
                    self._status.set(f"Fetching schedules {done}/{t}…"))
                nickname = _to_nickname(info.get("name", ""))
                abbr     = info.get("abbreviation", "")
                info["next_game"] = fetch_next_game_espn(nickname, abbr)
                target_list.append(info)

            self.after(0, lambda: self._apply_data(win_infos, loss_infos, worst_infos, source))

        except Exception as exc:
            self.after(0, lambda e=exc: self._on_error(e))

    def _apply_data(self, win_infos: list, loss_infos: list,
                    worst_infos: list, source: str):
        self._repopulate_board(win_infos, loss_infos, worst_infos)
        now = datetime.now().strftime("%H:%M:%S")
        total = len(win_infos) + len(loss_infos)
        self._ts_lbl.config(text=f"Updated {now} · {source}")
        self._status.set(
            f"✓  {total} team{'s' if total!=1 else ''} on a {self.min_streak}+ game streak  "
            f"·  {len(worst_infos)} on season-worst loss streak  "
            f"·  auto-refresh in 2 min"
        )
        self._finish()

    def _on_error(self, exc: Exception):
        msg = str(exc)
        if "ModuleNotFoundError" in type(exc).__name__ or "No module" in msg:
            msg = ("nba_api not installed.\n"
                   "Run:  pip install nba_api requests\n"
                   "Then restart the app.")
        elif "urlopen" in msg or "gaierror" in msg.lower():
            msg = "Network error — check your internet connection."

        for w in self._board.winfo_children():
            w.destroy()
        tk.Label(self._board, text=f"⚠  {msg}", font=FONT_UI,
                 bg=BG, fg=LOSS_CLR, wraplength=600, justify="left").pack(pady=30, padx=20)
        self._status.set(f"Error: {msg[:80]}")
        self._finish()

    def _finish(self):
        self.btn_refresh.config(state="normal", text="⟳  Refresh")
        self._busy = False
        self._after_id = self.after(REFRESH_INTERVAL_MS, self._refresh)

    def apply_team_lists(self, win: list[str], loss: list[str]):
        self.win_teams  = win
        self.loss_teams = loss
        self._refresh()


# ═════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    App().mainloop()