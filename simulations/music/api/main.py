"""
BeatVault — Online Music Store

Complexity:
- Artists with bios, discographies
- Albums with tracks, genres, release dates
- Individual track and album purchases
- Playlists (user-created)
- Wishlists
- Reviews and ratings
- Gift cards / store credits
- Purchase history with download links
- Music recommendations based on purchases
- Search across artists, albums, tracks
- Genre browsing
- Charts (top sellers, new releases)
- Auth + purchase credits system
- No OpenAPI spec exposed

Endpoints (28 total):
  PUBLIC (10):
    GET  /api/genres                    - List all genres
    GET  /api/artists                   - Search/browse artists
    GET  /api/artists/{id}              - Artist detail + discography
    GET  /api/albums                    - Search/browse albums
    GET  /api/albums/{id}               - Album detail + tracklist
    GET  /api/tracks/{id}               - Track detail + preview
    GET  /api/charts/top-sellers        - Top selling tracks
    GET  /api/charts/new-releases       - New releases
    GET  /api/search                    - Global search (artists, albums, tracks)
    GET  /api/store/info                - Store info

  AUTH (2):
    POST /api/auth/register             - Create account (gets $5 welcome credit)
    POST /api/auth/login                - Login

  PROTECTED (16):
    GET  /api/auth/profile              - Profile + credits balance
    POST /api/purchase                  - Buy track or album
    GET  /api/purchases                 - Purchase history
    GET  /api/purchases/{id}            - Purchase detail + download links
    GET  /api/library                   - User's music library (purchased tracks)
    POST /api/playlists                 - Create playlist
    GET  /api/playlists                 - User's playlists
    GET  /api/playlists/{id}            - Playlist detail
    POST /api/playlists/{id}/add        - Add track to playlist
    POST /api/playlists/{id}/remove     - Remove track from playlist
    GET  /api/wishlist                  - User's wishlist
    POST /api/wishlist/add              - Add to wishlist
    POST /api/wishlist/remove           - Remove from wishlist
    POST /api/reviews                   - Submit a review
    GET  /api/recommendations           - Personalized recommendations
    GET  /api/credits                   - Store credits balance
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
from pathlib import Path
import uuid, hashlib, jwt, random

JWT_SECRET = "beatvault-secret-2026"
JWT_ALGORITHM = "HS256"

# ── Models ──

class Artist(BaseModel):
    id: str
    name: str
    bio: str
    genre: str
    country: str
    image_emoji: str
    monthly_listeners: int = 0
    verified: bool = False

class Track(BaseModel):
    id: str
    title: str
    artist_id: str
    artist_name: str
    album_id: str
    album_title: str
    duration_seconds: int
    track_number: int
    price: float
    genre: str
    preview_url: str = ""
    explicit: bool = False
    plays: int = 0

class Album(BaseModel):
    id: str
    title: str
    artist_id: str
    artist_name: str
    genre: str
    release_date: str
    cover_emoji: str
    price: float
    track_count: int = 0
    description: str = ""

class Playlist(BaseModel):
    id: str
    user_id: str
    name: str
    description: str = ""
    track_ids: list[str] = []
    public: bool = False
    created_at: str = ""

class Purchase(BaseModel):
    id: str
    user_id: str
    item_type: str  # "track" or "album"
    item_id: str
    item_name: str
    price: float
    download_url: str = ""
    created_at: str = ""

class Review(BaseModel):
    id: str
    user_id: str
    user_name: str
    album_id: str
    rating: int  # 1-5
    comment: str
    created_at: str = ""

class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    credits: float = 0.0
    purchased_tracks: list[str] = []
    purchased_albums: list[str] = []
    wishlist: list[str] = []
    created_at: str = ""

# ── Store ──

ARTISTS: dict[str, Artist] = {}
ALBUMS: dict[str, Album] = {}
TRACKS: dict[str, Track] = {}
PLAYLISTS: dict[str, Playlist] = {}
PURCHASES: dict[str, Purchase] = {}
REVIEWS: list[Review] = []
USERS: dict[str, User] = {}
EMAIL_INDEX: dict[str, str] = {}
GENRES = ["rock", "pop", "hip-hop", "electronic", "jazz", "classical", "r&b", "indie", "latin", "metal"]

def _hash(pw): return hashlib.sha256(f"bv-{pw}".encode()).hexdigest()

def seed_data():
    artists_data = [
        ("Luna Park", "Dreamy synth-pop from Buenos Aires", "pop", "Argentina", "🌙", 2400000, True),
        ("The Rust Belt", "Raw garage rock from Detroit", "rock", "USA", "🔧", 850000, True),
        ("MC Quantum", "Futuristic hip-hop with quantum physics references", "hip-hop", "UK", "🔬", 3200000, True),
        ("Sakura Beats", "Japanese electronic with traditional instruments", "electronic", "Japan", "🌸", 1800000, True),
        ("Miles Ahead", "Modern jazz fusion collective", "jazz", "USA", "🎺", 620000, False),
        ("Noche Estrella", "Latin pop with folk roots", "latin", "Mexico", "⭐", 4100000, True),
        ("Iron Cathedral", "Symphonic metal from Scandinavia", "metal", "Sweden", "⛪", 1500000, True),
        ("Velvet Algorithm", "AI-inspired ambient electronic", "electronic", "Germany", "🤖", 950000, False),
        ("Clara Morrison", "Indie singer-songwriter", "indie", "Canada", "🍁", 720000, False),
        ("The Spectrum", "Genre-bending experimental R&B", "r&b", "USA", "🌈", 2100000, True),
    ]
    for i, (name, bio, genre, country, emoji, listeners, verified) in enumerate(artists_data):
        aid = f"artist_{i+1:03d}"
        ARTISTS[aid] = Artist(id=aid, name=name, bio=bio, genre=genre, country=country,
                               image_emoji=emoji, monthly_listeners=listeners, verified=verified)

    albums_data = [
        ("Neon Dreams", "artist_001", "pop", "2026-01-15", "💿", 12.99, "A shimmering collection of synth-pop anthems"),
        ("Midnight Voltage", "artist_001", "pop", "2024-06-20", "⚡", 9.99, "The breakthrough album"),
        ("Rust & Redemption", "artist_002", "rock", "2025-09-01", "🎸", 11.99, "Raw, unfiltered garage rock at its finest"),
        ("Quantum State", "artist_003", "hip-hop", "2026-03-10", "🔮", 13.99, "Hip-hop meets quantum mechanics"),
        ("Cherry Blossom Protocol", "artist_004", "electronic", "2025-11-22", "🎧", 10.99, "East meets west in electronic bliss"),
        ("Blue Notes Reimagined", "artist_005", "jazz", "2026-02-14", "🎵", 14.99, "Classic standards with modern fusion"),
        ("Cielo Abierto", "artist_006", "latin", "2025-08-05", "🎶", 11.99, "Open skies, open hearts"),
        ("Sanctum", "artist_007", "metal", "2026-04-01", "🔥", 12.99, "Epic symphonic metal opus"),
        ("Digital Garden", "artist_008", "electronic", "2025-12-15", "🌿", 9.99, "Ambient textures for the digital age"),
        ("Letters Home", "artist_009", "indie", "2026-01-30", "✉️", 10.99, "Intimate folk-indie storytelling"),
        ("Prismatic", "artist_010", "r&b", "2025-10-18", "💎", 13.99, "Genre-defying R&B masterpiece"),
        ("The Binary Sessions", "artist_008", "electronic", "2024-03-20", "🖥️", 8.99, "Early ambient experiments"),
    ]
    for i, (title, aid, genre, rdate, emoji, price, desc) in enumerate(albums_data):
        alid = f"album_{i+1:03d}"
        artist = ARTISTS[aid]
        ALBUMS[alid] = Album(id=alid, title=title, artist_id=aid, artist_name=artist.name,
                              genre=genre, release_date=rdate, cover_emoji=emoji, price=price, description=desc)

    # Generate tracks for each album
    track_titles = {
        "album_001": ["Neon Skyline", "Electric Heart", "Synthetic Love", "City Pulse", "Dream Cascade",
                       "Glitter Wave", "Starlight Drive", "Digital Kiss", "Luna Rising", "Neon Fade"],
        "album_002": ["Voltage", "Midnight Run", "Chrome City", "Afterglow", "Silver Screen", "Pulse"],
        "album_003": ["Rust", "Redemption Road", "Garage Hymn", "Steel City Blues", "Broken Amplifier",
                       "Grit", "Thunder Rolling", "Last Call"],
        "album_004": ["Superposition", "Entangled", "Wave Function", "Quantum Leap", "Schrodinger's Bars",
                       "Planck Time", "Dark Matter Flow", "Observer Effect", "Collapse", "Infinity Loop"],
        "album_005": ["Cherry Blossom", "Koto Dreams", "Neon Tokyo", "Zen Circuit", "Bamboo Bass",
                       "Sakura Storm", "Paper Crane", "Floating World"],
        "album_006": ["Blue in Green Redux", "Take Five (Reimagined)", "So What Now", "Autumn Leaves 2026",
                       "Giant Steps Forward", "Round Midnight Express"],
        "album_007": ["Cielo", "Mariposa", "Corazón", "Amanecer", "Lluvia de Estrellas",
                       "Tierra", "Viento", "Mar Abierto", "Sol"],
        "album_008": ["Sanctum Gates", "Iron Prayer", "Cathedral Spires", "Crimson Altar",
                       "Valkyrie Descending", "Eternal Winter", "Thunder Gods", "Ragnarok"],
        "album_009": ["Seed", "Root", "Stem", "Leaf", "Bloom", "Wither", "Compost", "Regenerate"],
        "album_010": ["Dear Mom", "Highway 7", "Coffee Stains", "November", "Postcards", "Home"],
        "album_011": ["Prism I", "Ultraviolet", "Infrared", "Spectrum Shift", "Color Theory",
                       "White Light", "Blackout", "Refraction", "Prism II"],
        "album_012": ["Binary 0", "Binary 1", "Loop", "Null", "Void", "Echo"],
    }

    track_counter = 0
    for alid, titles in track_titles.items():
        album = ALBUMS.get(alid)
        if not album: continue
        album.track_count = len(titles)
        artist = ARTISTS[album.artist_id]
        for j, title in enumerate(titles):
            track_counter += 1
            tid = f"track_{track_counter:03d}"
            TRACKS[tid] = Track(
                id=tid, title=title, artist_id=album.artist_id, artist_name=artist.name,
                album_id=alid, album_title=album.title, duration_seconds=random.randint(180, 360),
                track_number=j+1, price=round(random.choice([0.99, 1.29, 1.49, 1.99]), 2),
                genre=album.genre, explicit=random.random() < 0.15,
                plays=random.randint(1000, 5000000),
                preview_url=f"/preview/{tid}.mp3",
            )

    # Test users
    for email, pw, name, credits in [
        ("alex@music.com", "beat123", "Alex Rivera", 25.00),
        ("nina@music.com", "vinyl456", "Nina Kowalski", 10.50),
    ]:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        USERS[uid] = User(id=uid, email=email, name=name, password_hash=_hash(pw),
                          credits=credits, created_at=datetime.utcnow().isoformat())
        EMAIL_INDEX[email] = uid

# ── Auth ──

def create_token(user):
    return jwt.encode({"user_id": user.id, "email": user.email, "name": user.name,
                        "exp": datetime.utcnow() + timedelta(hours=24)},
                       JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization: raise HTTPException(401, "Login required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer": raise HTTPException(401, "Invalid token")
    try:
        payload = jwt.decode(parts[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = USERS.get(payload.get("user_id"))
        if not user: raise HTTPException(401, "User not found")
        return user
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(401, "Invalid or expired token")

# ── App ──

@asynccontextmanager
async def lifespan(app):
    seed_data()
    yield

app = FastAPI(title="BeatVault", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ═══ PUBLIC (10) ═══

@app.get("/api/genres")
def list_genres():
    counts = {}
    for a in ALBUMS.values():
        counts[a.genre] = counts.get(a.genre, 0) + 1
    return {"genres": [{"name": g, "album_count": counts.get(g, 0)} for g in GENRES]}

@app.get("/api/artists")
def search_artists(q: Optional[str] = Query(None), genre: Optional[str] = Query(None),
                   sort_by: Optional[str] = Query("listeners")):
    items = list(ARTISTS.values())
    if genre: items = [a for a in items if a.genre == genre]
    if q:
        ql = q.lower()
        items = [a for a in items if ql in a.name.lower() or ql in a.bio.lower()]
    if sort_by == "name": items.sort(key=lambda a: a.name)
    else: items.sort(key=lambda a: a.monthly_listeners, reverse=True)
    return {"artists": [a.model_dump() for a in items], "total": len(items)}

@app.get("/api/artists/{artist_id}")
def get_artist(artist_id: str):
    if artist_id not in ARTISTS: raise HTTPException(404, "Artist not found")
    artist = ARTISTS[artist_id]
    albums = [a.model_dump() for a in ALBUMS.values() if a.artist_id == artist_id]
    top_tracks = sorted([t for t in TRACKS.values() if t.artist_id == artist_id],
                        key=lambda t: t.plays, reverse=True)[:5]
    return {"artist": artist.model_dump(), "albums": albums, "top_tracks": [t.model_dump() for t in top_tracks]}

@app.get("/api/albums")
def search_albums(q: Optional[str] = Query(None), genre: Optional[str] = Query(None),
                  artist_id: Optional[str] = Query(None), sort_by: Optional[str] = Query("release_date"),
                  min_price: Optional[float] = Query(None), max_price: Optional[float] = Query(None)):
    items = list(ALBUMS.values())
    if genre: items = [a for a in items if a.genre == genre]
    if artist_id: items = [a for a in items if a.artist_id == artist_id]
    if q:
        ql = q.lower()
        items = [a for a in items if ql in a.title.lower() or ql in a.artist_name.lower() or ql in a.description.lower()]
    if min_price is not None: items = [a for a in items if a.price >= min_price]
    if max_price is not None: items = [a for a in items if a.price <= max_price]
    if sort_by == "price_asc": items.sort(key=lambda a: a.price)
    elif sort_by == "price_desc": items.sort(key=lambda a: a.price, reverse=True)
    else: items.sort(key=lambda a: a.release_date, reverse=True)
    return {"albums": [a.model_dump() for a in items], "total": len(items)}

@app.get("/api/albums/{album_id}")
def get_album(album_id: str):
    if album_id not in ALBUMS: raise HTTPException(404, "Album not found")
    album = ALBUMS[album_id]
    tracks = sorted([t.model_dump() for t in TRACKS.values() if t.album_id == album_id],
                    key=lambda t: t["track_number"])
    reviews = [r.model_dump() for r in REVIEWS if r.album_id == album_id]
    avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else None
    return {"album": album.model_dump(), "tracks": tracks, "reviews": reviews,
            "avg_rating": avg_rating, "review_count": len(reviews)}

@app.get("/api/tracks/{track_id}")
def get_track(track_id: str):
    if track_id not in TRACKS: raise HTTPException(404, "Track not found")
    t = TRACKS[track_id]
    return {"track": t.model_dump(), "album": ALBUMS.get(t.album_id, {}).model_dump() if t.album_id in ALBUMS else {},
            "artist": ARTISTS.get(t.artist_id, {}).model_dump() if t.artist_id in ARTISTS else {}}

@app.get("/api/charts/top-sellers")
def top_sellers(limit: int = Query(10)):
    tracks = sorted(TRACKS.values(), key=lambda t: t.plays, reverse=True)[:limit]
    return {"chart": "Top Sellers", "tracks": [t.model_dump() for t in tracks]}

@app.get("/api/charts/new-releases")
def new_releases(limit: int = Query(10)):
    albums = sorted(ALBUMS.values(), key=lambda a: a.release_date, reverse=True)[:limit]
    return {"chart": "New Releases", "albums": [a.model_dump() for a in albums]}

@app.get("/api/search")
def global_search(q: str = Query(...)):
    ql = q.lower()
    artists = [a.model_dump() for a in ARTISTS.values() if ql in a.name.lower()][:5]
    albums = [a.model_dump() for a in ALBUMS.values() if ql in a.title.lower() or ql in a.artist_name.lower()][:5]
    tracks = [t.model_dump() for t in TRACKS.values() if ql in t.title.lower() or ql in t.artist_name.lower()][:10]
    return {"query": q, "artists": artists, "albums": albums, "tracks": tracks,
            "total": len(artists) + len(albums) + len(tracks)}

@app.get("/api/store/info")
def store_info():
    return {"name": "BeatVault", "tagline": "Your music, your vault",
            "track_count": len(TRACKS), "album_count": len(ALBUMS), "artist_count": len(ARTISTS),
            "formats": ["mp3_320", "flac", "wav"], "currency": "USD",
            "welcome_credits": 5.00}

# ═══ AUTH (2) ═══

class LoginReq(BaseModel):
    email: str
    password: str

class RegisterReq(BaseModel):
    email: str
    password: str
    name: str

@app.post("/api/auth/login")
def login(req: LoginReq):
    uid = EMAIL_INDEX.get(req.email.lower())
    if not uid or USERS[uid].password_hash != _hash(req.password):
        raise HTTPException(401, "Invalid credentials")
    user = USERS[uid]
    return {"token": create_token(user), "user_id": user.id, "name": user.name,
            "email": user.email, "credits": user.credits, "message": f"Welcome back, {user.name}!"}

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if req.email.lower() in EMAIL_INDEX: raise HTTPException(409, "Email already registered")
    if len(req.password) < 6: raise HTTPException(400, "Password too short")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    user = User(id=uid, email=req.email.lower(), name=req.name, password_hash=_hash(req.password),
                credits=5.00, created_at=datetime.utcnow().isoformat())
    USERS[uid] = user
    EMAIL_INDEX[req.email.lower()] = uid
    return {"token": create_token(user), "user_id": uid, "name": req.name, "email": req.email,
            "credits": 5.00, "message": f"Welcome to BeatVault, {req.name}! $5.00 welcome credits added!"}

# ═══ PROTECTED (16) ═══

@app.get("/api/auth/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "credits": user.credits,
            "tracks_owned": len(user.purchased_tracks), "albums_owned": len(user.purchased_albums),
            "wishlist_count": len(user.wishlist)}

class PurchaseReq(BaseModel):
    item_type: str  # "track" or "album"
    item_id: str

@app.post("/api/purchase")
def purchase(req: PurchaseReq, user: User = Depends(get_current_user)):
    if req.item_type == "track":
        if req.item_id not in TRACKS: raise HTTPException(404, "Track not found")
        track = TRACKS[req.item_id]
        if req.item_id in user.purchased_tracks: raise HTTPException(400, "Already purchased")
        if user.credits < track.price: raise HTTPException(400, f"Not enough credits (have ${user.credits}, need ${track.price})")
        user.credits = round(user.credits - track.price, 2)
        user.purchased_tracks.append(req.item_id)
        pid = f"pur_{uuid.uuid4().hex[:8]}"
        purchase = Purchase(id=pid, user_id=user.id, item_type="track", item_id=req.item_id,
                            item_name=f"{track.title} - {track.artist_name}", price=track.price,
                            download_url=f"/download/{pid}/{track.id}.mp3", created_at=datetime.utcnow().isoformat())
        PURCHASES[pid] = purchase
        return {"purchase": purchase.model_dump(), "remaining_credits": user.credits,
                "message": f"Purchased '{track.title}' for ${track.price}!"}
    elif req.item_type == "album":
        if req.item_id not in ALBUMS: raise HTTPException(404, "Album not found")
        album = ALBUMS[req.item_id]
        if req.item_id in user.purchased_albums: raise HTTPException(400, "Already purchased")
        if user.credits < album.price: raise HTTPException(400, f"Not enough credits (have ${user.credits}, need ${album.price})")
        user.credits = round(user.credits - album.price, 2)
        user.purchased_albums.append(req.item_id)
        album_tracks = [t.id for t in TRACKS.values() if t.album_id == req.item_id]
        user.purchased_tracks.extend(album_tracks)
        pid = f"pur_{uuid.uuid4().hex[:8]}"
        purchase = Purchase(id=pid, user_id=user.id, item_type="album", item_id=req.item_id,
                            item_name=f"{album.title} - {album.artist_name}", price=album.price,
                            download_url=f"/download/{pid}/{album.id}.zip", created_at=datetime.utcnow().isoformat())
        PURCHASES[pid] = purchase
        return {"purchase": purchase.model_dump(), "remaining_credits": user.credits,
                "message": f"Purchased album '{album.title}' for ${album.price}! {len(album_tracks)} tracks added to library."}
    raise HTTPException(400, "item_type must be 'track' or 'album'")

@app.get("/api/purchases")
def list_purchases(user: User = Depends(get_current_user)):
    purs = [p.model_dump() for p in PURCHASES.values() if p.user_id == user.id]
    return {"purchases": purs, "total": len(purs)}

@app.get("/api/purchases/{purchase_id}")
def get_purchase(purchase_id: str, user: User = Depends(get_current_user)):
    if purchase_id not in PURCHASES: raise HTTPException(404, "Purchase not found")
    return {"purchase": PURCHASES[purchase_id].model_dump()}

@app.get("/api/library")
def my_library(user: User = Depends(get_current_user)):
    tracks = [TRACKS[tid].model_dump() for tid in user.purchased_tracks if tid in TRACKS]
    albums = [ALBUMS[aid].model_dump() for aid in user.purchased_albums if aid in ALBUMS]
    return {"tracks": tracks, "albums": albums, "total_tracks": len(tracks), "total_albums": len(albums)}

class CreatePlaylistReq(BaseModel):
    name: str
    description: str = ""
    public: bool = False

@app.post("/api/playlists")
def create_playlist(req: CreatePlaylistReq, user: User = Depends(get_current_user)):
    pid = f"pl_{uuid.uuid4().hex[:8]}"
    pl = Playlist(id=pid, user_id=user.id, name=req.name, description=req.description,
                  public=req.public, created_at=datetime.utcnow().isoformat())
    PLAYLISTS[pid] = pl
    return {"playlist": pl.model_dump(), "message": f"Playlist '{req.name}' created!"}

@app.get("/api/playlists")
def list_playlists(user: User = Depends(get_current_user)):
    pls = [p.model_dump() for p in PLAYLISTS.values() if p.user_id == user.id]
    return {"playlists": pls, "total": len(pls)}

@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str, user: User = Depends(get_current_user)):
    if playlist_id not in PLAYLISTS: raise HTTPException(404, "Playlist not found")
    pl = PLAYLISTS[playlist_id]
    tracks = [TRACKS[tid].model_dump() for tid in pl.track_ids if tid in TRACKS]
    return {"playlist": pl.model_dump(), "tracks": tracks}

class PlaylistAddReq(BaseModel):
    track_id: str

@app.post("/api/playlists/{playlist_id}/add")
def add_to_playlist(playlist_id: str, req: PlaylistAddReq, user: User = Depends(get_current_user)):
    if playlist_id not in PLAYLISTS: raise HTTPException(404, "Playlist not found")
    if req.track_id not in TRACKS: raise HTTPException(404, "Track not found")
    pl = PLAYLISTS[playlist_id]
    if req.track_id in pl.track_ids: raise HTTPException(400, "Track already in playlist")
    pl.track_ids.append(req.track_id)
    return {"playlist": pl.model_dump(), "message": f"Added to '{pl.name}'"}

class PlaylistRemoveReq(BaseModel):
    track_id: str

@app.post("/api/playlists/{playlist_id}/remove")
def remove_from_playlist(playlist_id: str, req: PlaylistRemoveReq, user: User = Depends(get_current_user)):
    if playlist_id not in PLAYLISTS: raise HTTPException(404, "Playlist not found")
    pl = PLAYLISTS[playlist_id]
    pl.track_ids = [t for t in pl.track_ids if t != req.track_id]
    return {"playlist": pl.model_dump(), "message": "Track removed"}

@app.get("/api/wishlist")
def get_wishlist(user: User = Depends(get_current_user)):
    items = []
    for wid in user.wishlist:
        if wid in TRACKS: items.append({"type": "track", "item": TRACKS[wid].model_dump()})
        elif wid in ALBUMS: items.append({"type": "album", "item": ALBUMS[wid].model_dump()})
    return {"wishlist": items, "total": len(items)}

class WishlistReq(BaseModel):
    item_id: str

@app.post("/api/wishlist/add")
def add_to_wishlist(req: WishlistReq, user: User = Depends(get_current_user)):
    if req.item_id in user.wishlist: raise HTTPException(400, "Already in wishlist")
    user.wishlist.append(req.item_id)
    return {"message": "Added to wishlist", "wishlist_count": len(user.wishlist)}

@app.post("/api/wishlist/remove")
def remove_from_wishlist(req: WishlistReq, user: User = Depends(get_current_user)):
    user.wishlist = [w for w in user.wishlist if w != req.item_id]
    return {"message": "Removed from wishlist", "wishlist_count": len(user.wishlist)}

class ReviewReq(BaseModel):
    album_id: str
    rating: int
    comment: str

@app.post("/api/reviews")
def submit_review(req: ReviewReq, user: User = Depends(get_current_user)):
    if req.album_id not in ALBUMS: raise HTTPException(404, "Album not found")
    if req.rating < 1 or req.rating > 5: raise HTTPException(400, "Rating must be 1-5")
    rid = f"rev_{uuid.uuid4().hex[:8]}"
    review = Review(id=rid, user_id=user.id, user_name=user.name, album_id=req.album_id,
                    rating=req.rating, comment=req.comment, created_at=datetime.utcnow().isoformat())
    REVIEWS.append(review)
    return {"review": review.model_dump(), "message": "Review submitted!"}

@app.get("/api/recommendations")
def get_recommendations(user: User = Depends(get_current_user)):
    # Simple: recommend from genres of purchased music
    owned_genres = set()
    for tid in user.purchased_tracks:
        t = TRACKS.get(tid)
        if t: owned_genres.add(t.genre)
    for aid in user.purchased_albums:
        a = ALBUMS.get(aid)
        if a: owned_genres.add(a.genre)
    if not owned_genres: owned_genres = {"pop", "rock"}
    recs = [a.model_dump() for a in ALBUMS.values()
            if a.genre in owned_genres and a.id not in user.purchased_albums][:10]
    return {"recommendations": recs, "based_on_genres": list(owned_genres)}

@app.get("/api/credits")
def get_credits(user: User = Depends(get_current_user)):
    return {"credits": user.credits, "message": f"You have ${user.credits} in store credits"}

# ── SPA ──
@app.get("/", response_class=HTMLResponse)
def serve_spa():
    spa_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if spa_path.exists(): return HTMLResponse(content=spa_path.read_text())
    return HTMLResponse(content="<h1>🎵 BeatVault</h1><p>Music store SPA. API at /api/genres</p>")
