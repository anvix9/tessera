"""
RealWorld Conduit — Local implementation

Exact replica of the API at https://api.realworld.show/api
This is a Medium.com clone used as the standard benchmark for web frameworks.

The real site is live and deployed. This local version matches its API exactly
so we can test auto-discovery against it.

NOTE: Uses /api prefix like the real deployment. No OpenAPI exposed.

Endpoints (20 methods across 11 paths):
  POST /api/users/login              - Login
  POST /api/users                    - Register
  GET  /api/user                     - Get current user (auth)
  PUT  /api/user                     - Update current user (auth)
  GET  /api/profiles/{username}      - Get profile
  POST /api/profiles/{username}/follow   - Follow user (auth)
  DELETE /api/profiles/{username}/follow - Unfollow user (auth)
  GET  /api/articles/feed            - Feed articles (auth)
  GET  /api/articles                 - List/filter articles
  POST /api/articles                 - Create article (auth)
  GET  /api/articles/{slug}          - Get article
  PUT  /api/articles/{slug}          - Update article (auth)
  DELETE /api/articles/{slug}        - Delete article (auth)
  GET  /api/articles/{slug}/comments - Get comments
  POST /api/articles/{slug}/comments - Add comment (auth)
  DELETE /api/articles/{slug}/comments/{id} - Delete comment (auth)
  POST /api/articles/{slug}/favorite   - Favorite article (auth)
  DELETE /api/articles/{slug}/favorite - Unfavorite article (auth)
  GET  /api/tags                     - Get tags

QUIRKS that make this different from our other simulations:
- /users/login instead of /auth/login
- /user (singular) for current user
- Slug-based articles instead of ID-based
- Nested /articles/{slug}/favorite (not /articles/{slug}/like)
- DELETE for unfollow and unfavorite (not POST /unlike)
- Tag-based filtering
- RealWorld-style JSON wrapping: {"article": {...}}, {"user": {...}}
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid, hashlib, jwt, re, random

JWT_SECRET = "conduit-realworld-2026"
JWT_ALGORITHM = "HS256"

# ── Models ──

class User(BaseModel):
    id: str
    email: str
    username: str
    password_hash: str
    bio: str = ""
    image: str = ""
    following: list[str] = []  # usernames
    favorites: list[str] = []  # article slugs
    created_at: str = ""

class Article(BaseModel):
    slug: str
    title: str
    description: str
    body: str
    tag_list: list[str] = []
    author_username: str = ""
    favorites_count: int = 0
    created_at: str = ""
    updated_at: str = ""

class Comment(BaseModel):
    id: int
    body: str
    author_username: str
    article_slug: str
    created_at: str = ""

# ── Store ──

USERS: dict[str, User] = {}  # username -> user
EMAIL_INDEX: dict[str, str] = {}  # email -> username
ARTICLES: dict[str, Article] = {}  # slug -> article
COMMENTS: list[Comment] = []
COMMENT_COUNTER = 0
TAGS: set = set()

def _hash(pw): return hashlib.sha256(f"rw-{pw}".encode()).hexdigest()

def _slugify(title):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return f"{slug}-{uuid.uuid4().hex[:6]}"

def seed_data():
    global COMMENT_COUNTER

    # Users
    users_data = [
        ("johnjacob", "jake@jake.jake", "jakejake", "I work at statefarm", "https://i.pravatar.cc/300?u=jake"),
        ("celeb_author", "celeb@realworld.io", "password1", "Famous writer and blogger", "https://i.pravatar.cc/300?u=celeb"),
        ("techie", "tech@dev.io", "code123", "Full-stack developer", "https://i.pravatar.cc/300?u=tech"),
    ]
    for username, email, pw, bio, image in users_data:
        USERS[username] = User(id=f"u_{uuid.uuid4().hex[:8]}", email=email, username=username,
                                password_hash=_hash(pw), bio=bio, image=image,
                                created_at=datetime.utcnow().isoformat())
        EMAIL_INDEX[email] = username

    # Articles
    articles_data = [
        ("How to train your dragon", "Ever wonder how?",
         "You have to believe in yourself. That's the secret. The dragon will sense your confidence and respond accordingly. Training requires patience, dedication, and a deep understanding of dragon psychology.",
         ["training", "dragons"], "johnjacob"),
        ("The Future of AI in 2026", "AI is everywhere now",
         "Artificial intelligence has become ubiquitous in our daily lives. From the moment we wake up to our AI-optimized alarm, to the personalized news feed over breakfast, AI shapes every interaction. But what comes next?",
         ["ai", "technology", "future"], "celeb_author"),
        ("Building a REST API from Scratch", "A complete guide",
         "In this tutorial, we'll build a REST API using modern frameworks. We'll cover authentication, validation, testing, and deployment. By the end, you'll have a production-ready API.",
         ["programming", "api", "tutorial"], "techie"),
        ("Why Functional Programming Matters", "FP is not just a trend",
         "Functional programming offers a different paradigm for thinking about software. Immutability, pure functions, and composition lead to more predictable, testable code.",
         ["programming", "functional", "coding"], "techie"),
        ("My Journey Through South America", "6 months, 8 countries",
         "From the glaciers of Patagonia to the Amazon rainforest, South America is a continent of extremes. Here's what I learned traveling solo for six months through this incredible region.",
         ["travel", "adventure", "southamerica"], "celeb_author"),
        ("The Art of Sourdough", "From starter to loaf",
         "Making sourdough bread is both science and art. The wild yeast, the fermentation, the shaping — each step requires attention and patience. Here's my complete guide to artisan sourdough.",
         ["food", "baking", "sourdough"], "johnjacob"),
    ]

    for title, desc, body, tags, author in articles_data:
        slug = _slugify(title)
        ARTICLES[slug] = Article(
            slug=slug, title=title, description=desc, body=body,
            tag_list=tags, author_username=author,
            favorites_count=random.randint(0, 50),
            created_at=(datetime.utcnow() - timedelta(days=random.randint(1, 90))).isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        TAGS.update(tags)

    # Comments
    comment_texts = [
        "Great article! Really enjoyed this.",
        "This is exactly what I needed to read today.",
        "Interesting perspective. I'd love to hear more about this.",
        "I disagree with some points but overall well written.",
        "Bookmarking this for later. Thanks for sharing!",
    ]
    slugs = list(ARTICLES.keys())
    for i in range(12):
        COMMENT_COUNTER += 1
        COMMENTS.append(Comment(
            id=COMMENT_COUNTER, body=comment_texts[i % len(comment_texts)],
            author_username=["johnjacob", "celeb_author", "techie"][i % 3],
            article_slug=slugs[i % len(slugs)],
            created_at=(datetime.utcnow() - timedelta(hours=random.randint(1, 500))).isoformat(),
        ))

    # Some follows
    USERS["johnjacob"].following.append("celeb_author")
    USERS["techie"].following.append("johnjacob")


# ── Auth ──

def create_token(user):
    return jwt.encode({"user_id": user.id, "username": user.username, "email": user.email,
                        "exp": datetime.utcnow() + timedelta(hours=24)},
                       JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Auth is optional — returns None if no token."""
    if not authorization: return None
    token = authorization.replace("Token ", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return USERS.get(payload.get("username"))
    except Exception:
        return None

def get_required_user(authorization: Optional[str] = Header(None)) -> User:
    """Auth required."""
    user = get_optional_user(authorization)
    if not user: raise HTTPException(401, "Authentication required")
    return user


# ── Helpers ──

def _format_user(user: User, token: str = None):
    d = {"email": user.email, "username": user.username, "bio": user.bio, "image": user.image}
    if token: d["token"] = token
    return {"user": d}

def _format_profile(user: User, current_user: Optional[User] = None):
    following = current_user.username if current_user else None
    return {"profile": {
        "username": user.username, "bio": user.bio, "image": user.image,
        "following": user.username in (current_user.following if current_user else []),
    }}

def _format_article(article: Article, current_user: Optional[User] = None):
    author = USERS.get(article.author_username)
    return {"slug": article.slug, "title": article.title, "description": article.description,
            "body": article.body, "tagList": article.tag_list,
            "createdAt": article.created_at, "updatedAt": article.updated_at,
            "favorited": article.slug in (current_user.favorites if current_user else []),
            "favoritesCount": article.favorites_count,
            "author": {"username": article.author_username, "bio": author.bio if author else "",
                       "image": author.image if author else "", "following": False}}

def _format_comment(c: Comment):
    author = USERS.get(c.author_username)
    return {"id": c.id, "createdAt": c.created_at, "updatedAt": c.created_at,
            "body": c.body, "author": {"username": c.author_username,
            "bio": author.bio if author else "", "image": author.image if author else "",
            "following": False}}


# ── App — NO OpenAPI ──

@asynccontextmanager
async def lifespan(app):
    seed_data()
    yield

app = FastAPI(title="Conduit", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ═══ AUTH ═══

class LoginReq(BaseModel):
    user: dict

class RegisterReq(BaseModel):
    user: dict

@app.post("/api/users/login")
def login(req: LoginReq):
    email = req.user.get("email", "")
    password = req.user.get("password", "")
    username = EMAIL_INDEX.get(email)
    if not username: raise HTTPException(422, {"errors": {"email or password": ["is invalid"]}})
    user = USERS[username]
    if user.password_hash != _hash(password):
        raise HTTPException(422, {"errors": {"email or password": ["is invalid"]}})
    return _format_user(user, create_token(user))

@app.post("/api/users")
def register(req: RegisterReq):
    username = req.user.get("username", "")
    email = req.user.get("email", "")
    password = req.user.get("password", "")
    if not username or not email or not password:
        raise HTTPException(422, {"errors": {"body": ["can't be blank"]}})
    if username in USERS: raise HTTPException(422, {"errors": {"username": ["has already been taken"]}})
    if email in EMAIL_INDEX: raise HTTPException(422, {"errors": {"email": ["has already been taken"]}})
    user = User(id=f"u_{uuid.uuid4().hex[:8]}", email=email, username=username,
                password_hash=_hash(password), created_at=datetime.utcnow().isoformat())
    USERS[username] = user
    EMAIL_INDEX[email] = username
    return _format_user(user, create_token(user))

@app.get("/api/user")
def get_current_user(user: User = Depends(get_required_user)):
    return _format_user(user, create_token(user))

class UpdateUserReq(BaseModel):
    user: dict

@app.put("/api/user")
def update_user(req: UpdateUserReq, user: User = Depends(get_required_user)):
    if "email" in req.user: user.email = req.user["email"]
    if "bio" in req.user: user.bio = req.user["bio"]
    if "image" in req.user: user.image = req.user["image"]
    if "username" in req.user: user.username = req.user["username"]
    return _format_user(user, create_token(user))


# ═══ PROFILES ═══

@app.get("/api/profiles/{username}")
def get_profile(username: str, user: Optional[User] = Depends(get_optional_user)):
    if username not in USERS: raise HTTPException(404, "Profile not found")
    return _format_profile(USERS[username], user)

@app.post("/api/profiles/{username}/follow")
def follow_user(username: str, user: User = Depends(get_required_user)):
    if username not in USERS: raise HTTPException(404, "Profile not found")
    if username not in user.following: user.following.append(username)
    return _format_profile(USERS[username], user)

@app.delete("/api/profiles/{username}/follow")
def unfollow_user(username: str, user: User = Depends(get_required_user)):
    if username not in USERS: raise HTTPException(404, "Profile not found")
    user.following = [f for f in user.following if f != username]
    return _format_profile(USERS[username], user)


# ═══ ARTICLES ═══

@app.get("/api/articles/feed")
def feed_articles(limit: int = Query(20), offset: int = Query(0),
                  user: User = Depends(get_required_user)):
    items = [a for a in ARTICLES.values() if a.author_username in user.following]
    items.sort(key=lambda a: a.created_at, reverse=True)
    return {"articles": [_format_article(a, user) for a in items[offset:offset+limit]],
            "articlesCount": len(items)}

@app.get("/api/articles")
def list_articles(tag: Optional[str] = Query(None), author: Optional[str] = Query(None),
                  favorited: Optional[str] = Query(None),
                  limit: int = Query(20), offset: int = Query(0),
                  user: Optional[User] = Depends(get_optional_user)):
    items = list(ARTICLES.values())
    if tag: items = [a for a in items if tag in a.tag_list]
    if author: items = [a for a in items if a.author_username == author]
    if favorited and favorited in USERS:
        fav_user = USERS[favorited]
        items = [a for a in items if a.slug in fav_user.favorites]
    items.sort(key=lambda a: a.created_at, reverse=True)
    return {"articles": [_format_article(a, user) for a in items[offset:offset+limit]],
            "articlesCount": len(items)}

class CreateArticleReq(BaseModel):
    article: dict

@app.post("/api/articles")
def create_article(req: CreateArticleReq, user: User = Depends(get_required_user)):
    title = req.article.get("title", "")
    desc = req.article.get("description", "")
    body = req.article.get("body", "")
    tags = req.article.get("tagList", [])
    if not title or not body: raise HTTPException(422, {"errors": {"body": ["can't be blank"]}})
    slug = _slugify(title)
    article = Article(slug=slug, title=title, description=desc, body=body,
                      tag_list=tags, author_username=user.username,
                      created_at=datetime.utcnow().isoformat(),
                      updated_at=datetime.utcnow().isoformat())
    ARTICLES[slug] = article
    TAGS.update(tags)
    return {"article": _format_article(article, user)}

@app.get("/api/articles/{slug}")
def get_article(slug: str, user: Optional[User] = Depends(get_optional_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    return {"article": _format_article(ARTICLES[slug], user)}

class UpdateArticleReq(BaseModel):
    article: dict

@app.put("/api/articles/{slug}")
def update_article(slug: str, req: UpdateArticleReq, user: User = Depends(get_required_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    a = ARTICLES[slug]
    if a.author_username != user.username: raise HTTPException(403, "Not authorized")
    if "title" in req.article: a.title = req.article["title"]
    if "description" in req.article: a.description = req.article["description"]
    if "body" in req.article: a.body = req.article["body"]
    a.updated_at = datetime.utcnow().isoformat()
    return {"article": _format_article(a, user)}

@app.delete("/api/articles/{slug}")
def delete_article(slug: str, user: User = Depends(get_required_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    if ARTICLES[slug].author_username != user.username: raise HTTPException(403, "Not authorized")
    del ARTICLES[slug]
    return {}


# ═══ COMMENTS ═══

@app.get("/api/articles/{slug}/comments")
def get_comments(slug: str, user: Optional[User] = Depends(get_optional_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    comments = [_format_comment(c) for c in COMMENTS if c.article_slug == slug]
    return {"comments": comments}

class AddCommentReq(BaseModel):
    comment: dict

@app.post("/api/articles/{slug}/comments")
def add_comment(slug: str, req: AddCommentReq, user: User = Depends(get_required_user)):
    global COMMENT_COUNTER
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    body = req.comment.get("body", "")
    if not body: raise HTTPException(422, {"errors": {"body": ["can't be blank"]}})
    COMMENT_COUNTER += 1
    c = Comment(id=COMMENT_COUNTER, body=body, author_username=user.username,
                article_slug=slug, created_at=datetime.utcnow().isoformat())
    COMMENTS.append(c)
    return {"comment": _format_comment(c)}

@app.delete("/api/articles/{slug}/comments/{comment_id}")
def delete_comment(slug: str, comment_id: int, user: User = Depends(get_required_user)):
    global COMMENTS
    COMMENTS = [c for c in COMMENTS if not (c.id == comment_id and c.article_slug == slug)]
    return {}


# ═══ FAVORITES ═══

@app.post("/api/articles/{slug}/favorite")
def favorite_article(slug: str, user: User = Depends(get_required_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    if slug not in user.favorites:
        user.favorites.append(slug)
        ARTICLES[slug].favorites_count += 1
    return {"article": _format_article(ARTICLES[slug], user)}

@app.delete("/api/articles/{slug}/favorite")
def unfavorite_article(slug: str, user: User = Depends(get_required_user)):
    if slug not in ARTICLES: raise HTTPException(404, "Article not found")
    if slug in user.favorites:
        user.favorites.remove(slug)
        ARTICLES[slug].favorites_count = max(0, ARTICLES[slug].favorites_count - 1)
    return {"article": _format_article(ARTICLES[slug], user)}


# ═══ TAGS ═══

@app.get("/api/tags")
def get_tags():
    return {"tags": sorted(TAGS)}
