import os
import sys
import time
import random
import requests
import feedparser
from google import genai
from google.genai import types
import json
import re

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
# Attention : Le nouveau SDK préfère "GEMINI_API_KEY", mais on garde GOOGLE_API_KEY pour ne pas changer vos secrets
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Style visuel
BLOG_VISUAL_THEME = "minimalist vector art, engineering blueprint style, orange and dark grey color palette, high quality, 8k, unreal engine 5 render"

if not HASHNODE_TOKEN or not GOOGLE_API_KEY:
    print("❌ ERREUR : Clés API manquantes.")
    sys.exit(1)

# --- INITIALISATION NOUVEAU SDK (v2) ---
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    MODEL_NAME = "gemini-2.0-flash" # Le dernier modèle ultra-rapide
    print(f"🤖 Client Gemini initialisé sur le modèle : {MODEL_NAME}")
except Exception as e:
    print(f"❌ Erreur lors de l'initialisation du client Gemini : {e}")
    sys.exit(1)

# --- LISTE DES SOURCES (INGÉNIERIE & TECH) ---
RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence",
    "https://dev.to/feed/tag/engineering"
]

# --- AGENT 1 : LE VEILLEUR ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur : Scan des flux RSS...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                articles.append(f"- {entry.title} (Link: {entry.link})")
        except Exception as e:
            print(f"⚠️ Erreur lecture flux {feed_url}: {e}")
    
    random.shuffle(articles)
    context_articles = "\n".join(articles[:15])

    prompt = f"""
    Tu es un rédacteur en chef expert en ingénierie. Voici une liste d'articles récents :
    {context_articles}

    Sélectionne le sujet le plus pertinent, technique et intéressant pour un public d'ingénieurs francophones.
    Le sujet doit être actuel.
    
    Réponds UNIQUEMENT avec un objet JSON valide contenant :
    {{
        "title": "Un titre accrocheur en Français",
        "original_link": "Le lien de la source",
        "summary": "Un résumé en 3 phrases du sujet",
        "keywords": "liste, de, mots, cles"
    }}
    """
    
    try:
        # Notez la syntaxe V2 : contents au lieu de prompt
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json") # Force le JSON nativement
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Erreur Agent Veilleur : {e}")
        sys.exit(1)

# --- AGENT 2 : L'ARTISTE ---
def generate_image(prompt_description, is_cover=True):
    print(f"🎨 Agent Artiste : Création de l'image ({'Cover' if is_cover else 'Inline'})...")
    
    full_prompt = f"{prompt_description}, {BLOG_VISUAL_THEME}, no text, cinematic lighting"
    encoded_prompt = requests.utils.quote(full_prompt)
    seed = random.randint(0, 999999)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&model=flux"
    
    if not is_cover:
        return image_url 

    print("🧐 Agent Critique : Vérification de la qualité de l'image...")
    try:
        img_data = requests.get(image_url).content
        from PIL import Image
        import io
        image_pil = Image.open(io.BytesIO(img_data))

        validation_prompt = "Agis comme un critique d'art. Réponds seulement OUI si l'image est pro et sans défaut, sinon NON."
        
        # Envoi de l'image avec le nouveau SDK
        validation = client.models.generate_content(
            model=MODEL_NAME,
            contents=[validation_prompt, image_pil]
        )
        
        if "NON" in validation.text.upper():
            print("⚠️ Image rejetée. Nouvelle tentative...")
            seed2 = random.randint(0, 999999)
            return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed2}&model=flux"
        
        print("✅ Image validée.")
        return image_url

    except Exception as e:
        print(f"⚠️ Warning validation image ({e}), utilisation telle quelle.")
        return image_url

# --- AGENT 3 : LE RÉDACTEUR ---
def write_article(topic_data):
    print(f"✍️  Agent Rédacteur : Rédaction sur '{topic_data['title']}'...")
    
    prompt = f"""
    Rédige un article de blog technique (min 1500 mots) en Français sur :
    Titre : {topic_data['title']}
    Source : {topic_data['summary']}
    
    CONSIGNES :
    1. Ton Expert mais pédagogique.
    2. Structure Markdown claire (H2, H3, listes).
    3. Ajoute 2 placeholders d'images exactement comme ça : ![IMG_PROMPT: description en anglais]
    4. Signature : "Rédigé par Nathan Remacle."
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ Erreur Agent Rédacteur : {e}")
        sys.exit(1)

# --- PUBLICATION HASHNODE ---
def publish_to_hashnode(title, content, cover_image_url):
    print("🚀 Publication sur Hashnode...")
    
    # Récupération ID
    query_pub = """query { me { publications(first: 1) { edges { node { id } } } } }"""
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if 'errors' in data: raise ValueError(data['errors'])
        pub_id = data['data']['me']['publications']['edges'][0]['node']['id']
    except Exception as e:
        print(f"❌ Erreur ID Hashnode : {e}")
        sys.exit(1)

    # Publication
    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { url }
      }
    }
    """
    variables = {
        "input": {
            "title": title,
            "contentMarkdown": content,
            "publicationId": pub_id,
            "coverImageOptions": {
                "coverImageURL": cover_image_url,
                "isCoverAttributionHidden": True
            },
            "tags": [{"slug": "engineering", "name": "Engineering"}]
        }
    }
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        resp_json = resp.json()
        if "errors" in resp_json:
            print("❌ Erreur Hashnode:", resp_json['errors'])
            sys.exit(1)
        print(f"✅ Article publié : {resp_json['data']['publishPost']['post']['url']}")
    except Exception as e:
        print(f"❌ Erreur Publication : {e}")
        sys.exit(1)

# --- MAIN ---
def main():
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    cover_url = generate_image(f"Editorial illustration for '{topic['title']}'", is_cover=True)
    
    raw_content = write_article(topic)
    
    def replace_image(match):
        url = generate_image(match.group(1), is_cover=False)
        return f"![Illustration]({url})"
    
    final_content = re.sub(r'!\[IMG_PROMPT: (.*?)\]', replace_image, raw_content)
    
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()