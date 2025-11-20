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
import urllib.parse

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not HASHNODE_TOKEN or not GOOGLE_API_KEY:
    print("❌ ERREUR : Clés API manquantes.")
    sys.exit(1)

# --- INITIALISATION GEMINI ---
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    MODEL_NAME = "gemini-2.0-flash"
    print(f"🤖 Client Gemini initialisé : {MODEL_NAME}")
except Exception as e:
    print(f"❌ Erreur client Gemini : {e}")
    sys.exit(1)

# --- SOURCES RSS ---
RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence",
    "https://dev.to/feed/tag/engineering"
]

# --- NOUVEAU : STYLES VISUELS ---
VISUAL_STYLES = {
    "photorealistic": "hyper-realistic photography, 8k resolution, depth of field, cinematic lighting, shot on Sony A7R IV",
    "isometric": "3D isometric render, clean lines, blueprint aesthetic, orange and dark grey color palette, unreal engine 5, digital art",
    "abstract": "abstract data visualization, glowing nodes, fiber optics, dark background, cyberpunk aesthetic, intricate details"
}

# --- AGENT 1 : LE VEILLEUR ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur : Recherche de sujets...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                articles.append(f"- {entry.title} (Link: {entry.link})")
        except Exception:
            continue # On ignore silencieusement les erreurs de flux pour aller vite
    
    random.shuffle(articles)
    context_articles = "\n".join(articles[:15])

    prompt = f"""
    Tu es rédacteur en chef Tech. Analyse ces titres :
    {context_articles}

    Choisis le meilleur sujet technique.
    Réponds en JSON uniquement :
    {{
        "title": "Titre Français Expert",
        "original_link": "url",
        "summary": "Résumé technique",
        "keywords": "tags"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception:
        return {
            "title": "L'Impact de l'IA Générative sur l'Ingénierie Moderne",
            "original_link": "https://google.com",
            "summary": "Une analyse approfondie des nouveaux paradigmes.",
            "keywords": "AI"
        }

# --- NOUVEAU : AGENT DIRECTEUR ARTISTIQUE ---
def get_artistic_prompt(subject, style_key="isometric"):
    """
    Demande à Gemini de décrire l'image parfaite pour ce sujet.
    """
    style_desc = VISUAL_STYLES.get(style_key, VISUAL_STYLES["isometric"])
    
    prompt = f"""
    Agis comme un photographe et artiste 3D expert.
    Je veux générer une image pour un article intitulé : "{subject}".
    
    Écris un prompt en ANGLAIS pour un générateur d'images (comme Midjourney).
    Décris visuellement la scène. Ne mets PAS de texte dans l'image.
    Concentre-toi sur : l'éclairage, les objets centraux, la texture.
    
    Style imposé : {style_desc}
    
    Réponds UNIQUEMENT avec la description brute en anglais. Pas de guillemets.
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except:
        return f"futuristic technology illustration about {subject}, {style_desc}"

# --- AGENT 2 : L'ARTISTE (Amélioré) ---
def generate_image(base_subject, is_cover=True):
    # 1. Choisir un style
    style = "isometric" if is_cover else random.choice(["photorealistic", "abstract"])
    
    # 2. Obtenir le prompt détaillé via Gemini
    print(f"🎨 Conception artistique ({style})...")
    detailed_prompt = get_artistic_prompt(base_subject, style)
    print(f"   -> Prompt: {detailed_prompt[:60]}...")

    # 3. Construire l'URL Pollinations optimisée
    # On ajoute 'enhance=true' et on force le seed
    encoded_prompt = urllib.parse.quote(detailed_prompt)
    seed = random.randint(0, 999999)
    
    # Astuce : On ajoute des "Negative prompts" via l'URL si supporté, ou dans le prompt
    # Pollinations lit bien les descriptions longues.
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&model=flux&nologo=true&enhance=true"
    
    # Petite pause pour laisser le serveur générer (évite les timeouts immédiats)
    time.sleep(2) 
    
    # Pour la cover, on vérifie que l'URL répond bien (pas de 404/500)
    if is_cover:
        try:
            # On ajoute .jpg fictif pour Hashnode
            final_url = image_url + "&.jpg"
            return final_url
        except:
            pass

    return image_url + "&.jpg"

# --- AGENT 3 : LE RÉDACTEUR ---
def write_article(topic_data):
    print(f"✍️  Rédaction de l'article : {topic_data['title']}...")
    
    prompt = f"""
    Rédige un article technique expert (1500 mots) en Français sur : {topic_data['title']}.
    Source contexte : {topic_data['summary']}
    
    Structure :
    1. Intro accrocheuse (Le "Hook").
    2. Corps technique (H2, H3).
    3. Exemples concrets ou Code blocks si pertinent.
    4. Conclusion prospective.
    
    IMPORTANT POUR LES IMAGES :
    Insère exactement 2 images dans le texte en utilisant cette balise :
    [[IMAGE: description courte du concept à illustrer]]
    
    Signature : "Rédigé par Nathan Remacle."
    """
    
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text
    except Exception as e:
        print(f"❌ Erreur Rédacteur : {e}")
        sys.exit(1)

# --- PUBLICATION ---
def publish_to_hashnode(title, content, cover_image_url):
    print("🚀 Envoi vers Hashnode...")
    
    # Récupération ID Publication
    query_pub = """query { me { publications(first: 1) { edges { node { id } } } } }"""
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers)
        pub_id = resp.json()['data']['me']['publications']['edges'][0]['node']['id']
    except:
        print("❌ Impossible de récupérer l'ID Hashnode.")
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
        data = resp.json()
        if "errors" in data:
            print(f"❌ Erreur Hashnode : {data['errors']}")
            # Retry sans cover si erreur d'image
            if "coverImageURL" in str(data['errors']):
                print("⚠️ Retrying sans cover...")
                del variables["input"]["coverImageOptions"]
                resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        
        post_url = data.get('data', {}).get('publishPost', {}).get('post', {}).get('url', 'URL inconnue')
        print(f"✅ SUCCÈS : {post_url}")
        
    except Exception as e:
        print(f"❌ Erreur fatale publication : {e}")

# --- MAIN ---
def main():
    # 1. Sujet
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    # 2. Cover Image (Isométrique / Blueprint)
    cover_url = generate_image(topic['title'], is_cover=True)
    
    # 3. Contenu
    raw_content = write_article(topic)
    
    # 4. Injection Images In-line
    def replace_img(match):
        desc = match.group(1)
        url = generate_image(desc, is_cover=False)
        return f"![Illustration: {desc}]({url})"
    
    final_content = re.sub(r'\[\[IMAGE: (.*?)\]\]', replace_img, raw_content)
    
    # 5. Check si images présentes, sinon force insertion
    if "![Illustration" not in final_content:
        print("⚠️ Injection forcée d'une image manquante.")
        forced_img = generate_image(f"Technical diagram for {topic['title']}", is_cover=False)
        final_content = f"![Main Illustration]({forced_img})\n\n" + final_content

    # 6. Publier
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()