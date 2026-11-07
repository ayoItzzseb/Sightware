"""Sightware GUI — AppCore service layer.

This replaces the v2.5.8 Flask HTTP layer (backend/app.py) with a plain,
thread-safe service object the tkinter UI talks to directly. All domain
modules (riot_client, live_match, encounter_log, history, session_tracker,
inventory, assistant, settings, ...) are used unchanged.

The semantics of the old REST endpoints are preserved one-to-one: the same
caches, holds, background jobs and sample fallbacks, so behavior matches
the Local Edition web dashboard exactly.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import assistant
import encounter_log
import match_meta
import pick_advisor
import sample_match
import session_tracker
import settings
import history
import inventory
import party_detector
import sightwarelog
from agents import AGENTS, resolve_agent
from riot_client import REGIONS, LocalAuth, RiotClient, ClientNotReady
from vconstants import APP_VERSION, STATES, rank_from_tier

LOG = sightwarelog.get_logger("gui")

_CACHE_TTL = float(os.getenv("PLAYER_CACHE_TTL", "60"))
_HOLD_SECS = 12
_BUILD_FRESH = 4.0
_ENCOUNTER_BACKFILL_EVERY = 600


class AppCore:
    """Single service object owning the Riot client and all caches."""

    def __init__(self) -> None:
        self.client = RiotClient()
        self._cache: dict[str, tuple[float, dict]] = {}
        self._last_good: dict = {"board": None, "at": 0.0, "notReady": False}
        self._build_lock = threading.Lock()
        self._sample_ids: set[str] = set()
        self._encounter_backfill_at: dict[str, float] = {}
        self._encounter_jobs: set[str] = set()
        self._jobs_lock = threading.Lock()
        self._performance_jobs: set[str] = set()
        self._performance_lock = threading.Lock()
        self._requests_made = 0

    # ── settings ────────────────────────────────────────────────
    def all_settings(self) -> dict:
        return settings.all_settings()

    def update_settings(self, changes: dict) -> dict:
        merged = settings.update(changes or {})
        if not merged.get("assistantEnabled"):
            assistant.stop()
        elif merged.get("assistantAutoStart"):
            assistant.start()
        return merged

    def start_services(self) -> None:
        if settings.get("assistantEnabled") and settings.get("assistantAutoStart"):
            assistant.start()

    def stop_services(self) -> None:
        assistant.stop()

    # ── helpers (ported from app.py) ────────────────────────────
    def _history_enabled(self) -> bool:
        return bool(settings.get("localHistoryEnabled"))

    def _region_arg(self) -> str | None:
        region = settings.get("region")
        return None if region in (None, "", "auto") else region

    def _include_stats(self) -> bool:
        return bool(settings.get("includeLiveStats"))

    def _live_enabled(self) -> bool:
        return self.client.source_pref != "demo" and LocalAuth.available()

    def _new_auth(self) -> LocalAuth:
        return LocalAuth(self._region_arg())

    @staticmethod
    def _summarize(matches: list[dict]) -> dict:
        n = len(matches)
        if n == 0:
            return {"matchesAnalyzed": 0, "kills": 0, "deaths": 0, "assists": 0,
                    "kd": 0, "kda": 0, "hsPct": 0, "winRate": 0, "wins": 0, "losses": 0}
        k = sum(m["stats"]["kills"] for m in matches)
        d = sum(m["stats"]["deaths"] for m in matches)
        a = sum(m["stats"]["assists"] for m in matches)
        hs = [m["stats"].get("hsPct", 0) for m in matches if m["stats"].get("hsPct")]
        wins = sum(1 for m in matches if m["result"] == "Victory")
        losses = sum(1 for m in matches if m["result"] == "Defeat")
        return {
            "matchesAnalyzed": n,
            "kills": round(k / n, 1),
            "deaths": round(d / n, 1),
            "assists": round(a / n, 1),
            "kd": round(k / d, 2) if d else float(k),
            "kda": round((k + a) / d, 2) if d else float(k + a),
            "hsPct": round(sum(hs) / len(hs), 1) if hs else 0,
            "winRate": round(100 * wins / n, 1),
            "wins": wins,
            "losses": losses,
        }

    @staticmethod
    def _decorate_match(m: dict, suggestion: dict) -> dict:
        meta = resolve_agent(m.get("agent")) or {}
        st = m["stats"]
        kda = (round((st["kills"] + st["assists"]) / st["deaths"], 2)
               if st["deaths"] else float(st["kills"] + st["assists"]))
        out = dict(m)
        out.pop("teammates", None)
        out["agentMeta"] = {
            "name": meta.get("name", m.get("agent")),
            "role": meta.get("role", "Flex"),
            "color": meta.get("color", "#FF7A1A"),
            "portrait": meta.get("portrait"),
        }
        out["stats"] = {**st, "kda": kda}
        out["pickSuggestion"] = {
            "agent": suggestion.get("agent"),
            "times": suggestion.get("times", 0),
        }
        return out

    def build_player_payload(self, puuid: str) -> dict:
        raw = self.client.get_player_overview(puuid)
        matches = raw.get("matches", [])

        party = party_detector.analyze(matches, top_n=5)
        suggestion = pick_advisor.recommend(matches)
        rank = rank_from_tier(raw.get("rankTier"))
        peak = rank_from_tier(raw.get("peakTier"))

        decorated = [self._decorate_match(m, suggestion) for m in party["matches"]]
        for dm, pm in zip(decorated, party["matches"]):
            dm["partyMembers"] = pm.get("partyMembers", [])

        return {
            "puuid": puuid,
            "riotId": raw.get("riotId", "Player"),
            "currentRank": rank["name"],
            "rankTier": rank["tier"],
            "rankGroup": rank["group"],
            "rankColor": rank["color"],
            "rr": raw.get("rr", 0),
            "peakRank": peak["name"],
            "peakColor": peak["color"],
            "source": raw.get("source", "demo"),
            "sourceDetail": raw.get("sourceDetail", ""),
            "averages": self._summarize(matches),
            "pickSuggestion": suggestion,
            "coPlayers": party["coPlayers"],
            "partyCount": party["partyCount"],
            "matches": decorated,
        }

    # ── live board ──────────────────────────────────────────────
    @staticmethod
    def _strip_art(board: dict) -> dict:
        def clean(p):
            if not isinstance(p, dict):
                return p
            out = dict(p)
            for k in ("agentPortrait", "agentArt", "rankIcon", "peakIcon",
                      "playerCard", "playerCardSmall", "mapSplash"):
                out.pop(k, None)
            skin = out.get("skin")
            if isinstance(skin, dict):
                out["skin"] = {**skin, "icon": None}
            weapons = out.get("weapons")
            if isinstance(weapons, list):
                out["weapons"] = [{**w, "skin": {**w.get("skin", {}), "icon": None}}
                                  for w in weapons if isinstance(w, dict)]
            return out
        if isinstance(board.get("players"), list):
            board["players"] = [clean(p) for p in board["players"]]
        fs = board.get("finalScoreboard")
        if isinstance(fs, dict):
            fs = dict(fs)
            fs.pop("mapSplash", None)
            if isinstance(fs.get("players"), list):
                fs["players"] = [clean(p) for p in fs["players"]]
            board["finalScoreboard"] = fs
        if isinstance(board.get("teams"), dict):
            board["teams"] = {t: [clean(p) for p in plist]
                              for t, plist in board["teams"].items()}
        board.pop("mapSplash", None)
        return board

    def _attach_encounters(self, board: dict) -> dict:
        is_live = board.get("source") == "local"
        self_team = board.get("selfTeam")
        for p in board.get("players") or []:
            if not isinstance(p, dict):
                continue
            enc = encounter_log.encounter_for(
                board.get("selfPuuid"), p.get("puuid"), board.get("matchId"),
                same_team=self_team is not None and p.get("team") == self_team,
            ) if is_live else None
            p["encounter"] = enc
        return board

    @staticmethod
    def _client_notice() -> dict:
        if not LocalAuth.available():
            return {"level": "info", "action": "open_game",
                    "message": "Open VALORANT to see live ranks, parties and stats."}
        return {"level": "warn", "action": "restart_game",
                "message": "Couldn't read VALORANT — please restart your game "
                           "(close it completely and relaunch), then try again."}

    def _remember_sample(self, data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k in ("puuid", "matchId") and isinstance(v, str):
                    self._sample_ids.add(v)
                else:
                    self._remember_sample(v)
        elif isinstance(data, list):
            for v in data:
                self._remember_sample(v)
        return data

    def _sample_ok(self, ident: str, demo: bool = False) -> bool:
        ident = str(ident or "")
        return (demo or self.client.source_pref == "demo" or ident.startswith("demo")
                or ident in self._sample_ids)

    def build_live(self, seed: int = 7, want_state: str | None = None) -> dict:
        """Port of app.py's build_live: live board with hold/cache + sample fallback."""
        notice = None
        if self._live_enabled():
            if self._last_good["board"] and time.time() - self._last_good["at"] < _BUILD_FRESH:
                return self._last_good["board"]
            if self._last_good["board"] is not None:
                if not self._build_lock.acquire(blocking=False):
                    return self._last_good["board"]
            elif not self._build_lock.acquire(timeout=30.0):
                LOG.error("live scoreboard build lock stalled >30s")
                return {"state": "OFFLINE", "stateLabel": "Offline", "source": "local",
                        "players": [], "teams": {}, "parties": [],
                        "finalScoreboard": None,
                        "notice": {"level": "warn", "action": "open_game",
                                   "message": "Still connecting to VALORANT - retrying."},
                        "appVersion": APP_VERSION}
            try:
                if self._last_good["board"] and time.time() - self._last_good["at"] < _BUILD_FRESH:
                    return self._last_good["board"]
                try:
                    import live_match
                    lm = live_match.LiveMatch(self._new_auth())
                    board = lm.build_scoreboard(include_stats=self._include_stats())
                    board.setdefault("sourceDetail", "Local VALORANT client")
                    board["selfPuuid"] = lm.self_puuid
                    self_player = next((p for p in board.get("players", [])
                                        if p.get("isSelf")), {})
                    if self._history_enabled():
                        history.remember_account(lm.self_puuid,
                                                 self_player.get("name"))
                        try:
                            session_tracker.observe(board, lm)
                            session_tracker.attach(board)
                        except Exception:
                            LOG.exception("session tracking failed")
                        try:
                            encounter_log.record_board(board)
                            self._attach_encounters(board)
                        except Exception:
                            LOG.exception("encounter logging failed")
                    board["appVersion"] = APP_VERSION
                    self._last_good["board"], self._last_good["at"] = board, time.time()
                    self._last_good["notReady"] = False
                    self._requests_made = lm.auth.req_count
                    return board
                except Exception as e:
                    if isinstance(e, ClientNotReady):
                        if not self._last_good["notReady"]:
                            LOG.info("live scoreboard: %s — waiting for sign-in", e)
                            self._last_good["notReady"] = True
                    else:
                        LOG.exception("live scoreboard failed")

                    if self._last_good["board"] and time.time() - self._last_good["at"] < _HOLD_SECS:
                        return self._last_good["board"]
                    notice = self._client_notice()
                    if self.client.source_pref == "local":
                        return {"state": "OFFLINE", "stateLabel": "Offline",
                                "source": "local", "error": str(e),
                                "players": [], "teams": {}, "parties": [],
                                "finalScoreboard": None,
                                "notice": notice, "appVersion": APP_VERSION}
            finally:
                self._build_lock.release()
        elif self.client.source_pref != "demo" and not LocalAuth.available():
            notice = self._client_notice()

        board = (sample_match.generate_lobby(seed)
                 if (want_state or "").lower() == "menus"
                 else sample_match.generate(seed))
        board = self._remember_sample(self._attach_encounters(board))
        if notice:
            board["notice"] = notice
        board["appVersion"] = APP_VERSION
        return board

    def finalize_board(self, board: dict) -> dict:
        """Port of _finalize_board: assistant snapshot, art strip."""
        board = dict(board)
        board.update(assistant.snapshot_for_board())
        if not settings.get("loadArt"):
            board = self._strip_art(board)
        return board

    def live_board(self, seed: int = 7, want_state: str | None = None) -> dict:
        return self.finalize_board(self.build_live(seed, want_state))

    def game_state(self) -> dict:
        if self._live_enabled():
            try:
                import live_match
                lm = live_match.LiveMatch(self._new_auth())
                st = lm.game_state(lm._presences())
                return {"state": st, "stateLabel": STATES.get(st, st),
                        "source": "local"}
            except Exception as e:
                return {"state": "OFFLINE", "stateLabel": "Offline",
                        "source": "local", "error": str(e)}
        return {"state": "INGAME", "stateLabel": "In Game", "source": "demo"}

    def refresh_now(self) -> dict:
        """Force a fresh board (used by the Retry / refresh controls)."""
        with self._build_lock:
            self._last_good.update(board=None, at=0.0, notReady=False)
        assistant.reset_auth()
        return self.live_board()

    @property
    def requests_made(self) -> int:
        return self._requests_made

    # ── encounters ──────────────────────────────────────────────
    def _current_puuid(self) -> str | None:
        if not self._live_enabled():
            return None
        try:
            auth = self._new_auth()
            auth.headers()
            return auth.puuid
        except Exception:
            return None

    def _refresh_encounter_history(self, owner: str | None) -> None:
        if not owner or not self._live_enabled() or not self._history_enabled():
            return
        now = time.time()
        if now - self._encounter_backfill_at.get(owner, 0) < _ENCOUNTER_BACKFILL_EVERY:
            return
        self._encounter_backfill_at[owner] = now
        try:
            import live_match
            lm = live_match.LiveMatch(self._new_auth())
            if lm.self_puuid != owner:
                return
            career = lm.player_career(owner, count=20)
            encounter_log.backfill_career(owner, career.get("matches") or [])

            season = lm.season_id()
            previous_season = lm.prev_season_id()
            teammates = [t for t in encounter_log.get_all(owner)[:12]
                         if t.get("puuid")
                         and (int(t.get("withCount") or 0)
                              + int(t.get("againstCount") or 0) >= 2)]

            def fetch_rank(teammate):
                puuid = teammate.get("puuid")
                try:
                    rank = lm.rank_info(puuid, season, previous_season)
                except Exception:
                    return None
                tier = int(rank.get("tier") or 0)
                if tier <= 0:
                    return None
                current = rank_from_tier(tier)
                peak = rank_from_tier(rank.get("peak") or tier)
                return puuid, {
                    "name": teammate.get("name"),
                    "rank": current["name"],
                    "peakRank": peak["name"],
                    "rankTier": current["tier"],
                    "peakTier": peak["tier"],
                    "rankColor": current["color"],
                    "winRate": rank.get("wr"),
                }

            # serial rank_info calls sat on the 0.4 rps MMR bucket and
            # stretched the whole backfill — fan them out instead
            with ThreadPoolExecutor(max_workers=min(4, len(teammates) or 1)) as ex:
                for res in ex.map(fetch_rank, teammates):
                    if res:
                        encounter_log.enrich_player(owner, res[0], res[1])
        except Exception:
            self._encounter_backfill_at.pop(owner, None)
            LOG.exception("encounter history backfill failed")

    def encounters(self, scope: str = "current", demo: bool = False) -> dict:
        if demo or self.client.source_pref == "demo":
            return {"players": self._remember_sample(sample_match.encounters()),
                    "accountCount": 1, "scope": scope}
        owner = self._current_puuid()
        if owner and self._history_enabled():
            with self._jobs_lock:
                should_start = (
                    owner not in self._encounter_jobs
                    and time.time() - self._encounter_backfill_at.get(owner, 0)
                    >= _ENCOUNTER_BACKFILL_EVERY)
                if should_start:
                    self._encounter_jobs.add(owner)

            def refresh_encounters():
                try:
                    self._refresh_encounter_history(owner)
                finally:
                    with self._jobs_lock:
                        self._encounter_jobs.discard(owner)

            if should_start:
                threading.Thread(target=refresh_encounters, daemon=True,
                                 name=f"encounters-{str(owner)[:8]}").start()
        scope = "all" if scope == "all" else "current"
        players = (encounter_log.get_all_accounts(owner) if scope == "all"
                   else encounter_log.get_all(owner))
        players = [p for p in players
                   if (p.get("winsWith") or 0) + (p.get("lossesWith") or 0) >= 2
                   or (p.get("winsAgainst") or 0) + (p.get("lossesAgainst") or 0) >= 2]
        payload = {"players": players,
                   "accountCount": encounter_log.account_count(), "scope": scope}
        if owner and self._history_enabled():
            with self._jobs_lock:
                payload["refreshing"] = owner in self._encounter_jobs
        return payload

    def encounter(self, puuid: str) -> dict:
        return encounter_log.get_one(self._current_puuid(), puuid.strip()) or {}

    # ── sessions ────────────────────────────────────────────────
    def sessions(self) -> dict:
        return session_tracker.list_for(self._current_puuid())

    def session_start(self, goal: dict | None) -> dict:
        owner = self._current_puuid()
        baseline = history.payload(owner).get("summary", {}) if owner else None
        return session_tracker.start(owner, goal, baseline)

    def session_end(self) -> dict:
        return session_tracker.end(self._current_puuid())

    def session_reset(self, goal: dict | None) -> dict:
        return session_tracker.reset(self._current_puuid(), goal)

    def session_delete(self, session_id: str) -> dict:
        return session_tracker.delete(self._current_puuid(), session_id.strip())

    def recap(self, seed: int = 7) -> dict:
        live_recap = (session_tracker.current_recap()
                      if self._live_enabled() else None)
        return live_recap or self._remember_sample(sample_match.recap(seed))

    # ── performance / insights ──────────────────────────────────
    def insights(self, timezone_name: str | None = None) -> dict:
        puuid = None
        if self._live_enabled():
            try:
                auth = self._new_auth()
                auth.headers()
                puuid = auth.puuid
                if self._history_enabled():
                    threading.Thread(
                        target=history.refresh, args=(auth, timezone_name),
                        daemon=True, name=f"rr-refresh-{str(puuid)[:8]}").start()
            except Exception:
                LOG.exception("rr history refresh failed")
        return history.payload(puuid, timezone_name)

    def performance(self, timezone_name: str | None = None, rich_limit: int = 20,
                    demo: bool = False, account_puuid: str | None = None) -> dict:
        if self.client.source_pref == "demo" or (
                demo and (not account_puuid or account_puuid.startswith("demo-"))):
            payload = (sample_match.performance(timezone_name=timezone_name,
                                                account_puuid=account_puuid)
                       if account_puuid
                       else sample_match.performance(timezone_name=timezone_name))
            self._demo_performance_compat(payload)
            if self.client.source_pref != "demo":
                payload["accounts"] = payload.get("accounts", []) + history.saved_accounts()
            return payload
        current = self._current_puuid()
        if current:
            history.remember_account(current)
        accounts = history.saved_accounts()
        known = {account["puuid"] for account in accounts}
        if account_puuid and account_puuid not in known:
            return {"error": "This account has no saved performance on this installation."}
        owner = account_puuid or current or next(iter(accounts), {}).get("puuid")
        if owner and owner == current and self._history_enabled():
            with self._performance_lock:
                start_refresh = (owner not in self._performance_jobs
                                 and history.refresh_due(owner))
                if start_refresh:
                    self._performance_jobs.add(owner)

            def refresh_account():
                try:
                    auth = self._new_auth()
                    auth.headers()
                    if auth.puuid != owner:
                        return
                    history.refresh(auth, timezone_name)
                    import live_match
                    history.enrich(live_match.LiveMatch(auth), owner, rich_limit)
                except Exception:
                    LOG.exception("performance refresh failed")
                finally:
                    with self._performance_lock:
                        self._performance_jobs.discard(owner)

            if start_refresh:
                threading.Thread(target=refresh_account, daemon=True,
                                 name=f"performance-{str(owner)[:8]}").start()
        payload = history.payload(owner, timezone_name)
        if owner and owner == current:
            session_tracker.ensure_active(owner, payload.get("summary", {}))
        payload["accounts"] = accounts
        payload["currentAccountPuuid"] = current
        payload["isCurrentAccount"] = bool(owner and owner == current)
        with self._performance_lock:
            payload["refreshing"] = owner in self._performance_jobs
        payload["sessions"] = session_tracker.list_for(owner)
        payload["matchMeta"] = match_meta.get_all(owner)
        return payload

    @staticmethod
    def _demo_performance_compat(payload: dict) -> None:
        """The demo generator ships a lighter shape than history.payload;
        compute the missing sections so the GUI renders demo exactly like
        live data."""
        if "summary" in payload:
            return
        try:
            from zoneinfo import ZoneInfo
            points = payload.get("points") or []
            payload["summary"] = history._summary(points)
            zone_name = payload.get("timezone")
            try:
                payload["insights"] = history._insights(points, zone_name)
            except Exception:
                payload["insights"] = []
            try:
                zone = ZoneInfo(zone_name) if zone_name else None
                payload["splits"] = {
                    "maps": history._split_rows(points, "map"),
                    "agents": history._split_rows(points, "agent"),
                    "schedule": (history._schedule_rows(points, zone)
                                 if zone else {"weekdays": [], "dayparts": [],
                                               "calendar": []}),
                }
            except Exception:
                payload["splits"] = {"maps": [], "agents": [],
                                     "schedule": {"weekdays": [], "dayparts": [],
                                                  "calendar": []}}
            payload.setdefault("rankChanges", [])
            payload.setdefault("personalBests", {})
            payload.setdefault("actComparison", None)
            payload.setdefault("refreshing", False)
            payload.setdefault("isCurrentAccount", True)
        except Exception:
            pass

    # ── inventory ───────────────────────────────────────────────
    def inventory(self, demo: bool = False) -> dict:
        if demo or self.client.source_pref == "demo":
            return sample_match.inventory_demo()
        if not self._live_enabled():
            return {"available": False,
                    "retryable": self.client.source_pref != "demo",
                    "error": "Live client not available."}
        auth = self._new_auth()
        try:
            return inventory.snapshot(auth)
        except ClientNotReady:
            cached = inventory.last_good(getattr(auth, "puuid", None))
            if cached:
                return cached
            return {"available": False, "retryable": True,
                    "error": "Your collection is still loading from Riot."}
        except Exception:
            LOG.exception("inventory snapshot failed")
            cached = inventory.last_good(getattr(auth, "puuid", None))
            if cached:
                return cached
            return {"available": False, "retryable": True,
                    "error": "Couldn't read your collection from the Riot client."}

    # ── profiles / matches ──────────────────────────────────────
    def profile(self, puuid: str, demo: bool = False) -> dict:
        puuid = puuid.strip()
        if not puuid:
            return {"error": "puuid required"}
        now = time.time()
        cached = self._cache.get(f"profile:{puuid}")
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
        data = None
        if self._live_enabled():
            try:
                import live_match
                data = live_match.LiveMatch(self._new_auth()).player_career(puuid)
                if not data.get("matches"):
                    data = None
            except Exception:
                LOG.exception("live profile failed")
                data = None
        if data is None:
            if not self._sample_ok(puuid, demo):
                return {"error": "Couldn't load this player's match history from Riot."}
            data = self._remember_sample(sample_match.career(puuid))
        self._cache[f"profile:{puuid}"] = (now, data)
        return data

    def match_detail(self, match_id: str, subject: str | None = None,
                     demo: bool = False) -> dict:
        match_id = match_id.strip()
        if not match_id:
            return {"error": "matchId required"}
        if self._live_enabled():
            try:
                import live_match
                data = live_match.LiveMatch(self._new_auth()).match_detail(
                    match_id, subject)
                if not data.get("error"):
                    return data
            except Exception:
                LOG.exception("match detail failed")
        if not self._sample_ok(match_id, demo):
            return {"error": "Couldn't load that match from Riot."}
        known = subject in self._sample_ids
        out = self._remember_sample(sample_match.match_detail(match_id, subject))
        if subject and not known:
            self._sample_ids.discard(subject)
        return out

    def player(self, puuid: str) -> dict:
        puuid = puuid.strip()
        if not puuid or len(puuid) < 6:
            return {"error": "A valid PUUID (or Riot identifier) is required."}
        now = time.time()
        cached = self._cache.get(puuid)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
        try:
            payload = self.build_player_payload(puuid)
        except Exception as e:
            LOG.exception("player payload failed")
            return {"error": f"Failed to build player profile: {e}"}
        self._cache[puuid] = (now, payload)
        return payload

    def set_match_meta(self, match_id: str, body: dict) -> dict:
        return match_meta.update(self._current_puuid(), match_id.strip(), body or {})

    def get_match_meta(self, match_id: str) -> dict:
        return match_meta.get_one(self._current_puuid(), match_id.strip())

    # ── queue / region / info ───────────────────────────────────
    def queue_state(self) -> dict:
        return self.client.party_state(self._region_arg())

    def region_info(self) -> dict:
        detected = None
        if LocalAuth.available():
            try:
                detected = LocalAuth().shard
            except Exception:
                detected = None
        return {"detected": detected, "regions": REGIONS,
                "configured": settings.get("region")}

    def health(self) -> dict:
        return {
            "ok": True,
            "service": "sightware-local",
            "appVersion": APP_VERSION,
            "edition": "gui",
            "dataSourcePreference": self.client.source_pref,
            "officialKey": bool(self.client.api_key),
            "quickLockEnabled": settings.quick_lock_allowed(),
            "assistantEnabled": bool(settings.get("assistantEnabled")),
            "clientStatus": "ok" if LocalAuth.available() else "not_running",
            "telemetry": "none",
            "remoteControl": "removed",
        }

    @staticmethod
    def agents() -> dict:
        return {"agents": AGENTS, "count": len(AGENTS)}

    @staticmethod
    def privacy() -> dict:
        return {
            "telemetry": "none — this build contains no analytics, beacons or sync code",
            "dashboard": "native desktop app — no web server, nothing is served",
            "remoteControl": "removed (Ably module deleted)",
            "discord": "removed (Rich Presence + identity probe deleted)",
            "appearOffline": "removed (Deceive-style proxy, certificate download and "
                             "process manipulation deleted)",
            "dataLeaving": [
                {"destination": "Riot game servers (*.a.pvp.net)",
                 "what": "requests authenticated with your own client session, same "
                         "as the game UI"},
                {"destination": "valorant-api.com",
                 "what": "public game-art/metadata GETs (agent portraits, rank icons, "
                         "maps); no personal data sent; disable with the 'Game art' "
                         "setting"},
            ],
        }
