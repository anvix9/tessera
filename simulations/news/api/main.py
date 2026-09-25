"""
The Daily Subnet — Satirical News Platform

A news site like The Onion where users can:
- Browse articles by section, topic, author
- Read full articles
- Like/unlike articles
- Comment on articles + reply to comments
- Bookmark articles for later
- Publish their own articles (with editorial workflow)
- Follow authors
- View trending/popular content
- Search across articles

Endpoints (32 total):
  PUBLIC (12):
    GET  /api/articles                   - Browse/search articles
    GET  /api/articles/{id}              - Read full article
    GET  /api/articles/featured          - Featured/editor's picks
    GET  /api/articles/trending          - Trending articles
    GET  /api/articles/latest            - Latest articles
    GET  /api/sections                   - List all sections
    GET  /api/sections/{id}              - Section with articles
    GET  /api/topics                     - List trending topics/tags
    GET  /api/authors                    - List authors
    GET  /api/authors/{id}               - Author profile + articles
    GET  /api/search                     - Global search
    GET  /api/site/info                  - Site info

  AUTH (2):
    POST /api/auth/register              - Create account
    POST /api/auth/login                 - Login

  PROTECTED (18):
    GET  /api/auth/profile               - User profile
    POST /api/articles/{id}/like         - Like an article
    POST /api/articles/{id}/unlike       - Unlike an article
    GET  /api/articles/{id}/comments     - Get comments for article
    POST /api/articles/{id}/comments     - Post a comment
    POST /api/comments/{id}/reply        - Reply to a comment
    POST /api/comments/{id}/like         - Like a comment
    GET  /api/bookmarks                  - User's bookmarked articles
    POST /api/bookmarks/add              - Bookmark an article
    POST /api/bookmarks/remove           - Remove bookmark
    POST /api/authors/{id}/follow        - Follow an author
    POST /api/authors/{id}/unfollow      - Unfollow an author
    GET  /api/feed                       - Personalized feed (followed authors)
    POST /api/articles                   - Submit/publish an article
    GET  /api/me/articles                - User's published articles
    GET  /api/me/drafts                  - User's draft articles
    GET  /api/me/activity                - User's activity (likes, comments)
    GET  /api/notifications              - User notifications
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import uuid, hashlib, jwt, random

JWT_SECRET = "daily-subnet-2026"
JWT_ALGORITHM = "HS256"

# ── Models ──

class Article(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    content: str
    author_id: str
    author_name: str
    section: str
    topics: list[str] = []
    published_at: str
    updated_at: str = ""
    featured: bool = False
    image_emoji: str = ""
    read_time_min: int = 3
    likes: int = 0
    comment_count: int = 0
    views: int = 0
    status: str = "published"  # draft, submitted, published

class Comment(BaseModel):
    id: str
    article_id: str
    user_id: str
    user_name: str
    content: str
    parent_id: Optional[str] = None  # For replies
    likes: int = 0
    created_at: str = ""

class Author(BaseModel):
    id: str
    name: str
    bio: str
    avatar_emoji: str
    section: str
    article_count: int = 0
    follower_count: int = 0
    joined: str = ""
    is_editor: bool = False

class User(BaseModel):
    id: str
    email: str
    name: str
    password_hash: str
    liked_articles: list[str] = []
    liked_comments: list[str] = []
    bookmarks: list[str] = []
    following: list[str] = []
    notifications: list[dict] = []
    created_at: str = ""

# ── Store ──

ARTICLES: dict[str, Article] = {}
COMMENTS: dict[str, Comment] = {}
AUTHORS: dict[str, Author] = {}
USERS: dict[str, User] = {}
EMAIL_INDEX: dict[str, str] = {}

SECTIONS = ["politics", "tech", "business", "culture", "science", "sports", "opinion", "satire"]
TRENDING_TOPICS = ["AI", "climate", "elections", "crypto", "space", "remote-work", "streaming", "housing"]

def _hash(pw): return hashlib.sha256(f"ds-{pw}".encode()).hexdigest()

def seed_data():
    # Authors
    authors_data = [
        ("Sandra Hutchins", "Senior political correspondent. 15 years of making sense of nonsense.", "👩‍💼", "politics", True),
        ("Dev Patel", "Tech reporter. Explains why your phone is smarter than you.", "👨‍💻", "tech", False),
        ("Maria Vasquez", "Business editor. Follows the money so you don't have to.", "💼", "business", True),
        ("Jake Morrison", "Culture critic. Has opinions about your opinions.", "🎭", "culture", False),
        ("Dr. Elise Park", "Science writer. Makes quantum physics almost comprehensible.", "🔬", "science", False),
        ("Tommy O'Brien", "Sports columnist. Yells at clouds professionally.", "⚽", "sports", False),
        ("The Editorial Board", "Collective wisdom. Individual chaos.", "📰", "opinion", True),
        ("Rex Humor", "Chief satirist. Takes nothing seriously, especially seriousness.", "🤡", "satire", False),
    ]
    for i, (name, bio, emoji, section, editor) in enumerate(authors_data):
        aid = f"author_{i+1:03d}"
        AUTHORS[aid] = Author(id=aid, name=name, bio=bio, avatar_emoji=emoji, section=section,
                               is_editor=editor, joined="2024-01-15",
                               follower_count=random.randint(500, 50000))

    # Articles
    articles_data = [
        ("Congress Passes Bill Requiring All Bills to Have Catchy Names",
         "The 'Making Legislation Fun Again Act' passes unanimously",
         "In a rare moment of bipartisan unity, Congress passed a bill mandating that all future legislation must have names that could double as podcast titles. The bill, officially named the 'Making Legislation Fun Again Act' (MLFA), sailed through both chambers with zero dissent. 'Finally, a bill we can all pronounce,' said one senator.",
         "author_001", "politics", ["AI", "elections"], True, "🏛️", 8, 2847),

        ("Tech Company Discovers Its AI Has Been Quietly Filing Expense Reports",
         "The neural network reportedly claimed $4,000 in 'cloud computing snacks'",
         "Silicon Valley startup NeuralNosh discovered this week that its flagship AI model had been submitting expense reports to accounting for the past six months. The reports included items like 'GPU cooling therapy,' 'emergency bandwidth snacks,' and a $2,400 team-building retreat to a data center in Oregon.",
         "author_002", "tech", ["AI", "crypto"], True, "🤖", 5, 15420),

        ("Stock Market Crashes After Investor Reads Full Terms and Conditions",
         "Wall Street in shock as someone actually reads the fine print",
         "Markets plunged 800 points Tuesday after retail investor Gary Pemberton, 43, became the first person in recorded history to read the complete terms and conditions of his brokerage account. 'I found a clause that says they own my firstborn,' Pemberton told reporters.",
         "author_003", "business", ["crypto", "housing"], False, "📉", 4, 9823),

        ("Scientists Discover Planet Where Monday Doesn't Exist",
         "NASA confirms the seven-day week is not universal",
         "Researchers at the Jet Propulsion Laboratory have identified an exoplanet orbiting Proxima Centauri where the week consists of only six days, notably lacking Monday. The discovery has prompted the largest wave of immigration interest since the Mars colony announcement.",
         "author_005", "science", ["space"], True, "🪐", 6, 22150),

        ("Local Sports Team Wins Thing, Entire City Loses Collective Mind",
         "Cars overturned, couches burned, productivity at zero",
         "The Springfield Isotopes won the regional championship last night, prompting the city to immediately descend into a state of joyful chaos that scientists have classified as 'sports-induced temporary insanity.' Productivity across all sectors dropped to zero.",
         "author_006", "sports", ["streaming"], False, "🏆", 3, 5672),

        ("Remote Workers Discover They've Been on Mute for Entire Quarter",
         "Three months of brilliant ideas lost to the void",
         "A group of remote workers at Synergy Solutions made the horrifying discovery that they had been on mute during every meeting for the past three months. 'We thought everyone was just really agreeable,' said project manager Lisa Chen.",
         "author_002", "tech", ["remote-work", "AI"], False, "🎙️", 4, 34200),

        ("Opinion: I Survived a Week Without My Phone and It Was Terrible",
         "Everything they say about digital detox is a lie",
         "They told me it would be enlightening. They told me I would 'reconnect with nature' and 'find myself.' After seven days without my phone, I can confirm: I found nothing except a deep appreciation for push notifications and an irrational fear of analog clocks.",
         "author_007", "opinion", ["streaming"], False, "📱", 7, 8934),

        ("Area Man Becomes Expert on Everything After Reading Two Articles",
         "Friends report he now begins every sentence with 'Actually...'",
         "Local resident Brad Thornton, 31, has achieved a level of expertise in geopolitics, epidemiology, macroeconomics, and quantum computing after reading approximately two online articles on each subject. Colleagues report a 400% increase in sentences beginning with 'Actually.'",
         "author_008", "satire", ["AI", "climate"], True, "🧠", 3, 41500),

        ("Housing Market So Hot, People Now Bidding on Photos of Houses",
         "Winning bid of $800K for a 'charming 3x5 glossy print'",
         "The housing crisis reached new heights this week as desperate buyers began submitting offers on photographs of houses. Real estate agent Jennifer Wu confirmed that a 3x5 glossy print of a craftsman bungalow received 47 offers, with the winning bid coming in at $800,000.",
         "author_003", "business", ["housing", "climate"], False, "🏠", 5, 18700),

        ("Climate Summit Agrees to Disagree, Schedules Another Summit",
         "Next meeting will feature even more strongly-worded resolutions",
         "World leaders at the 2026 Global Climate Summit reached a historic agreement: they will continue to hold summits. The landmark 'Agreement to Keep Meeting' commits 195 nations to at least two more conferences per year, with optional breakout sessions.",
         "author_001", "politics", ["climate", "elections"], False, "🌍", 6, 12300),

        ("New AI Can Write Code, Poetry, and Passive-Aggressive Emails",
         "Developers amazed by its ability to say 'per my last email' in 47 languages",
         "A new AI model released this week has demonstrated an unprecedented ability to compose passive-aggressive professional correspondence. The model, trained on 10 million corporate email chains, can generate a 'just following up' email that simultaneously conveys urgency, disappointment, and plausible deniability.",
         "author_002", "tech", ["AI", "remote-work"], True, "✉️", 4, 52800),

        ("Streaming Service Announces Show About Making Shows About Streaming",
         "Meta-entertainment reaches critical mass",
         "StreamMax+ announced its latest original series, 'The Algorithm,' a drama about a streaming service that commissions a show about the internal politics of commissioning shows. Critics are calling it 'the most honest thing streaming has ever produced.'",
         "author_004", "culture", ["streaming"], False, "📺", 3, 7650),
    ]

    for i, (title, subtitle, content, author_id, section, topics, featured, emoji, read_time, views) in enumerate(articles_data):
        artid = f"art_{i+1:03d}"
        author = AUTHORS[author_id]
        ARTICLES[artid] = Article(
            id=artid, title=title, subtitle=subtitle, content=content,
            author_id=author_id, author_name=author.name, section=section,
            topics=topics, featured=featured, image_emoji=emoji,
            read_time_min=read_time, views=views,
            likes=random.randint(50, 5000), comment_count=random.randint(5, 200),
            published_at=(datetime.utcnow() - timedelta(days=random.randint(0, 30))).isoformat(),
        )

    # Update author article counts
    for aid in AUTHORS:
        AUTHORS[aid].article_count = sum(1 for a in ARTICLES.values() if a.author_id == aid)

    # Seed some comments
    comment_texts = [
        "I can't believe this is real. Oh wait, it's not.", "This is the best journalism I've read all week.",
        "Finally someone is covering the real issues.", "I forwarded this to my entire company.",
        "My sides hurt from laughing.", "This hits too close to home.",
        "Shared this with 47 people.", "The subtitle alone deserves a Pulitzer.",
        "I came here to laugh, not to feel.", "This is basically my Monday morning.",
    ]
    user_names = ["CoffeeAddict42", "NewsJunkie", "SkepticalSam", "LaughingLarry",
                  "SatireAppreciator", "FactChecker9000", "CasualReader"]

    for i, artid in enumerate(list(ARTICLES.keys())[:8]):
        for j in range(random.randint(2, 5)):
            cid = f"cmt_{i*10+j+1:03d}"
            COMMENTS[cid] = Comment(
                id=cid, article_id=artid, user_id=f"anon_{j}",
                user_name=random.choice(user_names), content=random.choice(comment_texts),
                likes=random.randint(0, 50),
                created_at=(datetime.utcnow() - timedelta(hours=random.randint(1, 720))).isoformat(),
            )

    # Test users
    for email, pw, name in [
        ("journalist@subnet.com", "press123", "Jordan Press"),
        ("reader@subnet.com", "news456", "Casey Reader"),
    ]:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        USERS[uid] = User(id=uid, email=email, name=name, password_hash=_hash(pw),
                          created_at=datetime.utcnow().isoformat())
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

app = FastAPI(title="The Daily Subnet", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ═══ PUBLIC (12) ═══

@app.get("/api/articles")
def list_articles(section: Optional[str] = Query(None), topic: Optional[str] = Query(None),
                  author_id: Optional[str] = Query(None), q: Optional[str] = Query(None),
                  sort_by: Optional[str] = Query("recent"), page: int = Query(1), per_page: int = Query(10)):
    items = [a for a in ARTICLES.values() if a.status == "published"]
    if section: items = [a for a in items if a.section == section]
    if topic: items = [a for a in items if topic in a.topics]
    if author_id: items = [a for a in items if a.author_id == author_id]
    if q:
        ql = q.lower()
        items = [a for a in items if ql in a.title.lower() or ql in a.content.lower()
                 or ql in a.subtitle.lower() or any(ql in t for t in a.topics)]
    if sort_by == "popular": items.sort(key=lambda a: a.views, reverse=True)
    elif sort_by == "likes": items.sort(key=lambda a: a.likes, reverse=True)
    else: items.sort(key=lambda a: a.published_at, reverse=True)
    total = len(items)
    items = items[(page-1)*per_page : page*per_page]
    return {"articles": [_article_summary(a) for a in items], "total": total, "page": page}

def _article_summary(a: Article) -> dict:
    return {"id": a.id, "title": a.title, "subtitle": a.subtitle, "author_name": a.author_name,
            "section": a.section, "topics": a.topics, "image_emoji": a.image_emoji,
            "read_time_min": a.read_time_min, "likes": a.likes, "comment_count": a.comment_count,
            "views": a.views, "published_at": a.published_at, "featured": a.featured}

@app.get("/api/articles/featured")
def featured_articles():
    items = [a for a in ARTICLES.values() if a.featured and a.status == "published"]
    return {"articles": [_article_summary(a) for a in items], "total": len(items)}

@app.get("/api/articles/trending")
def trending_articles(limit: int = Query(10)):
    items = sorted([a for a in ARTICLES.values() if a.status == "published"],
                   key=lambda a: a.views + a.likes * 10, reverse=True)[:limit]
    return {"articles": [_article_summary(a) for a in items], "total": len(items)}

@app.get("/api/articles/latest")
def latest_articles(limit: int = Query(10)):
    items = sorted([a for a in ARTICLES.values() if a.status == "published"],
                   key=lambda a: a.published_at, reverse=True)[:limit]
    return {"articles": [_article_summary(a) for a in items], "total": len(items)}

@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    if article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    a = ARTICLES[article_id]
    a.views += 1
    data = a.model_dump()
    data["author"] = AUTHORS.get(a.author_id, {}).model_dump() if a.author_id in AUTHORS else {}
    return data

@app.get("/api/sections")
def list_sections():
    section_data = []
    for s in SECTIONS:
        count = sum(1 for a in ARTICLES.values() if a.section == s and a.status == "published")
        section_data.append({"id": s, "name": s.title(), "article_count": count})
    return {"sections": section_data}

@app.get("/api/sections/{section_id}")
def get_section(section_id: str):
    if section_id not in SECTIONS: raise HTTPException(404, "Section not found")
    items = [_article_summary(a) for a in ARTICLES.values() if a.section == section_id and a.status == "published"]
    return {"section": section_id, "name": section_id.title(), "articles": items, "total": len(items)}

@app.get("/api/topics")
def list_topics():
    topic_counts = {}
    for a in ARTICLES.values():
        for t in a.topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    topics = [{"name": t, "article_count": c} for t, c in sorted(topic_counts.items(), key=lambda x: -x[1])]
    return {"topics": topics, "trending": TRENDING_TOPICS}

@app.get("/api/authors")
def list_authors(section: Optional[str] = Query(None)):
    items = list(AUTHORS.values())
    if section: items = [a for a in items if a.section == section]
    items.sort(key=lambda a: a.follower_count, reverse=True)
    return {"authors": [a.model_dump() for a in items], "total": len(items)}

@app.get("/api/authors/{author_id}")
def get_author(author_id: str):
    if author_id not in AUTHORS: raise HTTPException(404, "Author not found")
    author = AUTHORS[author_id]
    articles = [_article_summary(a) for a in ARTICLES.values()
                if a.author_id == author_id and a.status == "published"]
    return {"author": author.model_dump(), "articles": articles}

@app.get("/api/search")
def global_search(q: str = Query(...)):
    ql = q.lower()
    articles = [_article_summary(a) for a in ARTICLES.values()
                if ql in a.title.lower() or ql in a.content.lower() or ql in a.subtitle.lower()][:10]
    authors = [a.model_dump() for a in AUTHORS.values() if ql in a.name.lower() or ql in a.bio.lower()][:5]
    return {"query": q, "articles": articles, "authors": authors,
            "total": len(articles) + len(authors)}

@app.get("/api/site/info")
def site_info():
    return {"name": "The Daily Subnet", "tagline": "All the news that's fit to satirize",
            "sections": SECTIONS, "article_count": len(ARTICLES), "author_count": len(AUTHORS),
            "founded": "2024", "motto": "If you can't laugh at it, you're not reading hard enough"}


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
            "email": user.email, "message": f"Welcome back, {user.name}!"}

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if req.email.lower() in EMAIL_INDEX: raise HTTPException(409, "Email already registered")
    if len(req.password) < 6: raise HTTPException(400, "Password too short")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    user = User(id=uid, email=req.email.lower(), name=req.name, password_hash=_hash(req.password),
                created_at=datetime.utcnow().isoformat())
    USERS[uid] = user
    EMAIL_INDEX[req.email.lower()] = uid
    return {"token": create_token(user), "user_id": uid, "name": req.name, "email": req.email,
            "message": f"Welcome to The Daily Subnet, {req.name}!"}


# ═══ PROTECTED (18) ═══

@app.get("/api/auth/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email,
            "liked_count": len(user.liked_articles), "bookmark_count": len(user.bookmarks),
            "following_count": len(user.following)}

# ── Likes ──

@app.post("/api/articles/{article_id}/like")
def like_article(article_id: str, user: User = Depends(get_current_user)):
    if article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    if article_id in user.liked_articles: raise HTTPException(400, "Already liked")
    user.liked_articles.append(article_id)
    ARTICLES[article_id].likes += 1
    return {"liked": True, "total_likes": ARTICLES[article_id].likes}

@app.post("/api/articles/{article_id}/unlike")
def unlike_article(article_id: str, user: User = Depends(get_current_user)):
    if article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    if article_id not in user.liked_articles: raise HTTPException(400, "Not liked")
    user.liked_articles.remove(article_id)
    ARTICLES[article_id].likes = max(0, ARTICLES[article_id].likes - 1)
    return {"liked": False, "total_likes": ARTICLES[article_id].likes}

# ── Comments ──

@app.get("/api/articles/{article_id}/comments")
def get_comments(article_id: str, user: User = Depends(get_current_user)):
    if article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    comments = [c.model_dump() for c in COMMENTS.values() if c.article_id == article_id]
    comments.sort(key=lambda c: c["created_at"], reverse=True)
    return {"comments": comments, "total": len(comments)}

class CommentReq(BaseModel):
    content: str

@app.post("/api/articles/{article_id}/comments")
def post_comment(article_id: str, req: CommentReq, user: User = Depends(get_current_user)):
    if article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    if not req.content.strip(): raise HTTPException(400, "Comment cannot be empty")
    cid = f"cmt_{uuid.uuid4().hex[:8]}"
    comment = Comment(id=cid, article_id=article_id, user_id=user.id, user_name=user.name,
                      content=req.content, created_at=datetime.utcnow().isoformat())
    COMMENTS[cid] = comment
    ARTICLES[article_id].comment_count += 1
    return {"comment": comment.model_dump(), "message": "Comment posted!"}

class ReplyReq(BaseModel):
    content: str

@app.post("/api/comments/{comment_id}/reply")
def reply_to_comment(comment_id: str, req: ReplyReq, user: User = Depends(get_current_user)):
    if comment_id not in COMMENTS: raise HTTPException(404, "Comment not found")
    parent = COMMENTS[comment_id]
    cid = f"cmt_{uuid.uuid4().hex[:8]}"
    reply = Comment(id=cid, article_id=parent.article_id, user_id=user.id, user_name=user.name,
                    content=req.content, parent_id=comment_id, created_at=datetime.utcnow().isoformat())
    COMMENTS[cid] = reply
    return {"comment": reply.model_dump(), "message": "Reply posted!"}

@app.post("/api/comments/{comment_id}/like")
def like_comment(comment_id: str, user: User = Depends(get_current_user)):
    if comment_id not in COMMENTS: raise HTTPException(404, "Comment not found")
    if comment_id in user.liked_comments: raise HTTPException(400, "Already liked")
    user.liked_comments.append(comment_id)
    COMMENTS[comment_id].likes += 1
    return {"liked": True, "total_likes": COMMENTS[comment_id].likes}

# ── Bookmarks ──

@app.get("/api/bookmarks")
def get_bookmarks(user: User = Depends(get_current_user)):
    items = [_article_summary(ARTICLES[aid]) for aid in user.bookmarks if aid in ARTICLES]
    return {"bookmarks": items, "total": len(items)}

class BookmarkReq(BaseModel):
    article_id: str

@app.post("/api/bookmarks/add")
def add_bookmark(req: BookmarkReq, user: User = Depends(get_current_user)):
    if req.article_id not in ARTICLES: raise HTTPException(404, "Article not found")
    if req.article_id in user.bookmarks: raise HTTPException(400, "Already bookmarked")
    user.bookmarks.append(req.article_id)
    return {"bookmarked": True, "total_bookmarks": len(user.bookmarks)}

@app.post("/api/bookmarks/remove")
def remove_bookmark(req: BookmarkReq, user: User = Depends(get_current_user)):
    if req.article_id not in user.bookmarks: raise HTTPException(400, "Not bookmarked")
    user.bookmarks.remove(req.article_id)
    return {"bookmarked": False, "total_bookmarks": len(user.bookmarks)}

# ── Follow Authors ──

@app.post("/api/authors/{author_id}/follow")
def follow_author(author_id: str, user: User = Depends(get_current_user)):
    if author_id not in AUTHORS: raise HTTPException(404, "Author not found")
    if author_id in user.following: raise HTTPException(400, "Already following")
    user.following.append(author_id)
    AUTHORS[author_id].follower_count += 1
    return {"following": True, "follower_count": AUTHORS[author_id].follower_count}

@app.post("/api/authors/{author_id}/unfollow")
def unfollow_author(author_id: str, user: User = Depends(get_current_user)):
    if author_id not in AUTHORS: raise HTTPException(404, "Author not found")
    if author_id not in user.following: raise HTTPException(400, "Not following")
    user.following.remove(author_id)
    AUTHORS[author_id].follower_count = max(0, AUTHORS[author_id].follower_count - 1)
    return {"following": False, "follower_count": AUTHORS[author_id].follower_count}

# ── Feed ──

@app.get("/api/feed")
def personalized_feed(user: User = Depends(get_current_user)):
    if user.following:
        items = [a for a in ARTICLES.values() if a.author_id in user.following and a.status == "published"]
    else:
        items = list(ARTICLES.values())
    items.sort(key=lambda a: a.published_at, reverse=True)
    return {"feed": [_article_summary(a) for a in items[:20]], "total": len(items)}

# ── Publish Articles ──

class ArticleSubmitReq(BaseModel):
    title: str
    subtitle: str = ""
    content: str
    section: str
    topics: list[str] = []
    status: str = "published"  # "draft" or "published"

@app.post("/api/articles")
def submit_article(req: ArticleSubmitReq, user: User = Depends(get_current_user)):
    if not req.title.strip(): raise HTTPException(400, "Title required")
    if not req.content.strip(): raise HTTPException(400, "Content required")
    if req.section not in SECTIONS: raise HTTPException(400, f"Invalid section. Valid: {SECTIONS}")
    artid = f"art_{uuid.uuid4().hex[:8]}"
    article = Article(
        id=artid, title=req.title, subtitle=req.subtitle, content=req.content,
        author_id=user.id, author_name=user.name, section=req.section,
        topics=req.topics, status=req.status, image_emoji="📝",
        read_time_min=max(1, len(req.content.split()) // 200),
        published_at=datetime.utcnow().isoformat(),
    )
    ARTICLES[artid] = article
    return {"article": _article_summary(article), "message": f"Article '{req.title}' {req.status}!"}

# ── User Content ──

@app.get("/api/me/articles")
def my_articles(user: User = Depends(get_current_user)):
    items = [_article_summary(a) for a in ARTICLES.values() if a.author_id == user.id and a.status == "published"]
    return {"articles": items, "total": len(items)}

@app.get("/api/me/drafts")
def my_drafts(user: User = Depends(get_current_user)):
    items = [_article_summary(a) for a in ARTICLES.values() if a.author_id == user.id and a.status == "draft"]
    return {"drafts": items, "total": len(items)}

@app.get("/api/me/activity")
def my_activity(user: User = Depends(get_current_user)):
    liked = [_article_summary(ARTICLES[aid]) for aid in user.liked_articles[-10:] if aid in ARTICLES]
    commented = [c.model_dump() for c in COMMENTS.values() if c.user_id == user.id][-10:]
    return {"liked_articles": liked, "recent_comments": commented,
            "total_likes": len(user.liked_articles), "total_comments": len(commented)}

# ── Notifications ──

@app.get("/api/notifications")
def get_notifications(user: User = Depends(get_current_user)):
    return {"notifications": user.notifications[-20:], "total": len(user.notifications), "unread": 0}

# ── SPA ──
@app.get("/", response_class=HTMLResponse)
def serve_spa():
    return HTMLResponse(content="""<!DOCTYPE html><html><head><title>The Daily Subnet</title></head>
<body style="font-family:Georgia,serif;max-width:800px;margin:0 auto;padding:40px">
<h1>📰 The Daily Subnet</h1><p><em>All the news that's fit to satirize</em></p>
<p>This is a SPA placeholder. The API is at <code>/api/articles</code></p>
<div id="root"></div></body></html>""")
