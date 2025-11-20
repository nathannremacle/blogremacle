import os
import sys
import time
import random
import requests
import feedparser
import google.generativeai as genai
from datetime import datetime

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Style visuel cohérent pour ton blog (Change ceci selon tes goûts)
BLOG_VISUAL_THEME = "minimalist vector art, engineering blueprint style, orange and dark grey color palette, high quality, 8k, unreal engine 5 render"

if not HASHNODE_TOKEN or not GOOGLE_API_KEY:
    print("❌ ERREUR : Clés API manquantes.")
    sys.exit(1)

# Configuration Gemini
genai.configure(api_key=GOOGLE_API_KEY)
# On utilise 1.5 Flash car il est rapide, a une grande fenêtre de contexte et est gratuit
model = genai.GenerativeModel('gemini-1.5-flash')
vision_model = genai.GenerativeModel('gemini-1.5-flash')

# --- LISTE DES SOURCES (INGÉNIERIE & TECH) ---
RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence",
    "https://dev.to/feed/tag/engineering"
]

# --- AGENT 1 : LE VEILLEUR (Recherche de sujet) ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur : Scan des flux RSS...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]: # Prendre les 3 plus récents de chaque flux
                articles.append(f"- {entry.title} (Link: {entry.link})")
        except Exception as e:
            print(f"⚠️ Erreur lecture flux {feed_url}: {e}")
    
    # Mélanger pour ne pas toujours prendre le premier flux
    random.shuffle(articles)
    context_articles = "\n".join(articles[:15])

    prompt = f"""
    Tu es un rédacteur en chef expert en ingénierie. Voici une liste d'articles récents :
    {context_articles}

    Sélectionne le sujet le plus pertinent, technique et intéressant pour un public d'ingénieurs francophones.
    Le sujet doit être actuel.
    
    Réponds UNIQUEMENT avec un objet JSON (sans markdown) contenant :
    {{
        "title": "Un titre accrocheur en Français",
        "original_link": "Le lien de la source",
        "summary": "Un résumé en 3 phrases du sujet",
        "keywords": "liste, de, mots, cles"
    }}
    """
    
    response = model.generate_content(prompt)
    # Nettoyage basique du JSON si Gemini met des ```json
    cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
    import json
    return json.loads(cleaned_text)

# --- AGENT 2 : L'ARTISTE (Génération & Validation d'image) ---
def generate_image(prompt_description, is_cover=True):
    """
    Génère une image via Pollinations.ai (Gratuit & sans clé API), 
    puis la vérifie avec Gemini Vision.
    """
    print(f"🎨 Agent Artiste : Création de l'image ({'Cover' if is_cover else 'Inline'})...")
    
    # Construction du prompt visuel
    full_prompt = f"{prompt_description}, {BLOG_VISUAL_THEME}, no text, cinematic lighting"
    encoded_prompt = requests.utils.quote(full_prompt)
    
    # Utilisation de Pollinations (Flux ou SDXL)
    # On ajoute un seed aléatoire pour éviter le cache
    seed = random.randint(0, 999999)
    image_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){encoded_prompt}?width=1280&height=720&seed={seed}&model=flux"
    
    if not is_cover:
        return image_url # Pas de validation stricte pour les images in-line pour gagner du temps

    # --- VALIDATION PAR IA (Critique d'art) ---
    print("🧐 Agent Critique : Vérification de la qualité de l'image...")
    try:
        # Télécharger l'image temporairement pour l'envoyer à Gemini
        img_data = requests.get(image_url).content
        from PIL import Image
        import io
        image_pil = Image.open(io.BytesIO(img_data))

        validation_prompt = """
        Agis comme un critique d'art et expert en publication web.
        Regarde cette image. Est-elle de haute qualité, sans déformations grotesques, et semble-t-elle professionnelle pour un blog d'ingénierie ?
        Réponds UNIQUEMENT par 'OUI' ou 'NON'.
        """
        validation = vision_model.generate_content([validation_prompt, image_pil])
        
        if "NON" in validation.text.upper():
            print("⚠️ Image rejetée par l'IA. Nouvelle tentative...")
            # On change le seed et on réessaie (appel récursif simple, max 1 fois pour éviter boucle infinie)
            # Pour simplifier ici, on renvoie juste une nouvelle URL avec seed différent
            seed2 = random.randint(0, 999999)
            return f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){encoded_prompt}?width=1280&height=720&seed={seed2}&model=flux"
        
        print("✅ Image validée par l'IA.")
        return image_url

    except Exception as e:
        print(f"⚠️ Warning: Impossible de valider l'image ({e}), on utilise l'URL telle quelle.")
        return image_url

# --- AGENT 3 : LE RÉDACTEUR (Rédaction de l'article) ---
def write_article(topic_data):
    print(f"✍️  Agent Rédacteur : Rédaction sur '{topic_data['title']}'...")
    
    prompt = f"""
    Rédige un article de blog technique et approfondi (minimum 1500 mots) en Français sur ce sujet :
    Titre : {topic_data['title']}
    Source contextuelle : {topic_data['summary']}
    
    CONSIGNES STRICTES DE QUALITÉ :
    1. Ton : Expert, ingénieur à ingénieur, mais fluide et pédagogique.
    2. Structure : Introduction accrocheuse (pas de "Dans cet article..."), 3 à 4 grandes sections techniques, cas d'usage réel, conclusion prospective.
    3. Formatage : Utilise le Markdown. Ajoute du **gras** pour les concepts clés. Utilise des listes à puces.
    4. Code : Si le sujet s'y prête (logiciel, data, cloud), INCLUS des blocs de code réalistes.
    5. Images : Tu DOIS insérer au moins 2 placeholders d'images dans le texte exactement sous cette forme : 
       ![IMG_PROMPT: description visuelle précise de l'image en anglais]
    6. Auteur : Termine par "Rédigé par Nathan Remacle."
    7. Interdit : Ne commence pas par "Titre:", ne dis pas "En conclusion". Sois naturel.
    
    Fais preuve d'esprit critique. N'hésite pas à nuancer les propos.
    """
    
    response = model.generate_content(prompt)
    return response.text

# --- FONCTION PUBLICATION HASHNODE (Similaire à ton ancien script mais nettoyé) ---
def publish_to_hashnode(title, content, cover_image_url):
    print("🚀 Publication sur Hashnode...")
    
    # 1. Récupérer l'ID de publication (peut être mis en cache ou hardcodé pour optimiser)
    query_pub = """
    query {
      me {
        publications(first: 1) {
          edges {
            node {
              id
            }
          }
        }
      }
    }
    """
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    resp = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers)
    pub_id = resp.json()['data']['me']['publications']['edges'][0]['node']['id']

    # 2. Mutation de publication
    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          url
        }
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
            "tags": [{"slug": "engineering", "name": "Engineering"}, {"slug": "tech", "name": "Tech"}] # Tu peux dynamiser ça
        }
    }
    
    resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
    
    if "errors" in resp.json():
        print("❌ Erreur Hashnode:", resp.json()['errors'])
        sys.exit(1)
        
    print(f"✅ Article publié : {resp.json()['data']['publishPost']['post']['url']}")

# --- ORCHESTRATION ---
def main():
    # 1. Trouver le sujet
    topic = fetch_trending_topic()
    print(f"🎯 Sujet choisi : {topic['title']}")
    
    # 2. Générer la couverture
    cover_prompt = f"Editorial illustration for an article titled '{topic['title']}', {topic['summary']}"
    cover_url = generate_image(cover_prompt, is_cover=True)
    
    # 3. Rédiger l'article
    raw_content = write_article(topic)
    
    # 4. Traiter les images in-line (Remplacer les placeholders par de vraies images AI)
    import re
    def replace_image_placeholder(match):
        img_prompt = match.group(1)
        print(f"🖼️ Génération image interne : {img_prompt}")
        url = generate_image(img_prompt, is_cover=False)
        return f"![Illustration : {img_prompt}]({url})"
    
    # Regex pour trouver ![IMG_PROMPT: ...]
    final_content = re.sub(r'!\[IMG_PROMPT: (.*?)\]', replace_image_placeholder, raw_content)
    
    # 5. Publier
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()